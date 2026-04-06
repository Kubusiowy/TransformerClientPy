from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlencode, urlparse, urlunparse

from transformer_client.models import ClientConfig
from transformer_client.state import ApplicationState


class MetricsWebSocketError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MetricsConnectionSettings:
    ws_url: str
    transformer_id: str
    access_token: str


class RawWebSocketClient:
    def __init__(self) -> None:
        self._socket: socket.socket | ssl.SSLSocket | None = None
        self._lock = threading.Lock()
        self._connected_url: str | None = None

    def connect(self, ws_url: str) -> None:
        parsed = urlparse(ws_url)
        if parsed.scheme not in {"ws", "wss"}:
            raise MetricsWebSocketError(f"Unsupported websocket scheme: {parsed.scheme}")

        host = parsed.hostname
        if not host:
            raise MetricsWebSocketError("Missing websocket host.")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=5)
        raw_sock.settimeout(5)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            sock: socket.socket | ssl.SSLSocket = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            sock = raw_sock

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._read_http_response(sock)
        self._validate_handshake(response, key)

        self.close()
        with self._lock:
            self._socket = sock
            self._connected_url = ws_url

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        frame = bytes(header) + mask + masked
        with self._lock:
            if self._socket is None:
                raise MetricsWebSocketError("WebSocket is not connected.")
            try:
                self._socket.sendall(frame)
            except OSError as exc:
                self.close()
                raise MetricsWebSocketError(str(exc)) from exc

    def close(self) -> None:
        sock = self._socket
        self._socket = None
        self._connected_url = None
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def read_text_frames(self, timeout_seconds: float) -> list[str]:
        with self._lock:
            sock = self._socket
        if sock is None:
            raise MetricsWebSocketError("WebSocket is not connected.")

        frames: list[str] = []
        previous_timeout = sock.gettimeout()
        try:
            sock.settimeout(timeout_seconds)
            while True:
                opcode, payload = self._recv_frame(sock)
                if opcode == "timeout":
                    break
                if opcode == 0x1:
                    frames.append(payload.decode("utf-8", errors="replace"))
                    sock.settimeout(0.001)
                    continue
                if opcode == 0x8:
                    self.close()
                    raise MetricsWebSocketError("WebSocket closed by server.")
                if opcode == 0x9:
                    self._send_control_frame(0xA, payload)
                    sock.settimeout(0.001)
                    continue
                sock.settimeout(0.001)
        except OSError as exc:
            self.close()
            raise MetricsWebSocketError(str(exc)) from exc
        finally:
            try:
                sock.settimeout(previous_timeout)
            except OSError:
                pass
        return frames

    @staticmethod
    def _read_http_response(sock: socket.socket | ssl.SSLSocket) -> str:
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
        return buffer.decode("latin1", errors="replace")

    @staticmethod
    def _validate_handshake(response: str, key: str) -> None:
        if "101 Switching Protocols" not in response:
            raise MetricsWebSocketError(f"WebSocket handshake failed: {response.strip()}")
        accept_line = None
        for line in response.split("\r\n"):
            if line.lower().startswith("sec-websocket-accept:"):
                accept_line = line.split(":", 1)[1].strip()
                break
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if accept_line != expected:
            raise MetricsWebSocketError("Invalid websocket handshake accept header.")

    @staticmethod
    def _recv_frame(sock: socket.socket | ssl.SSLSocket) -> tuple[int | str, bytes]:
        try:
            header = sock.recv(2)
        except socket.timeout:
            return ("timeout", b"")
        if not header:
            return (0x8, b"")
        first, second = header
        opcode = first & 0x0F
        masked = (second >> 7) & 1
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", RawWebSocketClient._recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", RawWebSocketClient._recv_exact(sock, 8))[0]
        mask = RawWebSocketClient._recv_exact(sock, 4) if masked else b""
        payload = RawWebSocketClient._recv_exact(sock, length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return (opcode, payload)

    @staticmethod
    def _recv_exact(sock: socket.socket | ssl.SSLSocket, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = sock.recv(size - len(chunks))
            if not chunk:
                raise MetricsWebSocketError("Unexpected EOF from websocket.")
            chunks.extend(chunk)
        return bytes(chunks)

    def _send_control_frame(self, opcode: int, payload: bytes = b"") -> None:
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        frame = bytes(header) + mask + masked
        with self._lock:
            if self._socket is None:
                return
            self._socket.sendall(frame)


class MetricsPublisher:
    def __init__(
        self,
        state: ApplicationState,
        config_supplier: Callable[[], ClientConfig],
        settings_supplier: Callable[[], MetricsConnectionSettings | None],
        refresh_access_token: Callable[[], str],
    ) -> None:
        self.state = state
        self.config_supplier = config_supplier
        self.settings_supplier = settings_supplier
        self.refresh_access_token = refresh_access_token
        self._client = RawWebSocketClient()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sent_updates: dict[str, str] = {}
        self._last_settings: MetricsConnectionSettings | None = None
        self._reconnect_delay_seconds = 1.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="metrics-ws")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._client.close()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            config = self.config_supplier()
            interval = max(config.metricsPublishMs, 100) / 1000.0
            if self._stop_event.wait(interval):
                break

            settings = self.settings_supplier()
            if settings is None:
                self._client.close()
                self._last_settings = None
                self._last_sent_updates = {}
                self.state.set_metrics_state("DISCONNECTED", None)
                continue

            try:
                if settings != self._last_settings:
                    self._client.close()
                    self._client.connect(settings.ws_url)
                    self._last_settings = settings
                    self._last_sent_updates = {}
                    self._reconnect_delay_seconds = 1.0
                    self.state.set_metrics_state("CONNECTED", None)

                for message in self._build_metric_messages():
                    self._client.send_text(json.dumps(message, ensure_ascii=True, separators=(",", ":")))

                for text in self._client.read_text_frames(0.01):
                    self._handle_incoming_text(text)
                self.state.set_metrics_state("CONNECTED", None)
            except Exception as exc:
                self._client.close()
                self._last_settings = None
                self._last_sent_updates = {}
                self.state.set_metrics_state("ERROR", str(exc))
                self._try_refresh_access_token()
                if self._stop_event.wait(self._reconnect_delay_seconds):
                    break
                self._reconnect_delay_seconds = min(self._next_reconnect_delay(), 10.0)

    def _build_metric_messages(self) -> list[dict]:
        result: list[dict] = []
        for item in self.state.metrics_messages():
            timestamp = item["timestamp"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            signature = f"{item['value']}|{timestamp}|{item['unit']}|{item['label']}"
            if self._last_sent_updates.get(item["metricKey"]) == signature:
                continue
            self._last_sent_updates[item["metricKey"]] = signature
            result.append(
                {
                    "key": item["metricKey"],
                    "value": item["value"],
                    "timestamp": timestamp,
                    "unit": item["unit"],
                    "label": item["label"],
                }
            )
        return result

    def _handle_incoming_text(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            self.state.merge_metric_point(payload)

    def _try_refresh_access_token(self) -> None:
        try:
            self.refresh_access_token()
        except Exception:
            pass

    def _next_reconnect_delay(self) -> float:
        if self._reconnect_delay_seconds < 1.5:
            return 2.0
        if self._reconnect_delay_seconds < 2.5:
            return 5.0
        return 10.0

def build_metrics_ws_url(base_url: str, transformer_id: str, access_token: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise MetricsWebSocketError(f"Unsupported backend URL scheme: {parsed.scheme}")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"/ws/transformers/{transformer_id}/metrics"
    query = urlencode({"token": access_token})
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))
