"""Модели предметной области: User, Wallet, Portfolio."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any

from valutatrade_hub.core.exceptions import CurrencyNotFoundError, InsufficientFundsError

MIN_PASSWORD_LENGTH = 4


class User:
    """Класс пользователя системы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime | str | None = None,
    ) -> None:
        """Инициализирует пользователя."""
        self.user_id = user_id
        self.username = username
        self._salt = salt
        self._hashed_password = hashed_password

        if isinstance(registration_date, str):
            self._registration_date = datetime.fromisoformat(registration_date)
        elif isinstance(registration_date, datetime):
            self._registration_date = registration_date
        else:
            self._registration_date = datetime.now().replace(microsecond=0)

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """Создаёт односторонний SHA-256 хеш пароля с солью."""
        return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> User:
        """Фабричный метод создания нового пользователя с валидацией пароля."""
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
        salt = secrets.token_hex(4)
        hashed = cls.hash_password(password, salt)
        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hashed,
            salt=salt,
            registration_date=datetime.now().replace(microsecond=0),
        )

    @property
    def user_id(self) -> int:
        """Возвращает уникальный идентификатор пользователя."""
        return self._user_id

    @user_id.setter
    def user_id(self, value: int) -> None:
        """Устанавливает ID пользователя."""
        if not isinstance(value, int) or value <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = value

    @property
    def username(self) -> str:
        """Возвращает имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Устанавливает имя пользователя с проверкой на пустоту."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Возвращает хеш пароля."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Возвращает соль пользователя."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Возвращает дату регистрации пользователя."""
        return self._registration_date

    def change_password(self, new_password: str) -> None:
        """Изменяет пароль пользователя с генерацией новой соли и хешированием."""
        if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
        self._salt = secrets.token_hex(4)
        self._hashed_password = self.hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверяет введённый пароль на совпадение с сохранённым хешем."""
        if not isinstance(password, str):
            return False
        return self.hash_password(password, self._salt) == self._hashed_password

    def get_user_info(self) -> dict[str, Any]:
        """Возвращает информацию о пользователе без пароля и соли."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Сериализует объект пользователя для сохранения в users.json."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        """Десериализует пользователя из словаря."""
        return cls(
            user_id=int(data["user_id"]),
            username=str(data["username"]),
            hashed_password=str(data["hashed_password"]),
            salt=str(data["salt"]),
            registration_date=str(data["registration_date"]),
        )


class Wallet:
    """Кошелёк пользователя для одной конкретной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        """Инициализирует кошелёк с кодом валюты и начальным балансом."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")
        self.currency_code = currency_code.strip().upper()
        self.balance = balance

    @property
    def balance(self) -> float:
        """Возвращает текущий баланс кошелька."""
        return self._balance

    @balance.setter
    def balance(self, value: float | int) -> None:
        """Устанавливает баланс, запрещая отрицательные и нечисловые значения."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополняет баланс на указанную положительную сумму."""
        self._validate_amount(amount)
        self.balance += float(amount)

    def withdraw(self, amount: float) -> None:
        """Снимает средства с кошелька или выбрасывает InsufficientFundsError."""
        self._validate_amount(amount)
        amount_float = float(amount)
        if amount_float > self._balance:
            raise InsufficientFundsError(
                available=self._balance,
                required=amount_float,
                code=self.currency_code,
            )
        self.balance -= amount_float

    @staticmethod
    def _validate_amount(amount: float) -> None:
        """Проверяет, что сумма операции — положительное число."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("'amount' должен быть положительным числом")

    def get_balance_info(self) -> str:
        """Возвращает строковое представление текущего баланса."""
        return f"{self.currency_code}: {self._balance:.4f}"

    def to_dict(self) -> dict[str, Any]:
        """Сериализует кошелёк в словарь."""
        return {
            "currency_code": self.currency_code,
            "balance": self._balance,
        }

    @classmethod
    def from_dict(cls, currency_code: str, data: dict[str, Any]) -> Wallet:
        """Восстанавливает кошелёк из словаря JSON."""
        code = data.get("currency_code", currency_code)
        balance = float(data.get("balance", 0.0))
        return cls(currency_code=code, balance=balance)


class Portfolio:
    """Управление всеми кошельками одного пользователя."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        """Инициализирует портфель пользователя."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = dict(wallets) if wallets else {}
        self._user = user

    @property
    def user_id(self) -> int:
        """Возвращает ID владельца портфеля."""
        return self._user_id

    @property
    def user(self) -> User | None:
        """Возвращает объект пользователя (только для чтения)."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Возвращает копию словаря кошельков для защиты инвариантов."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Создаёт и добавляет новый кошелёк в портфель, если его ещё нет."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")
        code = currency_code.strip().upper()
        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует в портфеле")
        wallet = Wallet(currency_code=code, balance=0.0)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Возвращает объект Wallet по коду валюты или None."""
        if not isinstance(currency_code, str):
            return None
        return self._wallets.get(currency_code.strip().upper())

    def get_total_value(
        self,
        base_currency: str = "USD",
        exchange_rates: dict[str, float] | None = None,
    ) -> float:
        """Возвращает общую стоимость всех валют портфеля в base_currency."""
        base = base_currency.strip().upper()
        rates = exchange_rates or {
            "USD_USD": 1.0,
            "EUR_USD": 1.0786,
            "GBP_USD": 1.2950,
            "BTC_USD": 59337.21,
            "RUB_USD": 0.01016,
            "ETH_USD": 3720.00,
            "SOL_USD": 175.50,
        }

        total_value = 0.0
        for code, wallet in self._wallets.items():
            if code == base:
                total_value += wallet.balance
                continue

            direct_key = f"{code}_{base}"
            reverse_key = f"{base}_{code}"

            if direct_key in rates:
                rate = rates[direct_key]
            elif reverse_key in rates and rates[reverse_key] > 0:
                rate = 1.0 / rates[reverse_key]
            elif f"{code}_USD" in rates and f"{base}_USD" in rates and rates[f"{base}_USD"] > 0:
                rate = rates[f"{code}_USD"] / rates[f"{base}_USD"]
            else:
                raise CurrencyNotFoundError(base)

            total_value += wallet.balance * rate

        return total_value

    def to_dict(self) -> dict[str, Any]:
        """Сериализует портфель для сохранения в portfolios.json."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {
                    "currency_code": wallet.currency_code,
                    "balance": wallet.balance,
                }
                for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], user: User | None = None) -> Portfolio:
        """Восстанавливает портфель из словаря JSON."""
        user_id = int(data["user_id"])
        raw_wallets = data.get("wallets", {})
        wallets = {
            code.upper(): Wallet.from_dict(code.upper(), w_data)
            for code, w_data in raw_wallets.items()
        }
        return cls(user_id=user_id, wallets=wallets, user=user)