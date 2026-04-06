from __future__ import annotations

import json
from pathlib import Path

from transformer_client.models import ClientConfig, DEFAULT_CLIENT_CONFIG


CONFIG_FILE_NAME = "client-config.json"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "resources" / "client-config.default.json"


def load_client_config(workdir: Path) -> ClientConfig:
    config_path = workdir / CONFIG_FILE_NAME
    if config_path.exists():
        return ClientConfig.from_dict(_load_json(config_path))
    if DEFAULT_CONFIG_PATH.exists():
        return ClientConfig.from_dict(_load_json(DEFAULT_CONFIG_PATH))
    return ClientConfig.from_dict(DEFAULT_CLIENT_CONFIG)


def save_client_config(config: ClientConfig, workdir: Path) -> Path:
    config_path = workdir / CONFIG_FILE_NAME
    config_path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
