"""Основной модуль координации обновления курсов (RatesUpdater)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage


def _get_parser_logger(log_path: str) -> logging.Logger:
    """Настраивает файловый логгер для Parser Service (logs/parser.log)."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("valutatrade.parser")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            filename=path,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


class RatesUpdater:
    """Координатор опроса внешних API, агрегации курсов и сохранения в хранилище."""

    def __init__(
        self,
        clients: Sequence[BaseApiClient] | None = None,
        storage: RatesStorage | None = None,
        config: ParserConfig | None = None,
    ) -> None:
        """Инициализирует RatesUpdater списком клиентов и объектом хранилища."""
        self.config = config or ParserConfig()
        self.storage = storage or RatesStorage(self.config)
        self.clients: list[BaseApiClient] = (
            list(clients)
            if clients is not None
            else [
                CoinGeckoClient(self.config),
                ExchangeRateApiClient(self.config),
            ]
        )
        self.logger = _get_parser_logger(self.config.PARSER_LOG_PATH)

    def run_update(self, source_filter: str | None = None) -> str:
        """Опрашивает клиентов, сохраняет данные в rates.json и exchange_rates.json."""
        selected_clients = self._filter_clients(source_filter)
        output_lines: list[str] = ["INFO: Starting rates update..."]
        self.logger.info("Starting rates update...")

        now_utc = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        aggregated_pairs: dict[str, dict[str, Any]] = {}
        history_records: list[dict[str, Any]] = []
        had_errors = False

        for client in selected_clients:
            src_name = client.source_name
            try:
                fetched = client.fetch_rates()
                count = len(fetched)
                msg = f"INFO: Fetching from {src_name}... OK ({count} rates)"
                output_lines.append(msg)
                self.logger.info("Fetched %d rates from %s", count, src_name)

                for pair_key, rate_val in fetched.items():
                    from_curr, to_curr = pair_key.split("_", 1)
                    aggregated_pairs[pair_key] = {
                        "rate": rate_val,
                        "updated_at": now_utc,
                        "source": src_name,
                    }
                    record_id = f"{from_curr}_{to_curr}_{now_utc}"
                    meta = client.last_meta.get(pair_key, {"status_code": 200})
                    history_records.append(
                        {
                            "id": record_id,
                            "from_currency": from_curr,
                            "to_currency": to_curr,
                            "rate": rate_val,
                            "timestamp": now_utc,
                            "source": src_name,
                            "meta": meta,
                        }
                    )
            except ApiRequestError as exc:
                had_errors = True
                err_msg = f"ERROR: Failed to fetch from {src_name}: {exc}"
                output_lines.append(err_msg)
                self.logger.error("Failed to fetch from %s: %s", src_name, exc)

        total_updated = len(aggregated_pairs)
        if total_updated > 0:
            write_msg = f"INFO: Writing {total_updated} rates to data/rates.json..."
            output_lines.append(write_msg)
            self.logger.info("Writing %d rates to storage", total_updated)
            self.storage.save_current_rates(aggregated_pairs, last_refresh=now_utc)
            self.storage.append_history_records(history_records)

        if had_errors:
            output_lines.append("Update completed with errors. Check logs/parser.log for details.")
        else:
            output_lines.append(
                f"Update successful. Total rates updated: {total_updated}. Last refresh: {now_utc}"
            )

        return "\n".join(output_lines)

    def _filter_clients(self, source_filter: str | None) -> list[BaseApiClient]:
        """Фильтрует список клиентов по аргументу --source (coingecko / exchangerate)."""
        if not source_filter:
            return self.clients

        normalized = source_filter.strip().lower()
        aliases = {
            "coingecko": "coingecko",
            "exchangerate": "exchangerate-api",
            "exchangerate-api": "exchangerate-api",
        }
        target = aliases.get(normalized)
        if target is None:
            raise ValueError(
                f"Неизвестный источник '{source_filter}'. Доступные: coingecko, exchangerate"
            )

        return [c for c in self.clients if c.source_name.lower() == target]
