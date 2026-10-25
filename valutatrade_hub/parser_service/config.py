"""Конфигурация API и параметров обновления для Parser Service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_dotenv_key(key_name: str, default: str = "") -> str:
    """Читает переменную из окружения или локального файла .env."""
    env_val = os.getenv(key_name)
    if env_val:
        return env_val.strip()

    dotenv_path = BASE_DIR / ".env"
    if dotenv_path.exists():
        try:
            for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                    continue
                k, v = clean_line.split("=", 1)
                if k.strip() == key_name:
                    return v.strip().strip("'").strip('"')
        except OSError:
            pass
    return default


@dataclass
class ParserConfig:
    """Структурированное хранение настроек Parser Service."""

    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: _load_dotenv_key("EXCHANGERATE_API_KEY", "")
    )

    # Эндпоинты
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    # Списки валют
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    # Пути к файлам
    RATES_FILE_PATH: str = str(BASE_DIR / "data" / "rates.json")
    HISTORY_FILE_PATH: str = str(BASE_DIR / "data" / "exchange_rates.json")
    PARSER_LOG_PATH: str = str(BASE_DIR / "logs" / "parser.log")

    # Сетевые параметры
    REQUEST_TIMEOUT: int = 10
