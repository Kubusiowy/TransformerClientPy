from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from transformer_client.backend import BackendClient, BackendError
from transformer_client.config import load_client_config, save_client_config
from transformer_client.control import MotorControlError, MotorControlLoop, RegisterControlStore
from transformer_client.models import AuthResponse, TransformerDto
from transformer_client.polling import PollingSupervisor
from transformer_client.state import ApplicationState


class LiveClientController:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.config = load_client_config(workdir)
        self.backend = BackendClient(self.config.backendUrl)
        self.state = ApplicationState()
        self.control_store = RegisterControlStore(workdir)
        self.polling = PollingSupervisor(self.state)
        self.motor_control = MotorControlLoop(self.state, self.config)
        self._refresh_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logged_in = False
        self.motor_control.start()

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    def set_backend_url(self, backend_url: str) -> None:
        self.config.backendUrl = backend_url.strip()
        self.backend.set_base_url(self.config.backendUrl)
        save_client_config(self.config, self.workdir)
        self.motor_control.update_config(self.config)

    def login(self, email: str, password: str, remember_credentials: bool) -> AuthResponse:
        self.config.email = email.strip()
        self.config.rememberCredentials = remember_credentials
        self.config.password = password if remember_credentials else ""
        self.set_backend_url(self.config.backendUrl)

        auth = self.backend.login(email.strip(), password)
        self._logged_in = True
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

    def clear_active_register_control(self) -> None:
        self.control_store.clear_active()
        self.state.clear_active_control()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=1.0)
        self.polling.shutdown()
        self.motor_control.stop()

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
