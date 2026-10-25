"""Singleton DatabaseManager — абстракция над JSON-хранилищем."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Единая точка управления чтением и атомарной записью JSON-файлов (Singleton).

    Реализация через __new__ обеспечивает простоту и гарантирует единственный
    экземпляр менеджера БД во всём приложении.
    """

    _instance: DatabaseManager | None = None

    def __new__(cls) -> DatabaseManager:
        """Возвращает единственный экземпляр DatabaseManager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Подключает SettingsLoader."""
        self._settings = SettingsLoader()

    def read_json(self, filepath: str | Path, default: Any) -> Any:
        """Безопасно читает JSON-файл или возвращает значение по умолчанию."""
        path = Path(filepath)
        if not path.exists():
            return default
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return default
            return json.loads(content)
        except (json.JSONDecodeError, OSError):
            return default

    def write_json(self, filepath: str | Path, data: Any) -> None:
        """Атомарно записывает данные в JSON-файл через временный .tmp файл."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def load_users_data(self) -> list[dict[str, Any]]:
        """Читает список пользователей из users.json."""
        path = self._settings.get("USERS_FILE")
        data = self.read_json(path, [])
        return data if isinstance(data, list) else []

    def save_users_data(self, users: list[dict[str, Any]]) -> None:
        """Сохраняет список пользователей в users.json."""
        path = self._settings.get("USERS_FILE")
        self.write_json(path, users)

    def load_portfolios_data(self) -> list[dict[str, Any]]:
        """Читает список портфелей из portfolios.json."""
        path = self._settings.get("PORTFOLIOS_FILE")
        data = self.read_json(path, [])
        return data if isinstance(data, list) else []

    def save_portfolios_data(self, portfolios: list[dict[str, Any]]) -> None:
        """Сохраняет список портфелей в portfolios.json."""
        path = self._settings.get("PORTFOLIOS_FILE")
        self.write_json(path, portfolios)

    def load_rates_data(self) -> dict[str, Any]:
        """Читает кеш курсов из rates.json."""
        path = self._settings.get("RATES_FILE")
        data = self.read_json(path, {})
        return data if isinstance(data, dict) else {}

    def save_rates_data(self, rates: dict[str, Any]) -> None:
        """Сохраняет кеш курсов в rates.json."""
        path = self._settings.get("RATES_FILE")
        self.write_json(path, rates)