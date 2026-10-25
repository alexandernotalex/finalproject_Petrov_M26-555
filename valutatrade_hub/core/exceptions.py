"""Пользовательские исключения платформы ValutaTrade Hub."""

from __future__ import annotations


class ValutaTradeError(Exception):
    """Базовое исключение приложения ValutaTrade Hub."""


class InsufficientFundsError(ValutaTradeError):
    """Исключение при нехватке средств на кошельке."""

    def __init__(self, available: float, required: float, code: str) -> None:
        """Формирует сообщение о нехватке средств."""
        self.available = available
        self.required = required
        self.code = code
        message = (
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )
        super().__init__(message)


class CurrencyNotFoundError(ValutaTradeError):
    """Исключение при запросе неизвестного кода валюты."""

    def __init__(self, code: str) -> None:
        """Формирует сообщение о неизвестной валюте."""
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Исключение при сбое обращения к внешнему API или источнику курсов."""

    def __init__(self, reason: str) -> None:
        """Формирует сообщение о сбое API."""
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")