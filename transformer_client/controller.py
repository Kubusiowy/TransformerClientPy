from __future__ import annotations

import threading
from pathlib import Path

from transformer_client.backend import BackendClient, BackendError
from transformer_client.config import load_client_config, save_client_config
from transformer_client.models import AuthResponse, TransformerDto
from transformer_client.polling import PollingSupervisor
from transformer_client.state import ApplicationState


class LiveClientController:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.config = load_client_config(workdir)
        self.backend = BackendClient(self.config.backendUrl)
        self.state = ApplicationState()
        self.polling = PollingSupervisor(self.state)
        self._refresh_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logged_in = False

    @property
    def logged_in(self) -> bool:
        return self._logged_in

    def set_backend_url(self, backend_url: str) -> None:
        self.config.backendUrl = backend_url.strip()
        self.backend.set_base_url(self.config.backendUrl)
        save_client_config(self.config, self.workdir)

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

            self.config.transformerId = selected.id
            save_client_config(self.config, self.workdir)
            self.state.apply_configuration(transformers, selected, meters, registers_by_meter)
            self.polling.reconcile(meters, registers_by_meter, self.config)
            return selected

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=1.0)
        self.polling.shutdown()

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
