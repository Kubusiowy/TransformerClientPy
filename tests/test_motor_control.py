from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from transformer_client.control import MotorControlLoop, RegisterControlStore
from transformer_client.models import ClientConfig, MeterDto, RegisterDto, TransformerDto
from transformer_client.state import ApplicationState


class MotorControlLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1)
        self.elapsed = 0.0
        self.state = ApplicationState()
        self.transformer = TransformerDto(id="test", name="Test", location=None)
        self.meter = MeterDto(
            id=1, name="Meter", deviceCode="M1", enabled=True,
            serialPort="test", baudRate=9600, dataBits=8, parity="NONE",
            stopBits=1, slaveId=1, byteOrder="BIG_ENDIAN", pollIntervalMs=100,
        )
        self.register = RegisterDto(
            id=10, meterId=1, name="Voltage", registerType="HOLDING",
            address=100, length=2, dataType="FLOAT32", scale=1.0,
            targetValue=None, thresholdValue=None, unit="V", enabled=True,
            orderIndex=0,
        )
        self.other_register = replace(self.register, id=11, name="Other", address=102)
        self.state.apply_configuration(
            [self.transformer], self.transformer, [self.meter],
            {1: [self.register, self.other_register]}, {}, None,
        )
        self.state.set_register_control(1, 10, 100.0, 1.0, True)
        self.clear_active = Mock(side_effect=self.state.clear_active_control)
        self.loop = MotorControlLoop(
            self.state,
            ClientConfig(motorDirectionInverted=False, motorSettleMs=1000),
            self.clear_active,
        )
        self.loop.driver = Mock()

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
        self.now += timedelta(seconds=seconds)

    def measure(self, value: float, register: RegisterDto | None = None) -> None:
        with patch("transformer_client.state.datetime") as clock:
            clock.now.return_value = self.now
            self.state.update_register_value(1, register or self.register, value)

    def tick(self) -> dict:
        # Execute the real control loop once with no threads, sleeps or hardware.
        with (
            patch.object(self.loop._stop_event, "wait", side_effect=[False, True]),
            patch("transformer_client.control.time.monotonic", return_value=self.elapsed),
            patch("transformer_client.control.datetime") as clock,
        ):
            clock.now.return_value = self.now
            self.loop._run()
        return self.state.snapshot()

    def movement_directions(self) -> list[str]:
        return [
            call.args[0] for call in self.loop.driver.set_direction.call_args_list
            if call.args[0] != "STOPPED"
        ]

    def assert_active(self) -> None:
        context = self.state.get_active_control_context()
        self.assertIsNotNone(context)
        self.assertEqual((context.meter_id, context.register_id), (1, 10))
        self.assertEqual(context.target_value, 100.0)
        self.clear_active.assert_not_called()

    def test_stale_measurement_pauses_and_fresh_measurement_resumes(self) -> None:
        self.measure(90.0)
        self.assertEqual(self.tick()["motor_state"], "RUNNING")

        for _ in range(3):
            self.advance(6.0)
            snapshot = self.tick()
            self.assertEqual(snapshot["motor_state"], "WAITING")
            self.assertEqual(snapshot["motor_direction"], "STOPPED")
            self.assert_active()
        self.assertEqual(self.movement_directions(), ["FORWARD"])

        self.measure(110.0)
        self.assertEqual(self.tick()["motor_state"], "RUNNING")
        self.assertEqual(self.movement_directions(), ["FORWARD", "REVERSE"])
        self.assert_active()

    def test_target_reached_keeps_regulating_in_both_directions(self) -> None:
        self.measure(100.5)
        self.tick()
        self.advance(2.0)
        self.measure(99.5)
        self.assertEqual(self.tick()["motor_state"], "TARGET_REACHED")
        self.assertEqual(self.movement_directions(), [])
        self.assert_active()

        self.advance(2.0)
        self.measure(98.0)
        self.tick()
        self.advance(2.0)
        self.measure(102.0)
        self.tick()
        self.assertEqual(self.movement_directions(), ["FORWARD", "REVERSE"])
        self.assert_active()

    def test_missing_initial_measurement_waits_without_clearing_selection(self) -> None:
        self.assertEqual(self.tick()["motor_state"], "WAITING")
        self.assertEqual(self.movement_directions(), [])
        self.assert_active()
        self.measure(90.0)
        self.assertEqual(self.tick()["motor_state"], "RUNNING")

    def test_same_measurement_does_not_trigger_repeated_steps(self) -> None:
        self.measure(90.0)
        self.tick()
        self.advance(2.0)
        self.assertEqual(self.tick()["motor_state"], "WAITING")
        self.assertEqual(self.movement_directions(), ["FORWARD"])
        self.advance(0.1)
        self.measure(90.0)
        self.assertEqual(self.tick()["motor_state"], "RUNNING")
        self.assertEqual(self.movement_directions(), ["FORWARD", "FORWARD"])

    def test_other_register_reading_does_not_resume_stale_active_register(self) -> None:
        self.measure(90.0)
        self.tick()
        self.advance(6.0)
        self.measure(110.0, self.other_register)
        self.assertEqual(self.tick()["motor_state"], "WAITING")
        self.assertEqual(self.movement_directions(), ["FORWARD"])
        self.assert_active()

    def test_manual_stop_during_outage_prevents_automatic_resume(self) -> None:
        self.measure(90.0)
        self.tick()
        self.advance(6.0)
        self.tick()
        self.state.clear_active_control()
        self.measure(90.0)
        self.assertEqual(self.tick()["motor_state"], "IDLE")
        self.assertIsNone(self.state.get_active_control_context())
        self.assertEqual(self.movement_directions(), ["FORWARD"])

    def test_configuration_refresh_preserves_selection_during_outage(self) -> None:
        self.measure(90.0)
        self.tick()
        self.advance(6.0)
        self.tick()
        with tempfile.TemporaryDirectory() as directory:
            store = RegisterControlStore(Path(directory))
            store.set_control(1, 10, 100.0, 1.0, True)
            store.prune_missing({(1, 10), (1, 11)})
            self.state.apply_configuration(
                [self.transformer], self.transformer, [self.meter],
                {1: [replace(self.register, targetValue=100.0, thresholdValue=1.0),
                     self.other_register]},
                store.controls, store.active_key,
            )
        self.assertEqual(self.tick()["motor_state"], "WAITING")
        self.assert_active()
        self.measure(90.0)
        self.assertEqual(self.tick()["motor_state"], "RUNNING")

    def test_application_restart_still_requires_manual_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RegisterControlStore(Path(directory))
            store.set_control(1, 10, 100.0, 1.0, True)
            restored = RegisterControlStore(Path(directory))
        self.assertIsNone(restored.active_key)
        self.assertEqual(restored.controls[(1, 10)].targetValue, 100.0)

    def test_missing_configuration_keeps_selection_and_resumes_on_return(self) -> None:
        self.measure(90.0)
        self.tick()
        with tempfile.TemporaryDirectory() as directory:
            store = RegisterControlStore(Path(directory))
            store.set_control(1, 10, 100.0, 1.0, True)
            store.set_control(1, 11, 50.0, 1.0, False)
            for _ in range(3):
                self.advance(6.0)
                store.prune_missing(set())
                self.state.apply_configuration(
                    [self.transformer], self.transformer, [], {},
                    store.controls, store.active_key,
                )
                snapshot = self.tick()
                self.assertEqual(snapshot["motor_state"], "WAITING")
                self.assertEqual(snapshot["active_control_key"], (1, 10))
                self.assertEqual(store.active_key, (1, 10))
                self.assertIn("niedostepny", snapshot["motor_message"])
            self.assertEqual(set(store.controls), {(1, 10)})
            self.assertEqual(self.movement_directions(), ["FORWARD"])

            store.prune_missing({(1, 10)})
            control = store.controls[(1, 10)]
            self.state.apply_configuration(
                [self.transformer], self.transformer, [self.meter],
                {1: [replace(self.register, targetValue=control.targetValue,
                             thresholdValue=control.thresholdValue)]},
                store.controls, store.active_key,
            )
            # Returning configuration alone must not trigger movement.
            self.assertEqual(self.tick()["motor_state"], "WAITING")
            self.assertEqual(self.movement_directions(), ["FORWARD"])
            self.measure(110.0)
            self.assertEqual(self.tick()["motor_state"], "RUNNING")
            self.assertEqual(self.movement_directions(), ["FORWARD", "REVERSE"])
            self.assert_active()

    def test_manual_stop_while_register_missing_survives_configuration_return(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RegisterControlStore(Path(directory))
            store.set_control(1, 10, 100.0, 1.0, True)
            store.prune_missing(set())
            self.state.apply_configuration(
                [self.transformer], self.transformer, [], {},
                store.controls, store.active_key,
            )
            self.assertEqual(self.tick()["motor_state"], "WAITING")
            store.clear_active()
            self.state.clear_active_control()
            store.prune_missing({(1, 10)})
            self.state.apply_configuration(
                [self.transformer], self.transformer, [self.meter],
                {1: [replace(self.register, targetValue=100.0, thresholdValue=1.0)]},
                store.controls, store.active_key,
            )
            self.measure(90.0)
            self.assertEqual(self.tick()["motor_state"], "IDLE")
            self.assertFalse(self.state.has_active_control())
            self.assertEqual(self.movement_directions(), [])


if __name__ == "__main__":
    unittest.main()
