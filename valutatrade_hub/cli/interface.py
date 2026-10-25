"""Командный интерфейс (CLI) платформы ValutaTrade Hub."""

from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Sequence

from valutatrade_hub.core.currencies import get_supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import TradingUseCases


class CliArgumentParser(argparse.ArgumentParser):
    """Парсер аргументов, выбрасывающий ValueError вместо завершения процесса."""

    def error(self, message: str) -> None:
        """Перехватывает ошибки парсинга аргументов."""
        raise ValueError(f"Ошибка аргументов командной строки: {message}")


def build_parser() -> CliArgumentParser:
    """Создаёт и настраивает парсер всех CLI-команд."""
    parser = CliArgumentParser(
        prog="valutatrade",
        description="CLI платформы отслеживания и симуляции торговли валютами",
        add_help=True,
    )
    subparsers = parser.add_subparsers(dest="command")

    # 1. register
    reg_parser = subparsers.add_parser("register", help="Зарегистрировать нового пользователя")
    reg_parser.add_argument("--username", required=True, type=str, help="Имя пользователя")
    reg_parser.add_argument("--password", required=True, type=str, help="Пароль (минимум 4 символа)")

    # 2. login
    login_parser = subparsers.add_parser("login", help="Войти в систему")
    login_parser.add_argument("--username", required=True, type=str, help="Имя пользователя")
    login_parser.add_argument("--password", required=True, type=str, help="Пароль")

    # 3. show-portfolio
    port_parser = subparsers.add_parser("show-portfolio", help="Показать портфель и балансы")
    port_parser.add_argument("--base", default="USD", type=str, help="Базовая валюта (по умолчанию USD)")

    # 4. buy
    buy_parser = subparsers.add_parser("buy", help="Купить валюту")
    buy_parser.add_argument("--currency", required=True, type=str, help="Код покупаемой валюты")
    buy_parser.add_argument("--amount", required=True, type=str, help="Количество покупаемой валюты")

    # 5. sell
    sell_parser = subparsers.add_parser("sell", help="Продать валюту")
    sell_parser.add_argument("--currency", required=True, type=str, help="Код продаваемой валюты")
    sell_parser.add_argument("--amount", required=True, type=str, help="Количество продаваемой валюты")

    # 6. get-rate
    rate_parser = subparsers.add_parser("get-rate", help="Получить курс валюты")
    rate_parser.add_argument(
        "--from", dest="from_currency", required=True, type=str, help="Исходная валюта"
    )
    rate_parser.add_argument(
        "--to", dest="to_currency", required=True, type=str, help="Целевая валюта"
    )

    # Вспомогательные команды интерактивного режима
    subparsers.add_parser("help", help="Показать список команд")
    subparsers.add_parser("exit", help="Выйти из программы")
    subparsers.add_parser("quit", help="Выйти из программы")

    return parser


def execute_command(
    tokens: Sequence[str],
    usecases: TradingUseCases,
    parser: CliArgumentParser,
) -> bool:
    """Выполняет одну команду CLI. Возвращает False, если запрошен выход."""
    if not tokens:
        return True

    try:
        args = parser.parse_args(tokens)
    except SystemExit:
        return True
    except ValueError as exc:
        print(exc)
        return True

    cmd = args.command
    if cmd in {"exit", "quit"}:
        print("Выход из ValutaTrade Hub.")
        return False

    if cmd == "help" or cmd is None:
        parser.print_help()
        return True

    try:
        if cmd == "register":
            print(usecases.register(username=args.username, password=args.password))
        elif cmd == "login":
            print(usecases.login(username=args.username, password=args.password))
        elif cmd == "show-portfolio":
            print(usecases.show_portfolio(base_currency=args.base))
        elif cmd == "buy":
            print(usecases.buy(currency_code=args.currency, amount=args.amount))
        elif cmd == "sell":
            print(usecases.sell(currency_code=args.currency, amount=args.amount))
        elif cmd == "get-rate":
            print(usecases.get_rate(from_currency=args.from_currency, to_currency=args.to_currency))
    except InsufficientFundsError as exc:
        print(exc)
    except CurrencyNotFoundError as exc:
        supported = ", ".join(get_supported_codes())
        print(
            f"{exc}. Поддерживаемые коды валют: {supported}. "
            "Используйте 'get-rate --help' для справки."
        )
    except ApiRequestError as exc:
        print(f"{exc}. Пожалуйста, повторите попытку позже или проверьте подключение к сети.")
    except (ValueError, PermissionError, TypeError) as exc:
        print(exc)

    return True


def run_cli(argv: Sequence[str] | None = None) -> None:
    """Точка входа CLI: поддерживает однократный вызов и интерактивный цикл (REPL)."""
    usecases = TradingUseCases()
    parser = build_parser()
    args_list = list(argv if argv is not None else sys.argv[1:])

    if args_list:
        execute_command(args_list, usecases, parser)
        return

    print("Добро пожаловать в ValutaTrade Hub CLI! Введите 'help' для списка команд или 'exit' для выхода.")
    while True:
        try:
            raw_line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход из ValutaTrade Hub.")
            break

        if not raw_line:
            continue

        try:
            tokens = shlex.split(raw_line)
        except ValueError as exc:
            print(f"Ошибка разбора строки: {exc}")
            continue

        should_continue = execute_command(tokens, usecases, parser)
        if not should_continue:
            break