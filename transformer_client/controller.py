from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

from transformer_client.backend import BackendClient, BackendError
from transformer_client.config import load_client_config, save_client_config
from transformer_client.control import MotorControlError, MotorControlLoop, RegisterControlStore
from transformer_client.logging_utils import setup_logging
from transformer_client.metrics_ws import MetricsConnectionSettings, MetricsPublisher, build_metrics_ws_url
from transformer_client.models import AuthResponse, TransformerDto
from transformer_client.polling import PollingSupervisor
from transformer_client.sms import JustSendSmsClient, SmsSendError
from transformer_client.state import ApplicationState


class TargetExceededSmsMonitor:
    def __init__(
        self,
        state: ApplicationState,
        get_config_copy,
        send_callback,
    ) -> None:
        self.state = state
        self.get_config_copy = get_config_copy
        self.send_callback = send_callback
        self.logger = logging.getLogger("transformer_client.sms_monitor")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_key: tuple[int, int] | None = None
        self._was_above_limit = False
        self._last_sent_at_by_key: dict[tuple[int, int], float] = {}
        self._threshold_above_by_key: dict[tuple[int, int], bool] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sms-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop_event.wait(0.5):
            config = self.get_config_copy()
            if not config.smsEnabled or not config.smsApiKey.strip() or not config.smsPhoneNumbers:
                self._last_key = None
                self._was_above_limit = False
                self._threshold_above_by_key.clear()
                continue

            context = self.state.get_active_control_context()
            snapshot = self.state.snapshot()
            transformer = snapshot["selected_transformer"]
            transformer_name = transformer.name if transformer is not None else "-"
            self._check_threshold_alerts(snapshot["rows"], transformer_name, config)
            if context is None or context.current_value is None or context.target_value is None:
                self._last_key = None
                self._was_above_limit = False
                continue

            key = (context.meter_id, context.register_id)
            if self._last_key != key:
                self._last_key = key
                self._was_above_limit = False

            threshold = abs(context.threshold_value) if context.threshold_value is not None else 0.0
            delta = context.current_value - context.target_value
            if delta > 0:
                if not self._was_above_limit:
                    now = time.monotonic()
                    cooldown_seconds = max(config.smsAlertCooldownMs, 0) / 1000.0
                    last_sent_at = self._last_sent_at_by_key.get(key, 0.0)
                    if now - last_sent_at >= cooldown_seconds:
                        unit = context.unit or ""
                        unit_suffix = f" {unit}" if unit else ""
                        message = (
                            f"Przekroczenie targetu. Transformer: {transformer_name}. "
                            f"Rejestr: {context.meter_name}/{context.register_name}. "
                            f"Pomiar: {context.current_value:.2f}{unit_suffix}. "
                            f"Target: {context.target_value:.2f}{unit_suffix}. "
                            f"Threshold: {threshold:.2f}{unit_suffix}. "
                            f"Przekroczenie ponad target: {delta:.2f}{unit_suffix}."
                        )
                        try:
                            self.send_callback(message)
                            self._last_sent_at_by_key[key] = now
                            self.logger.info(
                                "Target exceeded SMS sent meter=%s register=%s live=%.4f target=%.4f threshold=%.4f delta=%.4f",
                                context.meter_id,
                                context.register_id,
                                context.current_value,
                                context.target_value,
                                threshold,
                                delta,
                            )
                        except Exception as exc:
                            self.logger.error("Target exceeded SMS failed: %s", exc)
                self._was_above_limit = True
            else:
                self._was_above_limit = False

    def _check_threshold_alerts(self, rows, transformer_name: str, config) -> None:
        active_keys: set[tuple[int, int]] = set()
        for row in rows:
            key = (row.meter_id, row.register_id)
            threshold_value = row.sms_alert_threshold_value
            if threshold_value is None or row.value is None:
                self._threshold_above_by_key.pop(key, None)
                continue

            active_keys.add(key)
            delta = row.value - threshold_value
            if delta > 0:
                if not self._threshold_above_by_key.get(key, False):
                    now = time.monotonic()
                    cooldown_seconds = max(config.smsAlertCooldownMs, 0) / 1000.0
                    last_sent_at = self._last_sent_at_by_key.get(key, 0.0)
                    if now - last_sent_at >= cooldown_seconds:
                        unit_suffix = f" {row.unit}" if row.unit else ""
                        message = (
                            f"Przekroczenie progu SMS. Transformer: {transformer_name}. "
                            f"Rejestr: {row.meter_name}/{row.register_name}. "
                            f"Pomiar: {row.value:.2f}{unit_suffix}. "
                            f"Prog SMS: {threshold_value:.2f}{unit_suffix}. "
                            f"Przekroczenie: {delta:.2f}{unit_suffix}."
                        )
                        try:
                            self.send_callback(message)
                            self._last_sent_at_by_key[key] = now
                            self.logger.info(
                                "Threshold SMS sent meter=%s register=%s live=%.4f threshold=%.4f delta=%.4f",
                                row.meter_id,
                                row.register_id,
                                row.value,
                                threshold_value,
                                delta,
                            )
                        except Exception as exc:
                            self.logger.error("Threshold SMS failed: %s", exc)
                self._threshold_above_by_key[key] = True
            else:
                self._threshold_above_by_key[key] = False

        stale_keys = set(self._threshold_above_by_key) - active_keys
        for key in stale_keys:
            self._threshold_above_by_key.pop(key, None)


