from __future__ import annotations

import unittest
from datetime import datetime

from transformer_client.controller import TargetExceededSmsMonitor
from transformer_client.models import ClientConfig
from transformer_client.state import UiRow


def build_row(*, value: float, sms_threshold: float) -> UiRow:
    return UiRow(
        meter_id=1,
        meter_name="Meter 1",
        serial_port="COM1",
        status="CONNECTED",
        error=None,
        register_id=10,
        register_name="Register 10",
        register_type="HOLDING",
        address=100,
        data_type="FLOAT32",
        value=value,
        target_value=None,
        threshold_value=None,
        sms_alert_threshold_value=sms_threshold,
        control_active=False,
        unit="C",
        updated_at=datetime.now(),
    )


class TargetExceededSmsMonitorTests(unittest.TestCase):
    def test_threshold_change_resets_above_state_and_sends_new_sms(self) -> None:
        sent_messages: list[str] = []
        monitor = TargetExceededSmsMonitor(
            state=None,
            get_config_copy=lambda: None,
            send_callback=sent_messages.append,
        )
        config = ClientConfig(smsEnabled=True, smsApiKey="key", smsPhoneNumbers=["48123123123"], smsAlertCooldownMs=0)

        monitor._check_threshold_alerts([build_row(value=12.0, sms_threshold=10.0)], "T1", config)
        monitor._check_threshold_alerts([build_row(value=12.0, sms_threshold=11.0)], "T1", config)

        self.assertEqual(len(sent_messages), 2)
        self.assertIn("Prog SMS: 10.00 C.", sent_messages[0])
        self.assertIn("Prog SMS: 11.00 C.", sent_messages[1])

    def test_drop_below_threshold_resets_cooldown_and_allows_next_sms(self) -> None:
        sent_messages: list[str] = []
        monitor = TargetExceededSmsMonitor(
            state=None,
            get_config_copy=lambda: None,
            send_callback=sent_messages.append,
        )
        config = ClientConfig(smsEnabled=True, smsApiKey="key", smsPhoneNumbers=["48123123123"], smsAlertCooldownMs=300000)

        monitor._check_threshold_alerts([build_row(value=12.0, sms_threshold=10.0)], "T1", config)
        monitor._check_threshold_alerts([build_row(value=8.0, sms_threshold=10.0)], "T1", config)
        monitor._check_threshold_alerts([build_row(value=12.0, sms_threshold=10.0)], "T1", config)

        self.assertEqual(len(sent_messages), 2)


if __name__ == "__main__":
    unittest.main()
