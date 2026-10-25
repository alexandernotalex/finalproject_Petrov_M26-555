"""Декоратор @log_action для логирования доменных операций."""

from __future__ import annotations

import functools
import inspect
import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import get_action_logger


def log_action(
    action: str | None = None,
    verbose: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Логирует выполнение доменных операций (BUY, SELL, REGISTER, LOGIN).

    Фиксирует timestamp, пользователя, валюту, сумму, курс, базовую валюту и результат.
    Не подавляет исключения, но записывает тип и текст ошибки в лог.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        action_name = (action or func.__name__).upper()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_action_logger()
            settings = SettingsLoader()
            log_format = str(settings.get("LOG_FORMAT", "STRING")).upper()

            sig = inspect.signature(func)
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            params = bound.arguments

            self_obj = params.get("self")
            user_val = params.get("username")
            if not user_val and self_obj is not None:
                current_user = getattr(self_obj, "current_user", None)
                if current_user is not None:
                    user_val = getattr(current_user, "username", None)
            user_str = str(user_val) if user_val else "anonymous"

            currency_code = params.get("currency_code") or params.get("from_currency")
            amount = params.get("amount")
            base = params.get("base_currency") or "USD"

            timestamp = datetime.now().replace(microsecond=0).isoformat()

            try:
                result = func(*args, **kwargs)

                # Если при логине пользователь обновился внутри метода
                if user_str == "anonymous" and self_obj is not None:
                    current_user = getattr(self_obj, "current_user", None)
                    if current_user is not None:
                        user_str = getattr(current_user, "username", "anonymous")

                rate_val: str | None = None
                transition_val: str | None = None
                if isinstance(result, str):
                    rate_match = re.search(r"по курсу ([0-9.]+)", result)
                    if rate_match:
                        rate_val = rate_match.group(1)
                    trans_match = re.search(r"было [0-9.]+ → стало [0-9.]+", result)
                    if trans_match:
                        transition_val = trans_match.group(0)

                _write_log(
                    logger=logger,
                    log_format=log_format,
                    timestamp=timestamp,
                    action=action_name,
                    user=user_str,
                    currency=currency_code,
                    amount=amount,
                    rate=rate_val,
                    base=base if action_name in {"BUY", "SELL"} else None,
                    result_status="OK",
                    verbose=verbose,
                    details=transition_val,
                )
                return result

            except Exception as exc:
                _write_log(
                    logger=logger,
                    log_format=log_format,
                    timestamp=timestamp,
                    action=action_name,
                    user=user_str,
                    currency=currency_code,
                    amount=amount,
                    rate=None,
                    base=base if action_name in {"BUY", "SELL"} else None,
                    result_status="ERROR",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    verbose=verbose,
                )
                raise

        return wrapper

    return decorator


def _write_log(
    logger: Any,
    log_format: str,
    timestamp: str,
    action: str,
    user: str,
    currency: Any,
    amount: Any,
    rate: str | None,
    base: str | None,
    result_status: str,
    error_type: str | None = None,
    error_message: str | None = None,
    verbose: bool = False,
    details: str | None = None,
) -> None:
    """Форматирует и записывает сообщение в лог (STRING или JSON)."""
    if log_format == "JSON":
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "action": action,
            "user": user,
            "currency": str(currency).upper() if currency else None,
            "amount": amount,
            "rate": float(rate) if rate else None,
            "base": base,
            "result": result_status,
        }
        if error_type:
            payload["error_type"] = error_type
            payload["error_message"] = error_message
        if verbose and details:
            payload["details"] = details
        logger.info(json.dumps(payload, ensure_ascii=False))
        return

    parts = [f"{timestamp} {action} user='{user}'"]
    if currency is not None:
        parts.append(f"currency='{str(currency).strip().upper()}'")
    if amount is not None:
        try:
            parts.append(f"amount={float(amount):.4f}")
        except (ValueError, TypeError):
            parts.append(f"amount='{amount}'")
    if rate is not None:
        parts.append(f"rate={rate}")
    if base is not None:
        parts.append(f"base='{base}'")

    parts.append(f"result={result_status}")

    if error_type:
        parts.append(f"error_type={error_type} error_message='{error_message}'")
    if verbose and details:
        parts.append(f"details='{details}'")

    logger.info(" ".join(parts))
