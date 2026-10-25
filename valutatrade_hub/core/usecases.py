"""Бизнес-логика (use cases) основного сервиса ValutaTrade Hub."""

from __future__ import annotations

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    extract_flat_rates,
    get_or_refresh_rates,
    get_pairs_dict,
    resolve_pair_rate,
    validate_amount,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import RatesUpdater


class TradingUseCases:
    """Оркестратор бизнес-операций пользователя, портфеля и курсов валют."""

    def __init__(self) -> None:
        """Инициализирует сервис, менеджер БД, настройки и текущую сессию."""
        self._current_user: User | None = None
        self._db = DatabaseManager()
        self._settings = SettingsLoader()

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
        """Загружает список пользователей через DatabaseManager."""
        raw_users = self._db.load_users_data()
        return [User.from_dict(item) for item in raw_users]

    def _save_users(self, users: list[User]) -> None:
        """Сохраняет список пользователей через DatabaseManager."""
        self._db.save_users_data([u.to_dict() for u in users])

    def _load_portfolio(self, user: User) -> Portfolio:
        """Загружает портфель пользователя через DatabaseManager или создаёт новый."""
        raw_portfolios = self._db.load_portfolios_data()
        for item in raw_portfolios:
            if int(item.get("user_id", -1)) == user.user_id:
                return Portfolio.from_dict(item, user=user)
        return Portfolio(user_id=user.user_id, wallets={}, user=user)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        """Обновляет или добавляет портфель пользователя через DatabaseManager."""
        raw_portfolios = self._db.load_portfolios_data()
        updated = False
        for idx, item in enumerate(raw_portfolios):
            if int(item.get("user_id", -1)) == portfolio.user_id:
                raw_portfolios[idx] = portfolio.to_dict()
                updated = True
                break
        if not updated:
            raw_portfolios.append(portfolio.to_dict())
        self._db.save_portfolios_data(raw_portfolios)

    @log_action(action="REGISTER")
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

    @log_action(action="LOGIN")
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

    def show_portfolio(self, base_currency: str | None = None) -> str:
        """Возвращает состояние портфеля и общую стоимость в базовой валюте."""
        user = self._require_auth()
        default_base = str(self._settings.get("DEFAULT_BASE_CURRENCY", "USD"))
        base_curr_obj = get_currency(base_currency or default_base)
        base = base_curr_obj.code

        rates_data = get_or_refresh_rates()
        flat_rates = extract_flat_rates(rates_data)

        portfolio = self._load_portfolio(user)
        wallets = portfolio.wallets

        if not wallets:
            return f"Портфель пользователя '{user.username}' пуст."

        lines = [f"Портфель пользователя '{user.username}' (база: {base}):"]
        for code, wallet in wallets.items():
            rate, _, _ = resolve_pair_rate(code, base, rates_data)
            converted = wallet.balance * rate
            amount_fmt = (
                f"{wallet.balance:.2f}"
                if code in {"USD", "EUR", "RUB", "GBP"}
                else f"{wallet.balance:.4f}"
            )
            lines.append(f"- {code}: {amount_fmt}  → {converted:.2f} {base}")

        total = portfolio.get_total_value(base_currency=base, exchange_rates=flat_rates)
        lines.append("---------------------------------")
        lines.append(f"ИТОГО: {total:,.2f} {base}")
        return "\n".join(lines)

    @log_action(action="BUY", verbose=True)
    def buy(self, currency_code: str, amount: float | str) -> str:
        """Покупает указанное количество валюты и обновляет портфель пользователя."""
        user = self._require_auth()
        qty = validate_amount(amount)
        currency = get_currency(currency_code)
        code = currency.code

        rates_data = get_or_refresh_rates()
        rate, _, _ = resolve_pair_rate(code, "USD", rates_data)

        estimated_cost_usd = qty * rate
        portfolio = self._load_portfolio(user)

        usd_wallet = portfolio.get_wallet("USD")
        if code != "USD" and usd_wallet is not None and usd_wallet.balance > 0:
            if usd_wallet.balance < estimated_cost_usd:
                raise InsufficientFundsError(
                    available=usd_wallet.balance,
                    required=estimated_cost_usd,
                    code="USD",
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

    @log_action(action="SELL", verbose=True)
    def sell(self, currency_code: str, amount: float | str) -> str:
        """Продаёт указанную валюту из портфеля и начисляет выручку в USD."""
        user = self._require_auth()
        qty = validate_amount(amount)
        currency = get_currency(currency_code)
        code = currency.code

        portfolio = self._load_portfolio(user)
        wallet = portfolio.get_wallet(code)
        if wallet is None:
            raise ValueError(
                f"У вас нет кошелька '{code}'. "
                "Добавьте валюту: она создаётся автоматически при первой покупке."
            )

        rates_data = get_or_refresh_rates()
        rate, _, _ = resolve_pair_rate(code, "USD", rates_data)

        old_balance = wallet.balance
        wallet.withdraw(qty)
        new_balance = wallet.balance

        estimated_revenue_usd = qty * rate

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
        """Возвращает текущий и обратный курс между двумя валютами с проверкой TTL."""
        src_curr = get_currency(from_currency)
        dst_curr = get_currency(to_currency)
        src, dst = src_curr.code, dst_curr.code

        rates_data = get_or_refresh_rates()
        rate, updated_at_iso, is_fresh = resolve_pair_rate(src, dst, rates_data)

        formatted_time = updated_at_iso.replace("T", " ").replace("Z", "")
        reverse_rate = 1.0 / rate if rate > 0 else 0.0

        rate_str = f"{rate:.8f}".rstrip("0").rstrip(".") if rate < 0.01 else f"{rate:.4f}"
        rev_str = (
            f"{reverse_rate:.2f}"
            if reverse_rate >= 1
            else f"{reverse_rate:.8f}".rstrip("0").rstrip(".")
        )

        lines = [
            f"Курс {src}→{dst}: {rate_str} (обновлено: {formatted_time})",
            f"Обратный курс {dst}→{src}: {rev_str}",
        ]
        if not is_fresh:
            lines.append(
                "Внимание: данные в локальном кэше устарели (превышен TTL). "
                "Выполните 'update-rates' для получения свежих котировок."
            )
        return "\n".join(lines)

    def update_rates(self, source: str | None = None) -> str:
        """Запускает немедленное обновление курсов через Parser Service."""
        updater = RatesUpdater()
        return updater.run_update(source_filter=source)

    def show_rates(
        self,
        currency: str | None = None,
        top: int | None = None,
        base: str | None = None,
    ) -> str:
        """Выводит список курсов из локального кеша с поддержкой фильтрации и сортировки."""
        rates_data = self._db.load_rates_data()
        pairs = get_pairs_dict(rates_data)
        if not pairs:
            raise ValueError(
                "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
            )

        last_refresh = str(rates_data.get("last_refresh", "unknown"))
        base_code = validate_base_or_default(base)

        items: list[tuple[str, float, str, str]] = []
        for pair_key, info in pairs.items():
            if not isinstance(info, dict) or "rate" not in info:
                continue
            src_code = pair_key.split("_")[0].upper()
            rate_usd = float(info["rate"])
            updated_at = str(info.get("updated_at", last_refresh))
            source_name = str(info.get("source", "Cache"))

            if base_code != "USD":
                base_rate, _, _ = resolve_pair_rate(src_code, base_code, rates_data)
                final_rate = base_rate
                display_pair = f"{src_code}_{base_code}"
            else:
                final_rate = rate_usd
                display_pair = pair_key

            items.append((display_pair, final_rate, updated_at, source_name))

        if currency:
            target = currency.strip().upper()
            items = [it for it in items if it[0].startswith(f"{target}_")]
            if not items:
                raise ValueError(f"Курс для '{target}' не найден в кеше.")

        if top is not None:
            if top <= 0:
                raise ValueError("Параметр '--top' должен быть положительным целым числом")
            crypto_items: list[tuple[str, float, str, str]] = []
            for it in items:
                ticker = it[0].split("_")[0]
                try:
                    curr_obj = get_currency(ticker)
                    if isinstance(curr_obj, CryptoCurrency):
                        crypto_items.append(it)
                except CurrencyNotFoundError:
                    continue
            crypto_items.sort(key=lambda x: x[1], reverse=True)
            items = crypto_items[:top]
        else:
            items.sort(key=lambda x: x[0])

        header = f"Rates from cache (updated at {last_refresh}):"
        bullet_lines = [header]
        table = PrettyTable()
        table.field_names = ["Pair", "Rate", "Updated At", "Source"]
        table.align["Pair"] = "l"
        table.align["Rate"] = "r"

        for pair_name, rate_val, upd, src_name in items:
            fmt_rate = (
                f"{rate_val:.5f}".rstrip("0").rstrip(".") if rate_val < 1 else f"{rate_val:.2f}"
            )
            bullet_lines.append(f"- {pair_name}: {fmt_rate}")
            table.add_row([pair_name, fmt_rate, upd, src_name])

        return "\n".join(bullet_lines) + "\n\n" + table.get_string()


def validate_base_or_default(base: str | None) -> str:
    """Валидирует базовую валюту для show-rates или возвращает USD."""
    if not base:
        return "USD"
    curr = get_currency(base)
    return curr.code
