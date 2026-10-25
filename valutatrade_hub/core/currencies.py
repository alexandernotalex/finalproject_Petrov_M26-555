"""Иерархия валют (Fiat/Crypto) и реестр поддерживаемых валют."""

from __future__ import annotations

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Абстрактный базовый класс валюты."""

    def __init__(self, code: str, name: str) -> None:
        """Инициализирует базовые атрибуты валюты с проверкой инвариантов."""
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Код валюты не может быть пустым")
        clean_code = code.strip().upper()
        if " " in clean_code or not (2 <= len(clean_code) <= 5) or not clean_code.isalnum():
            raise ValueError(
                f"Некорректный код валюты '{code}':"
                "требуется 2-5 символов в верхнем регистре без пробелов"
            )

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")

        self.code: str = clean_code
        self.name: str = name.strip()

    @abstractmethod
    def get_display_info(self) -> str:
        """Возвращает строковое представление валюты для UI и логов."""


class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны или зоны эмиссии."""

    def __init__(self, code: str, name: str, issuing_country: str) -> None:
        """Инициализирует фиатную валюту."""
        super().__init__(code=code, name=name)
        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Страна/зона эмиссии не может быть пустой")
        self.issuing_country: str = issuing_country.strip()

    def get_display_info(self) -> str:
        """Возвращает отформатированную информацию о фиатной валюте."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с указанием алгоритма хеширования и рыночной капитализации."""

    def __init__(self, code: str, name: str, algorithm: str, market_cap: float) -> None:
        """Инициализирует криптовалюту."""
        super().__init__(code=code, name=name)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")
        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or market_cap < 0
        ):
            raise ValueError("Капитализация должна быть неотрицательным числом")
        self.algorithm: str = algorithm.strip()
        self.market_cap: float = float(market_cap)

    def get_display_info(self) -> str:
        """Возвращает отформатированную информацию о криптовалюте."""
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


# Реестр поддерживаемых в системе валют
CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency(code="USD", name="US Dollar", issuing_country="United States"),
    "EUR": FiatCurrency(code="EUR", name="Euro", issuing_country="Eurozone"),
    "GBP": FiatCurrency(code="GBP", name="British Pound", issuing_country="United Kingdom"),
    "RUB": FiatCurrency(code="RUB", name="Russian Ruble", issuing_country="Russian Federation"),
    "BTC": CryptoCurrency(code="BTC", name="Bitcoin", algorithm="SHA-256", market_cap=1.12e12),
    "ETH": CryptoCurrency(code="ETH", name="Ethereum", algorithm="Ethash", market_cap=4.50e11),
    "SOL": CryptoCurrency(
        code="SOL", name="Solana", algorithm="Proof of History", market_cap=8.50e10
    ),
}


def get_currency(code: str) -> Currency:
    """Возвращает объект валюты из реестра по коду или выбрасывает CurrencyNotFoundError."""
    if not isinstance(code, str) or not code.strip():
        raise CurrencyNotFoundError(str(code))
    normalized = code.strip().upper()
    currency = CURRENCY_REGISTRY.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency


def get_supported_codes() -> list[str]:
    """Возвращает список всех зарегистрированных кодов валют."""
    return sorted(CURRENCY_REGISTRY.keys())
