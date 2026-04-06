from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from transformer_client.models import ClientConfig, RegisterControl
from transformer_client.state import ApplicationState


CONTROL_FILE_NAME = "register-control.json"


class MotorControlError(Exception):
    pass


class RegisterControlStore:
    def __init__(self, workdir: Path) -> None:
        self.path = workdir / CONTROL_FILE_NAME
        self.controls: dict[tuple[int, int], RegisterControl] = {}
        self.active_key: tuple[int, int] | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.controls = {}
            self.active_key = None
            return

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        controls: dict[tuple[int, int], RegisterControl] = {}
        for item in payload.get("registers", []):
            control = RegisterControl(
                meterId=int(item["meterId"]),
                registerId=int(item["registerId"]),
                targetValue=float(item["targetValue"]) if item.get("targetValue") is not None else None,
                thresholdValue=float(item["thresholdValue"]) if item.get("thresholdValue") is not None else None,
            )
            controls[control.key] = control

        self.controls = controls
        # Active motor control is intentionally runtime-only.
        # After application restart, no register should start driving automatically.
        self.active_key = None

    def save(self) -> None:
        payload = {
            "activeRegister": None,
            "registers": [asdict(control) for control in sorted(self.controls.values(), key=lambda item: item.key)],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def set_control(
        self,
        meter_id: int,
        register_id: int,
        target_value: float | None,
        threshold_value: float | None,
        activate: bool,
    ) -> None:
        key = (meter_id, register_id)
        if activate and target_value is None:
            raise MotorControlError("Przed aktywacja ustaw targetValue i kliknij Apply.")
        self.controls[key] = RegisterControl(
            meterId=meter_id,
            registerId=register_id,
            targetValue=target_value,
            thresholdValue=threshold_value,
        )
        if activate:
            if self.active_key is not None and self.active_key != key:
                raise MotorControlError("Aktywny moze byc tylko jeden rejestr. Najpierw go zatrzymaj.")
            self.active_key = key
        self.save()

    def clear_active(self) -> None:
        self.active_key = None
        self.save()

    def prune_missing(self, valid_keys: set[tuple[int, int]]) -> None:
        self.controls = {key: value for key, value in self.controls.items() if key in valid_keys}
        if self.active_key not in valid_keys:
            self.active_key = None
        self.save()


class CommandMotorDriver:
    def __init__(self, config: ClientConfig) -> None:
        self.config = config
        self.forward_command = config.motorForwardCommand.strip()
        self.reverse_command = config.motorReverseCommand.strip()
        self.stop_command = config.motorStopCommand.strip()
        self._last_direction = "STOPPED"

    def set_direction(self, direction: str, burst_steps: int | None = None) -> None:
        if direction == "STOPPED" and direction == self._last_direction:
            return
        command = self._command_for(direction)
        if not command:
            if direction == "STOPPED":
                self._last_direction = direction
                return
            raise MotorControlError(
                "Brak komend silnika w client-config.json. Ustaw motorForwardCommand, motorReverseCommand i motorStopCommand."
            )

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={
                **os.environ,
                "MOTOR_BURST_STEPS": str(burst_steps if burst_steps is not None else self.config.motorBurstSteps),
                "MOTOR_STEP_DELAY_SEC": str(self.config.motorStepDelaySec),
                "MOTOR_ENABLE_DELAY_SEC": str(self.config.motorEnableDelaySec),
                "MOTOR_MICROSTEP_MODE": str(self.config.motorMicrostepMode),
                "MOTOR_M0_PIN": "" if self.config.motorM0Pin is None else str(self.config.motorM0Pin),
                "MOTOR_M1_PIN": "" if self.config.motorM1Pin is None else str(self.config.motorM1Pin),
                "MOTOR_M2_PIN": "" if self.config.motorM2Pin is None else str(self.config.motorM2Pin),
            },
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "Motor command failed."
            raise MotorControlError(stderr)
        self._last_direction = "STOPPED" if direction != "STOPPED" else "STOPPED"

    def stop(self) -> None:
        self.set_direction("STOPPED")

    def _command_for(self, direction: str) -> str:
        if direction == "FORWARD":
            return self.forward_command
        if direction == "REVERSE":
            return self.reverse_command
        return self.stop_command


class MotorControlLoop:
    def __init__(
        self,
        state: ApplicationState,
        config: ClientConfig,
        clear_active_callback: Callable[[], None],
    ) -> None:
        self.state = state
        self.config = config
        self.driver = CommandMotorDriver(config)
        self.clear_active_callback = clear_active_callback
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_key: tuple[int, int] | None = None
        self._last_distance: float | None = None
        self._last_progress_monotonic: float | None = None
        self._last_sample_update: datetime | None = None
        self._next_action_monotonic: float | None = None
        self._stable_since_monotonic: float | None = None
        self._last_burst_direction: str | None = None
        self._outside_band_samples = 0
        self._runtime_direction_inverted = False

    def update_config(self, config: ClientConfig) -> None:
        self.config = config
        self.driver = CommandMotorDriver(config)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="motor-control")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        try:
            self.driver.stop()
        except Exception:
            pass

    def _run(self) -> None:
        interval = max(self.config.controlLoopIntervalMs, 100) / 1000.0
        while not self._stop_event.wait(interval):
            interval = max(self.config.controlLoopIntervalMs, 100) / 1000.0
            context = self.state.get_active_control_context()
            if context is None:
                self._reset_progress_tracking()
                self._set_motor("IDLE", "STOPPED", "Brak aktywnego rejestru.")
                continue
            if context.current_value is None:
                self._reset_progress_tracking()
                self._set_motor("WAITING", "STOPPED", "Brak aktualnej wartosci rejestru.")
                continue
            if context.target_value is None:
                self._reset_progress_tracking()
                self._set_motor("ERROR", "STOPPED", "Brak targetValue dla aktywnego rejestru.")
                continue

            key = (context.meter_id, context.register_id)
            threshold = abs(context.threshold_value) if context.threshold_value is not None else 0.0
            current_value = context.current_value
            raw_delta = context.target_value - current_value
            raw_distance = abs(raw_delta)
            desired_direction = "FORWARD" if raw_delta > 0 else "REVERSE"
            settle_seconds = max(self.config.motorSettleMs, 0) / 1000.0
            resume_threshold = threshold + max(self.config.motorProgressEpsilon * 4.0, 2.0)
            now_monotonic = time.monotonic()
            fresh_sample = self._consume_sample_update(context.last_update)

            if self._last_key != key:
                self._last_key = key
                self._last_distance = raw_distance
                self._last_progress_monotonic = time.monotonic()
                self._last_sample_update = context.last_update
                self._next_action_monotonic = None
                self._stable_since_monotonic = None
                self._last_burst_direction = None
                self._outside_band_samples = 0
                self._runtime_direction_inverted = False

            if raw_distance <= threshold:
                self._last_distance = raw_distance
                self._last_progress_monotonic = time.monotonic()
                self._outside_band_samples = 0
                if self._stable_since_monotonic is None:
                    self._stable_since_monotonic = now_monotonic
                held_for = now_monotonic - self._stable_since_monotonic
                if held_for < settle_seconds:
                    self._set_motor(
                        "WAITING",
                        "STOPPED",
                        self._format_motor_message("Wartosc w threshold, obserwuje stabilnosc", context),
                    )
                else:
                    self._set_motor(
                        "TARGET_REACHED",
                        "STOPPED",
                        self._format_motor_message("Osiagnieto target", context),
                    )
                continue

            if self._stable_since_monotonic is not None and raw_distance <= resume_threshold:
                self._outside_band_samples = 0
                self._set_motor(
                    "HOLDING",
                    "STOPPED",
                    self._format_motor_message("Lekko poza targetem, trzymam bez korekty", context),
                )
                continue

            if self._stable_since_monotonic is not None:
                if fresh_sample:
                    self._outside_band_samples += 1
                if self._outside_band_samples < 2:
                    self._set_motor(
                        "HOLDING",
                        "STOPPED",
                        self._format_motor_message("Czekam na potwierdzenie wyjscia poza zakres", context),
                    )
                    continue

            self._stable_since_monotonic = None
            self._outside_band_samples = 0

            if fresh_sample:
                if self._has_progress(raw_distance):
                    self._last_distance = raw_distance
                    self._last_progress_monotonic = time.monotonic()
                elif (
                    self._last_distance is not None
                    and self._last_burst_direction == desired_direction
                    and (raw_distance - self._last_distance) >= self.config.motorProgressEpsilon
                ):
                    self._runtime_direction_inverted = not self._runtime_direction_inverted
                    self._last_burst_direction = None
                    self._next_action_monotonic = now_monotonic + settle_seconds
                    self._set_motor(
                        "HOLDING",
                        "STOPPED",
                        self._format_motor_message("Ostatni maly krok pogorszyl blad, odwrocono kierunek", context),
                    )
                    continue

            if self._measurement_stale(context.last_update):
                self._safety_stop(
                    self._format_motor_message(
                        "Safety stop: brak swiezego pomiaru",
                        context,
                    )
                )
                continue

            if self._next_action_monotonic is not None and now_monotonic < self._next_action_monotonic:
                settle_label = f"{settle_seconds:.0f}" if settle_seconds.is_integer() else f"{settle_seconds:.1f}"
                self._set_motor(
                    "WAITING",
                    "STOPPED",
                    self._format_motor_message(f"Czekam {settle_label} s i obserwuje pomiar", context),
                )
                continue
            self._next_action_monotonic = None

            if not fresh_sample and self._last_sample_update is not None:
                self._set_motor(
                    "WAITING",
                    "STOPPED",
                    self._format_motor_message("Czekam na swiezy pomiar", context),
                )
                continue

            self._last_burst_direction = desired_direction
            self._next_action_monotonic = now_monotonic + settle_seconds
            self._set_motor(
                "RUNNING",
                self._map_direction(desired_direction),
                self._format_motor_message("Maly krok korekty", context),
                burst_steps=1,
            )

    def _has_progress(self, distance: float) -> bool:
        if self._last_distance is None:
            return True
        return (self._last_distance - distance) >= self.config.motorProgressEpsilon

    def _measurement_stale(self, last_update: datetime | None) -> bool:
        if last_update is None:
            return True
        age_seconds = (datetime.now() - last_update).total_seconds()
        timeout_seconds = max(self.config.motorNoProgressTimeoutMs, self.config.motorSettleMs + 2000, 250) / 1000.0
        return age_seconds >= timeout_seconds

    def _reset_progress_tracking(self, keep_last_key: bool = False) -> None:
        self._last_key = None if not keep_last_key else self._last_key
        self._last_distance = None
        self._last_progress_monotonic = None
        self._last_sample_update = None
        self._next_action_monotonic = None
        self._stable_since_monotonic = None
        self._last_burst_direction = None
        self._outside_band_samples = 0
        if not keep_last_key:
            self._runtime_direction_inverted = False

    def _safety_stop(self, message: str) -> None:
        self._reset_progress_tracking()
        try:
            self.driver.stop()
        except Exception:
            pass
        self.clear_active_callback()
        self.state.set_motor_state("SAFETY_STOP", "STOPPED", message)

    @staticmethod
    def _format_motor_message(prefix: str, context) -> str:
        unit = context.unit or ""
        unit_suffix = f" {unit}" if unit else ""
        return (
            f"{prefix}: {context.meter_name} / {context.register_name} | "
            f"live={context.current_value:.4f}{unit_suffix} | "
            f"target={context.target_value:.4f}{unit_suffix}"
        )

    def _map_direction(self, logical_direction: str) -> str:
        effective_inverted = self.config.motorDirectionInverted ^ self._runtime_direction_inverted
        if not effective_inverted:
            return logical_direction
        return "REVERSE" if logical_direction == "FORWARD" else "FORWARD"

    def _consume_sample_update(self, last_update: datetime | None) -> bool:
        if last_update is None:
            return False
        if self._last_sample_update is None or last_update > self._last_sample_update:
            self._last_sample_update = last_update
            return True
        return False

    def _set_motor(self, state_name: str, direction: str, message: str, burst_steps: int | None = None) -> None:
        try:
            self.driver.set_direction(direction, burst_steps=burst_steps)
            self.state.set_motor_state(state_name, direction, message)
        except Exception as exc:
            self.state.set_motor_state("ERROR", "STOPPED", str(exc))
