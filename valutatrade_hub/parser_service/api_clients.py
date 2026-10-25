"""Клиенты для работы с внешними API курсов валют (CoinGecko, ExchangeRate-API)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Абстрактный базовый класс API-клиента."""

    def __init__(self, config: ParserConfig | None = None) -> None:
        """Инициализирует клиента конфигурацией парсера."""
        self.config = config or ParserConfig()
        self.last_meta: dict[str, dict[str, Any]] = {}

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Возвращает человекочитаемое имя источника данных."""

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Запрашивает курсы валют и возвращает словарь вида {'BTC_USD': 59337.21}."""


class CoinGeckoClient(BaseApiClient):
    """Клиент для получения курсов криптовалют из публичного API CoinGecko."""

    @property
    def source_name(self) -> str:
        """Имя источника для логов и метаданных."""
        return "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Запрашивает курсы криптовалют к базовой валюте (USD)."""
        ids_list = [
            self.config.CRYPTO_ID_MAP[code]
            for code in self.config.CRYPTO_CURRENCIES
            if code in self.config.CRYPTO_ID_MAP
        ]
        ids_param = ",".join(ids_list)
        vs_currency = self.config.BASE_CURRENCY.lower()

        params = {
            "ids": ids_param,
            "vs_currencies": vs_currency,
        }

        start_ts = time.perf_counter()
        try:
            response = requests.get(
                self.config.COINGECKO_URL,
                params=params,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise ApiRequestError(f"CoinGecko network error: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)

        if response.status_code == 429:
            raise ApiRequestError("CoinGecko: превышен лимит запросов (429 Too Many Requests)")
        if response.status_code != 200:
            raise ApiRequestError(
                f"CoinGecko вернул статус {response.status_code}: {response.text[:120]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiRequestError("CoinGecko вернул некорректный JSON") from exc

        etag = response.headers.get("ETag", "")
        rates: dict[str, float] = {}
        self.last_meta = {}

        for ticker, coin_id in self.config.CRYPTO_ID_MAP.items():
            if ticker not in self.config.CRYPTO_CURRENCIES:
                continue
            coin_data = payload.get(coin_id)
            if isinstance(coin_data, dict) and vs_currency in coin_data:
                rate_val = float(coin_data[vs_currency])
                pair_key = f"{ticker}_{self.config.BASE_CURRENCY}"
                rates[pair_key] = rate_val
                self.last_meta[pair_key] = {
                    "raw_id": coin_id,
                    "request_ms": elapsed_ms,
                    "status_code": response.status_code,
                    "etag": etag,
                }

        if not rates:
            raise ApiRequestError("CoinGecko не вернул ни одного курса валют")

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Клиент для получения курсов фиатных валют из ExchangeRate-API."""

    @property
    def source_name(self) -> str:
        """Имя источника для логов и метаданных."""
        return "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Запрашивает курсы фиатных валют и приводит их к формату {CODE}_USD."""
        api_key = self.config.EXCHANGERATE_API_KEY
        if not api_key:
            raise ApiRequestError(
                "Не задан ключ EXCHANGERATE_API_KEY в переменных окружения или файле .env"
            )

        base = self.config.BASE_CURRENCY.upper()
        url = f"{self.config.EXCHANGERATE_API_URL}/{api_key}/latest/{base}"

        start_ts = time.perf_counter()
        try:
            response = requests.get(url, timeout=self.config.REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise ApiRequestError(f"ExchangeRate-API network error: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)

        if response.status_code in {401, 403}:
            raise ApiRequestError(
                f"ExchangeRate-API: неверный или неактивный API-ключ (HTTP {response.status_code})"
            )
        if response.status_code == 429:
            raise ApiRequestError(
                "ExchangeRate-API: превышен лимит запросов (429 Too Many Requests)"
            )
        if response.status_code != 200:
            raise ApiRequestError(
                f"ExchangeRate-API вернул статус {response.status_code}: {response.text[:120]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiRequestError("ExchangeRate-API вернул некорректный JSON") from exc

        if payload.get("result") not in {"success", None}:
            error_type = payload.get("error-type", "unknown_error")
            raise ApiRequestError(f"ExchangeRate-API ошибка ответа: {error_type}")

        # В v6 API словарь может называться conversion_rates или rates
        raw_rates = payload.get("conversion_rates") or payload.get("rates")
        if not isinstance(raw_rates, dict):
            raise ApiRequestError("ExchangeRate-API: отсутствует блок курсов в ответе")

        etag = response.headers.get("ETag", "")
        rates: dict[str, float] = {}
        self.last_meta = {}

        for fiat_code in self.config.FIAT_CURRENCIES:
            code = fiat_code.upper()
            if code in raw_rates:
                units_per_base = float(raw_rates[code])
                if units_per_base <= 0:
                    continue
                # Переводим из (1 USD = X EUR) в цену 1 единицы валюты в USD (EUR_USD = 1 / X),
                # чтобы формат 1 EUR = 1.0786 USD и 1 RUB = 0.01016 USD был единым во всей системе
                rate_to_usd = round(1.0 / units_per_base, 8) if units_per_base > 0 else 0.0
                pair_key = f"{code}_{base}"
                rates[pair_key] = rate_to_usd
                self.last_meta[pair_key] = {
                    "raw_id": code,
                    "raw_rate_per_usd": units_per_base,
                    "request_ms": elapsed_ms,
                    "status_code": response.status_code,
                    "etag": etag,
                }

        if not rates:
            raise ApiRequestError("ExchangeRate-API не вернул отслеживаемых фиатных валют")

        return rates
