from __future__ import annotations

import struct
import time
from dataclasses import dataclass

from transformer_client.models import MeterDto, RegisterDto

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - depends on local environment
    serial = None

    class SerialException(Exception):
        pass


class ModbusError(Exception):
    pass


class ModbusTransportError(ModbusError):
    pass


class UnsupportedRegisterError(ModbusError):
    pass


@dataclass(frozen=True, slots=True)
class SerialPortConfig:
    port_name: str
    baud_rate: int
    data_bits: int
    parity: str
    stop_bits: int


class SerialModbusClient:
    def __init__(
        self,
        port_config: SerialPortConfig,
        *,
        timeout_ms: int,
        retries: int,
        discard_delay_ms: int,
    ) -> None:
        self.port_config = port_config
        self.timeout_ms = timeout_ms
        self.retries = retries
        self.discard_delay_ms = discard_delay_ms
        self._serial = None

    def open(self) -> None:
        if serial is None:
            raise ModbusTransportError("Missing dependency: install pyserial to use Modbus RTU.")
        try:
            self._serial = serial.Serial(
                port=self.port_config.port_name,
                baudrate=self.port_config.baud_rate,
                bytesize=self._map_data_bits(self.port_config.data_bits),
                parity=self._map_parity(self.port_config.parity),
                stopbits=self._map_stop_bits(self.port_config.stop_bits),
                timeout=self.timeout_ms / 1000.0,
            )
        except SerialException as exc:
            raise ModbusTransportError(str(exc)) from exc

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except SerialException:
                pass
            finally:
                self._serial = None

    def read_value(self, meter: MeterDto, register: RegisterDto) -> float:
        last_error: Exception | None = None
        attempts = self.retries + 1
        for _ in range(attempts):
            try:
                raw_value = self._read_once(meter, register)
                scale = register.scale if register.scale is not None else 1.0
                return float(raw_value) * scale
            except ModbusTransportError as exc:
                last_error = exc
                self._reset_line()
        if last_error is None:
            raise ModbusTransportError("Modbus read failed.")
        raise last_error

    def _read_once(self, meter: MeterDto, register: RegisterDto) -> float:
        if self._serial is None:
            raise ModbusTransportError("Serial port is not open.")

        function_code = self._map_register_type(register.registerType)
        offset = normalize_address(register.address)
        quantity = register.length if register.length > 0 else expected_register_length(register.dataType)
        request_payload = bytes(
            [
                meter.slaveId & 0xFF,
                function_code & 0xFF,
                (offset >> 8) & 0xFF,
                offset & 0xFF,
                (quantity >> 8) & 0xFF,
                quantity & 0xFF,
            ]
        )
        frame = request_payload + crc16(request_payload)

        try:
            self._reset_line()
            self._serial.write(frame)
            self._serial.flush()
            header = self._read_exact(3)
        except SerialException as exc:
            raise ModbusTransportError(str(exc)) from exc

        slave_id, response_function, third = header
        if response_function & 0x80:
            trailer = self._read_exact(2)
            response = header + trailer
            self._validate_crc(response)
            raise ModbusError(f"Modbus exception code {third} from slave {slave_id}.")

        byte_count = third
        payload = self._read_exact(byte_count + 2)
        response = header + payload
        self._validate_crc(response)
        data = payload[:-2]

        if function_code == 1:
            if not data:
                raise ModbusError("Empty coil response.")
            return float(1 if data[0] & 0x01 else 0)
        return decode_register_bytes(register, meter.byteOrder, data)

    def _reset_line(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except SerialException as exc:
            raise ModbusTransportError(str(exc)) from exc
        if self.discard_delay_ms > 0:
            time.sleep(self.discard_delay_ms / 1000.0)

    def _read_exact(self, size: int) -> bytes:
        if self._serial is None:
            raise ModbusTransportError("Serial port is not open.")
        chunks = bytearray()
        while len(chunks) < size:
            try:
                fragment = self._serial.read(size - len(chunks))
            except SerialException as exc:
                raise ModbusTransportError(str(exc)) from exc
            if not fragment:
                raise ModbusTransportError("Modbus timeout.")
            chunks.extend(fragment)
        return bytes(chunks)

    @staticmethod
    def _map_stop_bits(stop_bits: int) -> float:
        if serial is None:
            return 2 if stop_bits == 2 else 1
        return serial.STOPBITS_TWO if stop_bits == 2 else serial.STOPBITS_ONE

    @staticmethod
    def _map_parity(parity: str) -> str:
        if serial is None:
            return "N"
        normalized = parity.upper()
        if normalized == "EVEN":
            return serial.PARITY_EVEN
        if normalized == "ODD":
            return serial.PARITY_ODD
        return serial.PARITY_NONE

    @staticmethod
    def _map_data_bits(data_bits: int) -> int:
        if serial is None:
            return data_bits
        mapping = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS,
        }
        return mapping.get(data_bits, serial.EIGHTBITS)

    @staticmethod
    def _map_register_type(register_type: str) -> int:
        normalized = register_type.upper()
        if normalized == "COIL":
            return 1
        if normalized == "INPUT":
            return 4
        return 3

    @staticmethod
    def _validate_crc(frame: bytes) -> None:
        expected = crc16(frame[:-2])
        if frame[-2:] != expected:
            raise ModbusTransportError("Invalid Modbus CRC.")


def normalize_address(address: int) -> int:
    if address >= 40001:
        return address - 40001
    if address >= 30001:
        return address - 30001
    return address


def expected_register_length(data_type: str) -> int:
    normalized = data_type.upper()
    if normalized in {"INT32", "FLOAT32"}:
        return 2
    return 1


def decode_register_bytes(register: RegisterDto, byte_order: str, data: bytes) -> float:
    data_type = register.dataType.upper()
    if data_type == "INT16":
        if len(data) < 2:
            raise UnsupportedRegisterError("INT16 requires 2 bytes.")
        return float(struct.unpack(">h", data[:2])[0])

    if data_type == "INT32":
        chunk = _prepare_32bit_payload(data, byte_order)
        return float(struct.unpack(">i", chunk)[0])

    if data_type == "FLOAT32":
        chunk = _prepare_32bit_payload(data, byte_order)
        return float(struct.unpack(">f", chunk)[0])

    if len(data) < 2:
        raise UnsupportedRegisterError("Fallback INT16 requires 2 bytes.")
    return float(struct.unpack(">h", data[:2])[0])


def _prepare_32bit_payload(data: bytes, byte_order: str) -> bytes:
    if len(data) < 4:
        raise UnsupportedRegisterError("32-bit value requires 4 bytes.")
    chunk = data[:4]
    if byte_order.upper() == "LITTLE_ENDIAN":
        return chunk[2:4] + chunk[0:2]
    return chunk


def crc16(payload: bytes) -> bytes:
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            lsb = crc & 0x0001
            crc >>= 1
            if lsb:
                crc ^= 0xA001
    return struct.pack("<H", crc & 0xFFFF)
