"""Вспомогательные функции для работы с JSON-файлами, валидации и расчёта курсов."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"

CACHE_TTL_SECONDS = 300  # 5 минут

# Заглушка курсов на случай отсутствия или устаревания кеша
DEFAULT_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "RUB": 0.01016,
    "ETH": 3720.00,
}


def load_json(filepath: Path, default: Any) -> Any:
    """Читает JSON-файл или возвращает значение по умолчанию."""
    if not filepath.exists():
        return default
    try:
        content = filepath.read_text(encoding="utf-8").strip()
        if not content:
            return default
        return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(filepath: Path, data: Any) -> None:
    """Атомарно записывает данные в JSON-файл через временный файл."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(filepath)


def validate_currency_code(currency_code: str) -> str:
    """Проверяет и нормализует код валюты (верхний регистр, не пустой)."""
    if not isinstance(currency_code, str) or not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым")
    code = currency_code.strip().upper()
    if not code.isalpha() or not (2 <= len(code) <= 5):
        raise ValueError(f"Некорректный код валюты '{currency_code}'")
    return code


def validate_amount(amount: float | int | str) -> float:
    """Проверяет, что сумма является положительным числом float > 0."""
    try:
        value = float(amount)
    except (ValueError, TypeError) as exc:
        raise ValueError("'amount' должен быть положительным числом") from exc
    if isinstance(amount, bool) or value <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return value


def is_rate_fresh(updated_at_str: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
    """Проверяет, не устарел ли курс относительно заданного TTL."""
    try:
        updated_at = datetime.fromisoformat(updated_at_str)
        now = datetime.now(updated_at.tzinfo)
        return (now - updated_at) <= timedelta(seconds=ttl_seconds)
    except ValueError:
        return False


def get_or_refresh_rates() -> dict[str, Any]:
    """Возвращает кеш курсов из rates.json; при отсутствии создаёт из заглушки."""
    rates_data = load_json(RATES_FILE, {})
    if not rates_data:
        now_iso = datetime.now().replace(microsecond=0).isoformat()
        rates_data = {
            f"{code}_USD": {"rate": rate, "updated_at": now_iso}
            for code, rate in DEFAULT_RATES_TO_USD.items()
            if code != "USD"
        }
        rates_data["source"] = "StubService"
        rates_data["last_refresh"] = now_iso
        save_json(RATES_FILE, rates_data)
    return rates_data


def extract_flat_rates(rates_data: dict[str, Any]) -> dict[str, float]:
    """Извлекает словарь вида {'BTC_USD': 59337.21} из структуры rates.json."""
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
    """Вычисляет курс from_code -> to_code, время обновления и флаг свежести."""
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

    # Запасной расчёт через заглушку DEFAULT_RATES_TO_USD
    if src in DEFAULT_RATES_TO_USD and dst in DEFAULT_RATES_TO_USD:
        rate = DEFAULT_RATES_TO_USD[src] / DEFAULT_RATES_TO_USD[dst]
        rates_data[direct_key] = {"rate": rate, "updated_at": now_iso}
        rates_data["last_refresh"] = now_iso
        save_json(RATES_FILE, rates_data)
        return rate, now_iso, True

    raise ValueError(f"Не удалось получить курс для {src}→{dst}")