class LiveClientController:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.log_path = setup_logging(workdir)
        self.logger = logging.getLogger("transformer_client.controller")
        self.config = load_client_config(workdir)
        self.backend = BackendClient(self.config.backendUrl)
        self.state = ApplicationState()
        self.control_store = RegisterControlStore(workdir)
        self.polling = PollingSupervisor(self.state)
        self.motor_control = MotorControlLoop(self.state, self.config, self.clear_active_register_control)
        self.sms_client = JustSendSmsClient()
        self.sms_monitor = TargetExceededSmsMonitor(
            self.state,
            self._get_config_copy,
            self.send_sms_message,
        )
        self.metrics_publisher = MetricsPublisher(
            self.state,
            self._get_config_copy,
            self._current_metrics_settings,
            self.backend.refresh_access_token,
        )
        self._refresh_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logged_in = False
        self.logger.info("Controller started. log_file=%s backend=%s", self.log_path, self.config.backendUrl)
        self.motor_control.start()
        self.sms_monitor.start()
        self.metrics_publisher.start()

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    def set_backend_url(self, backend_url: str) -> None:
        self.config.backendUrl = backend_url.strip()
        self.backend.set_base_url(self.config.backendUrl)
        save_client_config(self.config, self.workdir)
        self.motor_control.update_config(self.config)
        self.logger.info("Backend URL updated to %s", self.config.backendUrl)

    def login(self, email: str, password: str, remember_credentials: bool) -> AuthResponse:
        self.config.email = email.strip()
        self.config.rememberCredentials = remember_credentials
        self.config.password = password if remember_credentials else ""
        self.set_backend_url(self.config.backendUrl)

        self.logger.info("Login attempt email=%s remember_credentials=%s", email.strip(), remember_credentials)
        auth = self.backend.login(email.strip(), password)
        self._logged_in = True
        self.logger.info("Login success role=%s user_id=%s", auth.role, auth.id)
        save_client_config(self.config, self.workdir)
        self.refresh_configuration()
        self._ensure_refresh_thread()
        return auth

    def refresh_configuration(self) -> TransformerDto:
        with self._refresh_lock:
            transformers = self.backend.get_transformers()
            if not transformers:
                raise BackendError("No transformers returned by backend.")

            selected = self._choose_transformer(transformers)
            meters = [meter for meter in self.backend.get_meters(selected.id) if meter.enabled]
            registers_by_meter = {
                meter.id: [register for register in self.backend.get_registers(meter.id) if register.enabled]
                for meter in meters
            }
            valid_keys = {
                (meter.id, register.id)
                for meter in meters
                for register in registers_by_meter.get(meter.id, [])
            }
            self.control_store.prune_missing(valid_keys)
            registers_by_meter = {
                meter_id: [self._apply_control_override(register) for register in registers]
                for meter_id, registers in registers_by_meter.items()
            }

            self.config.transformerId = selected.id
            save_client_config(self.config, self.workdir)
            self.motor_control.update_config(self.config)
            self.state.apply_configuration(
                transformers,
                selected,
                meters,
                registers_by_meter,
                self.control_store.controls,
                self.control_store.active_key,
            )
            self.polling.reconcile(meters, registers_by_meter, self.config)
            register_count = sum(len(items) for items in registers_by_meter.values())
            self.logger.info(
                "Configuration refreshed transformer=%s meters=%s registers=%s active_control=%s",
                selected.id,
                len(meters),
                register_count,
                self.control_store.active_key,
            )
            return selected

    def set_register_control(
        self,
        meter_id: int,
        register_id: int,
        target_value: float | None,
        threshold_value: float | None,
        activate: bool,
    ) -> None:
        if activate and target_value is None:
            raise MotorControlError("Przed aktywacja ustaw wartosc docelowa i kliknij Apply.")
        if activate and self.control_store.active_key is not None and self.control_store.active_key != (meter_id, register_id):
            raise MotorControlError("Aktywny moze byc tylko jeden rejestr. Najpierw zatrzymaj obecny.")
        self.control_store.set_control(meter_id, register_id, target_value, threshold_value, activate)
        self.state.set_register_control(meter_id, register_id, target_value, threshold_value, activate)
        self.logger.info(
            "Register control updated meter=%s register=%s target=%s threshold=%s active=%s",
            meter_id,
            register_id,
            target_value,
            threshold_value,
            activate,
        )

    def clear_active_register_control(self) -> None:
        self.control_store.clear_active()
        self.state.clear_active_control()
        self.logger.info("Active register control cleared")

    def set_register_sms_alert_threshold(
        self,
        meter_id: int,
        register_id: int,
        sms_alert_threshold_value: float | None,
    ) -> None:
        self.control_store.set_sms_alert_threshold(meter_id, register_id, sms_alert_threshold_value)
        self.state.set_register_sms_alert_threshold(meter_id, register_id, sms_alert_threshold_value)
        self.logger.info(
            "Register SMS threshold updated meter=%s register=%s sms_threshold=%s",
            meter_id,
            register_id,
            sms_alert_threshold_value,
        )

    def update_sms_settings(
        self,
        enabled: bool,
        phone_numbers: list[str],
    ) -> None:
        self.config.smsEnabled = enabled
        self.config.smsPhoneNumbers = [item for item in phone_numbers if item]
        save_client_config(self.config, self.workdir)
        self.logger.info(
            "SMS settings updated enabled=%s phones=%s sender=%s variant=%s",
            enabled,
            len(self.config.smsPhoneNumbers),
            self.config.smsSender,
            self.config.smsBulkVariant,
        )

    def send_test_sms(self) -> str:
        snapshot = self.state.snapshot()
        transformer = snapshot["selected_transformer"]
        transformer_name = transformer.name if transformer is not None else "-"
        message = (
            f"Test SMS z Transformer Client. Transformer={transformer_name}."
        )
        result = self.send_sms_message(message)
        self.logger.info("Test SMS requested result=%s", result)
        return result

    def send_sms_message(self, message: str) -> str:
        return self.sms_client.send_message(
            self.config.smsApiKey,
            self.config.smsSender,
            list(self.config.smsPhoneNumbers),
            message,
            self.config.smsBulkVariant,
        )

    def shutdown(self) -> None:
        self.logger.info("Controller shutdown requested")
        self._stop_event.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=1.0)
        self.polling.shutdown()
        self.motor_control.stop()
        self.sms_monitor.stop()
        self.metrics_publisher.stop()
        self.logger.info("Controller shutdown complete")

    def _choose_transformer(self, transformers: list[TransformerDto]) -> TransformerDto:
        if self.config.transformerId:
            for transformer in transformers:
                if transformer.id == self.config.transformerId:
                    return transformer
        return transformers[0]

    def _ensure_refresh_thread(self) -> None:
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return
        self._stop_event.clear()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
            name="config-refresh",
        )
        self._refresh_thread.start()

    def _refresh_loop(self) -> None:
        interval = max(self.config.configRefreshMs, 250) / 1000.0
        while not self._stop_event.wait(interval):
            try:
                self.refresh_configuration()
                self.state.set_backend_error(None)
            except Exception as exc:
                self.logger.exception("Configuration refresh failed: %s", exc)
                self.state.set_backend_error(str(exc))
            interval = max(self.config.configRefreshMs, 250) / 1000.0

    def _apply_control_override(self, register):
        control = self.control_store.controls.get((register.meterId, register.id))
        if control is None:
            return register
        return replace(
            register,
            targetValue=control.targetValue,
            thresholdValue=control.thresholdValue,
        )

    def _get_config_copy(self):
        return replace(self.config)

    def _current_metrics_settings(self) -> MetricsConnectionSettings | None:
        access_token = self.backend.tokens.access_token
        transformer_id = self.config.transformerId
        if not self._logged_in or not access_token or not transformer_id:
            return None
        ws_url = build_metrics_ws_url(self.config.backendUrl, transformer_id, access_token)
        return MetricsConnectionSettings(
            ws_url=ws_url,
            transformer_id=transformer_id,
            access_token=access_token,
        )
