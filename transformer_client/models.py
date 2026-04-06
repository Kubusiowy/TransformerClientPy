from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


DEFAULT_CLIENT_CONFIG: dict[str, Any] = {
    "backendUrl": "http://194.28.222.28:8080",
    "email": "admin@admin",
    "password": "ZAQ!2wsx",
    "transformerId": "649bb8d7-6064-48ef-b062-711d6724fb9c",
    "pollIntervalMs": 100,
    "configRefreshMs": 5000,
    "reconnectDelayMs": 3000,
    "modbusTimeoutMs": 250,
    "modbusRetries": 2,
    "modbusDiscardDelayMs": 150,
    "interRegisterDelayMs": 0,
    "rememberCredentials": True,
    "controlLoopIntervalMs": 100,
    "motorNoProgressTimeoutMs": 5000,
    "motorProgressEpsilon": 0.5,
    "metricsPublishMs": 500,
    "motorBurstSteps": 1,
    "motorStepDelaySec": 0.08,
    "motorSettleMs": 3000,
    "motorDirectionInverted": True,
    "motorMicrostepMode": "FULL",
    "motorM0Pin": None,
    "motorM1Pin": None,
    "motorM2Pin": None,
    "motorEnableDelaySec": 0.002,
    "motorAverageWindow": 8,
    "motorReverseThresholdMultiplier": 1.5,
    "motorReverseSamples": 2,
    "motorForwardCommand": "",
    "motorReverseCommand": "",
    "motorStopCommand": "",
}


