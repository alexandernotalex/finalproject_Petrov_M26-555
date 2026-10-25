"""Вспомогательные функции для валидации валют, расчёта курсов и работы с кешем."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from valutatrade_hub.core.currencies import Currency, get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

# Заглушка курсов на случай инициализации пустого кеша
DEFAULT_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.2950,
    "BTC": 59337.21,
    "RUB": 0.01016,
    "ETH": 3720.00,
    "SOL": 175.50,
}


def validate_currency_code(currency_code: str) -> str:
    """Проверяет код валюты через реестр currencies.py и возвращает его в верхнем регистре."""
    currency: Currency = get_currency(currency_code)
    return currency.code


def validate_amount(amount: float | int | str) -> float:
    """Проверяет, что сумма является положительным числом float > 0."""
    try:
        value = float(amount)
    except (ValueError, TypeError) as exc:
        raise ValueError("'amount' должен быть положительным числом") from exc
    if isinstance(amount, bool) or value <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return value


def is_rate_fresh(updated_at_str: str, ttl_seconds: int | None = None) -> bool:
    """Проверяет, не устарел ли курс относительно TTL из SettingsLoader."""
    settings = SettingsLoader()
    ttl = ttl_seconds if ttl_seconds is not None else int(settings.get("RATES_TTL_SECONDS", 300))
    try:
        updated_at = datetime.fromisoformat(updated_at_str)
        now = datetime.now(updated_at.tzinfo)
        return (now - updated_at) <= timedelta(seconds=ttl)
    except ValueError:
        return False


def get_or_refresh_rates() -> dict[str, Any]:
    """Читает кеш курсов через DatabaseManager; при отсутствии создаёт из заглушки."""
    db = DatabaseManager()
    rates_data = db.load_rates_data()
    if not rates_data:
        now_iso = datetime.now().replace(microsecond=0).isoformat()
        rates_data = {
            f"{code}_USD": {"rate": rate, "updated_at": now_iso}
            for code, rate in DEFAULT_RATES_TO_USD.items()
            if code != "USD"
        }
        rates_data["source"] = "StubService"
        rates_data["last_refresh"] = now_iso
        db.save_rates_data(rates_data)
    return rates_data


def extract_flat_rates(rates_data: dict[str, Any]) -> dict[str, float]:
    """Извлекает плоский словарь курсов {'BTC_USD': 59337.21} из структуры rates.json."""
    flat_rates: dict[str, float] = {"USD_USD": 1.0}
    for key, val in rates_data.items():
        if isinstance(val, dict) and "rate" in val:
            flat_rates[key.upper()] = float(val["rate"])
    return flat_rates


def resolve_pair_rate(
    from_code: str,
    to_code: str,
    rates_data: dict[str, Any],
) -> tuple[float, str, bool]:
    """Вычисляет курс from_code -> to_code, время обновления и флаг свежести TTL."""
    src = validate_currency_code(from_code)
    dst = validate_currency_code(to_code)
    now_iso = datetime.now().replace(microsecond=0).isoformat()

    if src == dst:
        return 1.0, now_iso, True

    direct_key = f"{src}_{dst}"
    reverse_key = f"{dst}_{src}"

    if direct_key in rates_data and isinstance(rates_data[direct_key], dict):
        entry = rates_data[direct_key]
        rate = float(entry["rate"])
        updated_at = str(entry.get("updated_at", now_iso))
        return rate, updated_at, is_rate_fresh(updated_at)

    if reverse_key in rates_data and isinstance(rates_data[reverse_key], dict):
        entry = rates_data[reverse_key]
        rev_rate = float(entry["rate"])
        if rev_rate > 0:
            rate = 1.0 / rev_rate
            updated_at = str(entry.get("updated_at", now_iso))
            return rate, updated_at, is_rate_fresh(updated_at)

    # Кросс-курс через USD
    src_usd_key = f"{src}_USD"
    dst_usd_key = f"{dst}_USD"
    if (
        src_usd_key in rates_data
        and dst_usd_key in rates_data
        and isinstance(rates_data[src_usd_key], dict)
        and isinstance(rates_data[dst_usd_key], dict)
    ):
        src_rate = float(rates_data[src_usd_key]["rate"])
        dst_rate = float(rates_data[dst_usd_key]["rate"])
        if dst_rate > 0:
            rate = src_rate / dst_rate
            updated_at = str(rates_data[src_usd_key].get("updated_at", now_iso))
            return rate, updated_at, is_rate_fresh(updated_at)

    # Резервное получение из DEFAULT_RATES_TO_USD
    if src in DEFAULT_RATES_TO_USD and dst in DEFAULT_RATES_TO_USD:
        rate = DEFAULT_RATES_TO_USD[src] / DEFAULT_RATES_TO_USD[dst]
        return rate, now_iso, False

    raise ApiRequestError(f"Не удалось получить курс для {src}→{dst}")
