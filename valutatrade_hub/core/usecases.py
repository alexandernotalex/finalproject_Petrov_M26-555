"""Бизнес-логика (use cases) основного сервиса ValutaTrade Hub."""

from __future__ import annotations

from datetime import datetime

from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    DEFAULT_RATES_TO_USD,
    PORTFOLIOS_FILE,
    RATES_FILE,
    USERS_FILE,
    extract_flat_rates,
    get_or_refresh_rates,
    load_json,
    resolve_pair_rate,
    save_json,
    validate_amount,
    validate_currency_code,
)


class TradingUseCases:
    """Оркестратор бизнес-операций пользователя, портфеля и курсов валют."""

    def __init__(self) -> None:
        """Инициализирует сервис и текущую сессию пользователя."""
        self._current_user: User | None = None

    @property
    def current_user(self) -> User | None:
        """Возвращает текущего авторизованного пользователя."""
        return self._current_user

    def _require_auth(self) -> User:
        """Проверяет, что пользователь вошёл в систему."""
        if self._current_user is None:
            raise PermissionError("Сначала выполните login")
        return self._current_user

    def _load_users(self) -> list[User]:
        """Загружает список пользователей из users.json."""
        raw_users = load_json(USERS_FILE, [])
        return [User.from_dict(item) for item in raw_users]

    def _save_users(self, users: list[User]) -> None:
        """Сохраняет список пользователей в users.json."""
        save_json(USERS_FILE, [u.to_dict() for u in users])

    def _load_portfolio(self, user: User) -> Portfolio:
        """Загружает портфель пользователя из portfolios.json или создаёт новый."""
        raw_portfolios = load_json(PORTFOLIOS_FILE, [])
        for item in raw_portfolios:
            if int(item.get("user_id", -1)) == user.user_id:
                return Portfolio.from_dict(item, user=user)
        return Portfolio(user_id=user.user_id, wallets={}, user=user)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        """Обновляет или добавляет портфель пользователя в portfolios.json."""
        raw_portfolios = load_json(PORTFOLIOS_FILE, [])
        updated = False
        for idx, item in enumerate(raw_portfolios):
            if int(item.get("user_id", -1)) == portfolio.user_id:
                raw_portfolios[idx] = portfolio.to_dict()
                updated = True
                break
        if not updated:
            raw_portfolios.append(portfolio.to_dict())
        save_json(PORTFOLIOS_FILE, raw_portfolios)

    def register(self, username: str, password: str) -> str:
        """Регистрирует нового пользователя и создаёт для него пустой портфель."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        clean_username = username.strip()

        users = self._load_users()
        if any(u.username.lower() == clean_username.lower() for u in users):
            raise ValueError(f"Имя пользователя '{clean_username}' уже занято")

        next_id = max((u.user_id for u in users), default=0) + 1
        new_user = User.create(user_id=next_id, username=clean_username, password=password)

        users.append(new_user)
        self._save_users(users)

        empty_portfolio = Portfolio(user_id=new_user.user_id, wallets={}, user=new_user)
        self._save_portfolio(empty_portfolio)

        return (
            f"Пользователь '{clean_username}' зарегистрирован (id={new_user.user_id}). "
            f"Войдите: login --username {clean_username} --password ****"
        )

    def login(self, username: str, password: str) -> str:
        """Выполняет вход пользователя в систему."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        clean_username = username.strip()

        users = self._load_users()
        user = next((u for u in users if u.username == clean_username), None)
        if user is None:
            raise ValueError(f"Пользователь '{clean_username}' не найден")

        if not user.verify_password(password):
            raise ValueError("Неверный пароль")

        self._current_user = user
        return f"Вы вошли как '{user.username}'"

    def show_portfolio(self, base_currency: str = "USD") -> str:
        """Возвращает отформатированное состояние портфеля и общую стоимость в базовой валюте."""
        user = self._require_auth()
        base = validate_currency_code(base_currency)

        rates_data = get_or_refresh_rates()
        flat_rates = extract_flat_rates(rates_data)

        supported_currencies = {"USD"} | set(DEFAULT_RATES_TO_USD.keys())
        for key in flat_rates:
            parts = key.split("_")
            if len(parts) == 2:
                supported_currencies.update(parts)

        if base not in supported_currencies:
            raise ValueError(f"Неизвестная базовая валюта '{base}'")

        portfolio = self._load_portfolio(user)
        wallets = portfolio.wallets

        if not wallets:
            return f"Портфель пользователя '{user.username}' пуст."

        lines = [f"Портфель пользователя '{user.username}' (база: {base}):"]
        for code, wallet in wallets.items():
            rate, _, _ = resolve_pair_rate(code, base, rates_data)
            converted = wallet.balance * rate
            amount_fmt = f"{wallet.balance:.2f}" if code in {"USD", "EUR", "RUB"} \
            else f"{wallet.balance:.4f}"
            lines.append(f"- {code}: {amount_fmt}  → {converted:.2f} {base}")

        total = portfolio.get_total_value(base_currency=base, exchange_rates=flat_rates)
        lines.append("---------------------------------")
        lines.append(f"ИТОГО: {total:,.2f} {base}")
        return "\n".join(lines)

    def buy(self, currency_code: str, amount: float | str) -> str:
        """Покупает указанное количество валюты и обновляет портфель пользователя."""
        user = self._require_auth()
        code = validate_currency_code(currency_code)
        qty = validate_amount(amount)

        rates_data = get_or_refresh_rates()
        try:
            rate, _, _ = resolve_pair_rate(code, "USD", rates_data)
        except ValueError as exc:
            raise ValueError(f"Не удалось получить курс для {code}→USD") from exc

        estimated_cost_usd = qty * rate
        portfolio = self._load_portfolio(user)

        # Если у пользователя есть USD-кошелёк и мы покупаем другую валюту, списываем USD
        usd_wallet = portfolio.get_wallet("USD")
        if code != "USD" and usd_wallet is not None and usd_wallet.balance > 0:
            if usd_wallet.balance < estimated_cost_usd:
                raise ValueError(
                    f"Недостаточно средств: доступно {usd_wallet.balance:.4f} USD, "
                    f"требуется {estimated_cost_usd:.4f} USD"
                )
            usd_wallet.withdraw(estimated_cost_usd)

        wallet = portfolio.get_wallet(code)
        if wallet is None:
            wallet = portfolio.add_currency(code)

        old_balance = wallet.balance
        wallet.deposit(qty)
        new_balance = wallet.balance

        self._save_portfolio(portfolio)

        return (
            f"Покупка выполнена: {qty:.4f} {code} по курсу {rate:.2f} USD/{code}\n"
            f"Изменения в портфеле:\n"
            f"- {code}: было {old_balance:.4f} → стало {new_balance:.4f}\n"
            f"Оценочная стоимость покупки: {estimated_cost_usd:,.2f} USD"
        )

    def sell(self, currency_code: str, amount: float | str) -> str:
        """Продаёт указанную валюту из портфеля и начисляет выручку в USD."""
        user = self._require_auth()
        code = validate_currency_code(currency_code)
        qty = validate_amount(amount)

        portfolio = self._load_portfolio(user)
        wallet = portfolio.get_wallet(code)
        if wallet is None:
            raise ValueError(
                f"У вас нет кошелька '{code}'. "
                "Добавьте валюту: она создаётся автоматически при первой покупке."
            )

        rates_data = get_or_refresh_rates()
        try:
            rate, _, _ = resolve_pair_rate(code, "USD", rates_data)
        except ValueError as exc:
            raise ValueError(f"Не удалось получить курс для {code}→USD") from exc

        old_balance = wallet.balance
        wallet.withdraw(qty)
        new_balance = wallet.balance

        estimated_revenue_usd = qty * rate

        # Начисляем выручку на USD-кошелёк, если продавалась не USD
        if code != "USD":
            usd_wallet = portfolio.get_wallet("USD")
            if usd_wallet is None:
                usd_wallet = portfolio.add_currency("USD")
            usd_wallet.deposit(estimated_revenue_usd)

        self._save_portfolio(portfolio)

        return (
            f"Продажа выполнена: {qty:.4f} {code} по курсу {rate:.2f} USD/{code}\n"
            f"Изменения в портфеле:\n"
            f"- {code}: было {old_balance:.4f} → стало {new_balance:.4f}\n"
            f"Оценочная выручка: {estimated_revenue_usd:,.2f} USD"
        )

    def get_rate(self, from_currency: str, to_currency: str) -> str:
        """Возвращает текущий и обратный курс между двумя валютами с проверкой TTL кеша."""
        src = validate_currency_code(from_currency)
        dst = validate_currency_code(to_currency)

        rates_data = get_or_refresh_rates()
        try:
            rate, updated_at_iso, is_fresh = resolve_pair_rate(src, dst, rates_data)
        except ValueError as exc:
            raise ValueError(f"Курс {src}→{dst} недоступен. Повторите попытку позже.") from exc

        if not is_fresh:
            # Обновляем метку времени из резервного источника/заглушки, если кеш устарел
            now_iso = datetime.now().replace(microsecond=0).isoformat()
            pair_key = f"{src}_{dst}"
            if pair_key in rates_data and isinstance(rates_data[pair_key], dict):
                rates_data[pair_key]["updated_at"] = now_iso
            rates_data["last_refresh"] = now_iso
            save_json(RATES_FILE, rates_data)
            updated_at_iso = now_iso

        formatted_time = updated_at_iso.replace("T", " ")
        reverse_rate = 1.0 / rate if rate > 0 else 0.0

        rate_str = f"{rate:.8f}".rstrip("0").rstrip(".") if rate < 0.01 else f"{rate:.4f}"
        rev_str = f"{reverse_rate:.2f}" if reverse_rate >= 1 else \
        f"{reverse_rate:.8f}".rstrip("0").rstrip(".")

        return (
            f"Курс {src}→{dst}: {rate_str} (обновлено: {formatted_time})\n"
            f"Обратный курс {dst}→{src}: {rev_str}"
        )
