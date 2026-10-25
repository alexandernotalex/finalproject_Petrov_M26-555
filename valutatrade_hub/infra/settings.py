"""Singleton SettingsLoader для загрузки и кеширования конфигурации проекта."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


class SettingsLoader:
    """Единая точка доступа к конфигурации проекта (Singleton).

    Реализация через метод __new__ выбрана за простоту, прозрачность типизации
    и высокую читаемость без усложнения иерархии метаклассами.
    """

    _instance: SettingsLoader | None = None
    _initialized: bool = False

    def __new__(cls) -> SettingsLoader:
        """Гарантирует создание единственного экземпляра класса."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Инициализирует настройки при первом создании экземпляра."""
        if not self._initialized:
            self._base_dir = Path(__file__).resolve().parent.parent.parent
            self._settings: dict[str, Any] = {}
            self.reload()
            SettingsLoader._initialized = True

    def reload(self) -> None:
        """Загружает или перезагружает настройки из pyproject.toml или config.json."""
        defaults: dict[str, Any] = {
            "BASE_DIR": str(self._base_dir),
            "DATA_DIR": str(self._base_dir / "data"),
            "USERS_FILE": str(self._base_dir / "data" / "users.json"),
            "PORTFOLIOS_FILE": str(self._base_dir / "data" / "portfolios.json"),
            "RATES_FILE": str(self._base_dir / "data" / "rates.json"),
            "EXCHANGE_RATES_FILE": str(self._base_dir / "data" / "exchange_rates.json"),
            "RATES_TTL_SECONDS": 300,
            "DEFAULT_BASE_CURRENCY": "USD",
            "LOG_DIR": str(self._base_dir / "logs"),
            "LOG_FILE": str(self._base_dir / "logs" / "actions.log"),
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "STRING",
            "LOG_MAX_BYTES": 1_048_576,  # 1 MB
            "LOG_BACKUP_COUNT": 5,
        }

        pyproject_path = self._base_dir / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with pyproject_path.open("rb") as f:
                    toml_data = tomllib.load(f)
                vt_cfg = toml_data.get("tool", {}).get("valutatrade", {})
                self._apply_custom_config(defaults, vt_cfg)
            except (tomllib.TOMLDecodeError, OSError):
                pass

        config_json_path = self._base_dir / "config.json"
        if config_json_path.exists():
            try:
                raw_json = json.loads(config_json_path.read_text(encoding="utf-8"))
                if isinstance(raw_json, dict):
                    self._apply_custom_config(defaults, raw_json)
            except (json.JSONDecodeError, OSError):
                pass

        self._settings = defaults

    def _apply_custom_config(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        """Сопоставляет пользовательские ключи из конфига с системными настройками."""
        path_keys = {
            "DATA_DIR",
            "USERS_FILE",
            "PORTFOLIOS_FILE",
            "RATES_FILE",
            "EXCHANGE_RATES_FILE",
            "LOG_DIR",
            "LOG_FILE",
        }
        for key, value in source.items():
            upper_key = key.upper()
            if upper_key in path_keys and isinstance(value, str):
                path_obj = Path(value)
                if not path_obj.is_absolute():
                    path_obj = self._base_dir / path_obj
                target[upper_key] = str(path_obj)
            else:
                target[upper_key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает значение конфигурации по ключу (регистронезависимо)."""
        return self._settings.get(key.upper(), default)
