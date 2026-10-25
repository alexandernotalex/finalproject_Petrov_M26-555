"""Точка входа приложения ValutaTrade Hub."""

from __future__ import annotations

from valutatrade_hub.cli.interface import run_cli


def main() -> None:
    """Запускает CLI интерфейс платформы."""
    run_cli()


if __name__ == "__main__":
    main()