@dataclass(slots=True)
class ClientConfig:
    backendUrl: str = DEFAULT_CLIENT_CONFIG["backendUrl"]
    email: str = DEFAULT_CLIENT_CONFIG["email"]
    password: str = DEFAULT_CLIENT_CONFIG["password"]
    transformerId: str | None = DEFAULT_CLIENT_CONFIG["transformerId"]
    pollIntervalMs: int = DEFAULT_CLIENT_CONFIG["pollIntervalMs"]
    configRefreshMs: int = DEFAULT_CLIENT_CONFIG["configRefreshMs"]
    reconnectDelayMs: int = DEFAULT_CLIENT_CONFIG["reconnectDelayMs"]
    modbusTimeoutMs: int = DEFAULT_CLIENT_CONFIG["modbusTimeoutMs"]
    modbusRetries: int = DEFAULT_CLIENT_CONFIG["modbusRetries"]
    modbusDiscardDelayMs: int = DEFAULT_CLIENT_CONFIG["modbusDiscardDelayMs"]
    interRegisterDelayMs: int = DEFAULT_CLIENT_CONFIG["interRegisterDelayMs"]
    rememberCredentials: bool = DEFAULT_CLIENT_CONFIG["rememberCredentials"]
    controlLoopIntervalMs: int = DEFAULT_CLIENT_CONFIG["controlLoopIntervalMs"]
    motorNoProgressTimeoutMs: int = DEFAULT_CLIENT_CONFIG["motorNoProgressTimeoutMs"]
    motorProgressEpsilon: float = DEFAULT_CLIENT_CONFIG["motorProgressEpsilon"]
    metricsPublishMs: int = DEFAULT_CLIENT_CONFIG["metricsPublishMs"]
    motorBurstSteps: int = DEFAULT_CLIENT_CONFIG["motorBurstSteps"]
    motorStepDelaySec: float = DEFAULT_CLIENT_CONFIG["motorStepDelaySec"]
    motorSettleMs: int = DEFAULT_CLIENT_CONFIG["motorSettleMs"]
    motorDirectionInverted: bool = DEFAULT_CLIENT_CONFIG["motorDirectionInverted"]
    motorMicrostepMode: str = DEFAULT_CLIENT_CONFIG["motorMicrostepMode"]
    motorM0Pin: int | None = DEFAULT_CLIENT_CONFIG["motorM0Pin"]
    motorM1Pin: int | None = DEFAULT_CLIENT_CONFIG["motorM1Pin"]
    motorM2Pin: int | None = DEFAULT_CLIENT_CONFIG["motorM2Pin"]
    motorEnableDelaySec: float = DEFAULT_CLIENT_CONFIG["motorEnableDelaySec"]
    motorAverageWindow: int = DEFAULT_CLIENT_CONFIG["motorAverageWindow"]
    motorReverseThresholdMultiplier: float = DEFAULT_CLIENT_CONFIG["motorReverseThresholdMultiplier"]
    motorReverseSamples: int = DEFAULT_CLIENT_CONFIG["motorReverseSamples"]
    motorForwardCommand: str = DEFAULT_CLIENT_CONFIG["motorForwardCommand"]
    motorReverseCommand: str = DEFAULT_CLIENT_CONFIG["motorReverseCommand"]
    motorStopCommand: str = DEFAULT_CLIENT_CONFIG["motorStopCommand"]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ClientConfig":
        merged = {**DEFAULT_CLIENT_CONFIG, **payload}
        return cls(
            backendUrl=str(merged["backendUrl"]),
            email=str(merged["email"]),
            password=str(merged["password"]),
            transformerId=merged["transformerId"] or None,
            pollIntervalMs=int(merged["pollIntervalMs"]),
            configRefreshMs=int(merged["configRefreshMs"]),
            reconnectDelayMs=int(merged["reconnectDelayMs"]),
            modbusTimeoutMs=int(merged["modbusTimeoutMs"]),
            modbusRetries=int(merged["modbusRetries"]),
            modbusDiscardDelayMs=int(merged["modbusDiscardDelayMs"]),
            interRegisterDelayMs=int(merged["interRegisterDelayMs"]),
            rememberCredentials=bool(merged["rememberCredentials"]),
            controlLoopIntervalMs=int(merged["controlLoopIntervalMs"]),
            motorNoProgressTimeoutMs=int(merged["motorNoProgressTimeoutMs"]),
            motorProgressEpsilon=float(merged["motorProgressEpsilon"]),
            metricsPublishMs=int(merged["metricsPublishMs"]),
            motorBurstSteps=int(merged["motorBurstSteps"]),
            motorStepDelaySec=float(merged["motorStepDelaySec"]),
            motorSettleMs=int(merged["motorSettleMs"]),
            motorDirectionInverted=bool(merged["motorDirectionInverted"]),
            motorMicrostepMode=str(merged["motorMicrostepMode"]),
            motorM0Pin=int(merged["motorM0Pin"]) if merged.get("motorM0Pin") is not None else None,
            motorM1Pin=int(merged["motorM1Pin"]) if merged.get("motorM1Pin") is not None else None,
            motorM2Pin=int(merged["motorM2Pin"]) if merged.get("motorM2Pin") is not None else None,
            motorEnableDelaySec=float(merged["motorEnableDelaySec"]),
            motorAverageWindow=int(merged["motorAverageWindow"]),
            motorReverseThresholdMultiplier=float(merged["motorReverseThresholdMultiplier"]),
            motorReverseSamples=int(merged["motorReverseSamples"]),
            motorForwardCommand=str(merged["motorForwardCommand"]),
            motorReverseCommand=str(merged["motorReverseCommand"]),
            motorStopCommand=str(merged["motorStopCommand"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "backendUrl": self.backendUrl,
            "email": self.email,
            "password": self.password,
            "transformerId": self.transformerId,
            "pollIntervalMs": self.pollIntervalMs,
            "configRefreshMs": self.configRefreshMs,
            "reconnectDelayMs": self.reconnectDelayMs,
            "modbusTimeoutMs": self.modbusTimeoutMs,
            "modbusRetries": self.modbusRetries,
            "modbusDiscardDelayMs": self.modbusDiscardDelayMs,
            "interRegisterDelayMs": self.interRegisterDelayMs,
            "rememberCredentials": self.rememberCredentials,
            "controlLoopIntervalMs": self.controlLoopIntervalMs,
            "motorNoProgressTimeoutMs": self.motorNoProgressTimeoutMs,
            "motorProgressEpsilon": self.motorProgressEpsilon,
            "metricsPublishMs": self.metricsPublishMs,
            "motorBurstSteps": self.motorBurstSteps,
            "motorStepDelaySec": self.motorStepDelaySec,
            "motorSettleMs": self.motorSettleMs,
            "motorDirectionInverted": self.motorDirectionInverted,
            "motorMicrostepMode": self.motorMicrostepMode,
            "motorM0Pin": self.motorM0Pin,
            "motorM1Pin": self.motorM1Pin,
            "motorM2Pin": self.motorM2Pin,
            "motorEnableDelaySec": self.motorEnableDelaySec,
            "motorAverageWindow": self.motorAverageWindow,
            "motorReverseThresholdMultiplier": self.motorReverseThresholdMultiplier,
            "motorReverseSamples": self.motorReverseSamples,
            "motorForwardCommand": self.motorForwardCommand,
            "motorReverseCommand": self.motorReverseCommand,
            "motorStopCommand": self.motorStopCommand,
        }


@dataclass(frozen=True, slots=True)
class AuthResponse:
    id: str
    accessToken: str
    refreshToken: str
    role: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuthResponse":
        return cls(
            id=str(payload["id"]),
            accessToken=str(payload["accessToken"]),
            refreshToken=str(payload["refreshToken"]),
            role=str(payload["role"]),
        )


@dataclass(frozen=True, slots=True)
class RefreshResponse:
    accessToken: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RefreshResponse":
        return cls(accessToken=str(payload["accessToken"]))


@dataclass(frozen=True, slots=True)
class TransformerDto:
    id: str
    name: str
    location: str | None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TransformerDto":
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            location=payload.get("location"),
        )


@dataclass(frozen=True, slots=True)
class MeterDto:
    id: int
    name: str
    deviceCode: str
    enabled: bool
    serialPort: str
    baudRate: int
    dataBits: int
    parity: str
    stopBits: int
    slaveId: int
    byteOrder: str
    pollIntervalMs: int | None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MeterDto":
        return cls(
            id=int(payload["id"]),
            name=str(payload["name"]),
            deviceCode=str(payload["deviceCode"]),
            enabled=bool(payload["enabled"]),
            serialPort=str(payload["serialPort"]),
            baudRate=int(payload["baudRate"]),
            dataBits=int(payload["dataBits"]),
            parity=str(payload["parity"]),
            stopBits=int(payload["stopBits"]),
            slaveId=int(payload["slaveId"]),
            byteOrder=str(payload["byteOrder"]),
            pollIntervalMs=int(payload["pollIntervalMs"]) if payload.get("pollIntervalMs") else None,
        )


@dataclass(frozen=True, slots=True)
class RegisterDto:
    id: int
    meterId: int
    name: str
    registerType: str
    address: int
    length: int
    dataType: str
    scale: float | None
    targetValue: float | None
    thresholdValue: float | None
    unit: str | None
    enabled: bool
    orderIndex: int | None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RegisterDto":
        return cls(
            id=int(payload["id"]),
            meterId=int(payload["meterId"]),
            name=str(payload["name"]),
            registerType=str(payload["registerType"]),
            address=int(payload["address"]),
            length=int(payload["length"]),
            dataType=str(payload["dataType"]),
            scale=float(payload["scale"]) if payload.get("scale") is not None else None,
            targetValue=float(payload["targetValue"]) if payload.get("targetValue") is not None else None,
            thresholdValue=float(payload["thresholdValue"]) if payload.get("thresholdValue") is not None else None,
            unit=payload.get("unit"),
            enabled=bool(payload["enabled"]),
            orderIndex=int(payload["orderIndex"]) if payload.get("orderIndex") is not None else None,
        )


@dataclass(slots=True)
class RegisterState:
    meterId: int
    register: RegisterDto
    value: float | None = None
    lastUpdate: datetime | None = None


@dataclass(frozen=True, slots=True)
class RegisterControl:
    meterId: int
    registerId: int
    targetValue: float | None
    thresholdValue: float | None

    @property
    def key(self) -> tuple[int, int]:
        return (self.meterId, self.registerId)


class MeterStatus:
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
