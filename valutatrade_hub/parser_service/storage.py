"""Операции чтения и атомарной записи для rates.json и exchange_rates.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    """Хранилище актуальных курсов (rates.json) и исторического журнала (exchange_rates.json)."""

    def __init__(self, config: ParserConfig | None = None) -> None:
        """Инициализирует пути к файлам данных."""
        self.config = config or ParserConfig()
        self.rates_path = Path(self.config.RATES_FILE_PATH)
        self.history_path = Path(self.config.HISTORY_FILE_PATH)

    @staticmethod
    def _atomic_write(filepath: Path, data: Any) -> None:
        """Атомарно записывает JSON через временный файл (.tmp -> replace)."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(filepath)

    @staticmethod
    def _safe_read(filepath: Path, default: Any) -> Any:
        """Безопасно читает JSON-файл или возвращает значение по умолчанию."""
        if not filepath.exists():
            return default
        try:
            text = filepath.read_text(encoding="utf-8").strip()
            if not text:
                return default
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return default

    def load_current_rates(self) -> dict[str, Any]:
        """Загружает актуальный снимок курсов из data/rates.json."""
        data = self._safe_read(self.rates_path, {})
        if not isinstance(data, dict):
            return {"pairs": {}, "last_refresh": None}
        if "pairs" not in data:
            # Миграция плоского формата в формат с ключом 'pairs'
            pairs: dict[str, Any] = {}
            for k, v in data.items():
                if isinstance(v, dict) and "rate" in v:
                    pairs[k] = v
            return {
                "pairs": pairs,
                "last_refresh": data.get("last_refresh"),
            }
        return data

    def save_current_rates(
        self,
        new_pairs: dict[str, dict[str, Any]],
        last_refresh: str,
    ) -> int:
        """Обновляет data/rates.json: апдейт побеждает, если updated_at свежее текущего."""
        current = self.load_current_rates()
        pairs = current.get("pairs", {})
        if not isinstance(pairs, dict):
            pairs = {}

        updated_count = 0
        for pair_key, info in new_pairs.items():
            existing = pairs.get(pair_key)
            new_ts = str(info.get("updated_at", ""))
            old_ts = str(existing.get("updated_at", "")) if isinstance(existing, dict) else ""
            if not old_ts or new_ts >= old_ts:
                pairs[pair_key] = {
                    "rate": float(info["rate"]),
                    "updated_at": new_ts,
                    "source": str(info.get("source", "ParserService")),
                }
                updated_count += 1

        snapshot = {
            "pairs": pairs,
            "last_refresh": last_refresh,
        }
        self._atomic_write(self.rates_path, snapshot)
        return updated_count

    def load_history(self) -> list[dict[str, Any]]:
        """Загружает исторический журнал из data/exchange_rates.json."""
        data = self._safe_read(self.history_path, [])
        return data if isinstance(data, list) else []

    def append_history_records(self, records: list[dict[str, Any]]) -> None:
        """Добавляет новые измерения в exchange_rates.json без дублирования по id."""
        if not records:
            return
        history = self.load_history()
        existing_ids = {str(item.get("id")) for item in history if isinstance(item, dict)}

        for rec in records:
            rec_id = str(rec.get("id", ""))
            if rec_id and rec_id not in existing_ids:
                history.append(rec)
                existing_ids.add(rec_id)

        self._atomic_write(self.history_path, history)