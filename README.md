# ValutaTrade Hub

Комплексная платформа на Python для отслеживания котировок и симуляции торговли фиатными и криптовалютами в реальном времени.

Система состоит из двух взаимодействующих сервисов:
1. **Core Service** — управление пользователями, виртуальными портфелями, кошельками, сделками покупки/продажи (`buy`/`sell`) и командным интерфейсом (CLI).
2. **Parser Service** — отказоустойчивый сервис сбора актуальных курсов из внешних API (**CoinGecko** для криптовалют и **ExchangeRate-API** для фиатных валют) с ведением локального кэша (`data/rates.json`) и исторического журнала (`data/exchange_rates.json`).

---

## Структура проекта

```text
finalproject_Petrov_M26-555/
├── data/
│   ├── users.json             # Зарегистрированные пользователи (SHA-256 + salt)
│   ├── portfolios.json        # Портфели и балансы кошельков пользователей
│   ├── rates.json             # Локальный срез актуальных курсов для Core Service
│   └── exchange_rates.json    # Исторический журнал всех замеров Parser Service
├── logs/
│   ├── actions.log            # Логи доменных операций (@log_action) с ротацией
│   └── parser.log             # Журнал работы Parser Service
├── valutatrade_hub/
│   ├── __init__.py
│   ├── logging_config.py      # Настройка логгера и RotatingFileHandler
│   ├── decorators.py          # Декоратор @log_action
│   ├── core/
│   │   ├── currencies.py      # Иерархия Currency -> FiatCurrency / CryptoCurrency
│   │   ├── exceptions.py      # InsufficientFundsError, CurrencyNotFoundError, ApiRequestError
│   │   ├── models.py          # Модели User, Wallet, Portfolio
│   │   ├── usecases.py        # Бизнес-логика команд
│   │   └── utils.py           # Валидаторы и расчёт кросс-курсов / TTL
│   ├── infra/
│   │   ├── settings.py        # Singleton SettingsLoader
│   │   └── database.py        # Singleton DatabaseManager (атомарная запись JSON)
│   ├── parser_service/
│   │   ├── config.py          # Конфигурация ParserConfig
│   │   ├── api_clients.py     # BaseApiClient, CoinGeckoClient, ExchangeRateApiClient
│   │   ├── storage.py         # Управление rates.json и exchange_rates.json
│   │   ├── updater.py         # Координатор обновления RatesUpdater
│   │   └── scheduler.py       # Фоновый планировщик обновлений RatesScheduler
│   └── cli/
│       └── interface.py       # Точка входа CLI и обработка команд
├── main.py                    # Точка входа приложения
├── pyproject.toml             # Зависимости, конфигурация Ruff и [tool.valutatrade]
└── README.md
```

---

## Установка и запуск

Требования: **Python 3.11+** и пакетный менеджер **[uv](https://docs.astral.sh/uv/)**.

1. Клонируйте репозиторий и перейдите в папку проекта:
   ```bash
   git clone <URL_репозитория>
   cd finalproject_Petrov_M26-555
   ```
2. Установите зависимости:
   ```bash
   uv sync
   ```
3. Запустите интерактивный режим CLI:
   ```bash
   uv run python main.py
   ```
4. Проверка стиля кода линтером Ruff:
   ```bash
   uv run ruff check .
   ```

---

## Настройка Parser Service и API-ключа

- **CoinGecko** (криптовалюты `BTC`, `ETH`, `SOL`) работает через публичный эндпоинт без ключа.
- **ExchangeRate-API** (фиатные валюты `EUR`, `GBP`, `RUB`) требует бесплатный API-ключ с сайта [exchangerate-api.com](https://www.exchangerate-api.com/).

Сохраните ваш ключ в файле `.env` в корне проекта (файл добавлен в `.gitignore`):
```env
EXCHANGERATE_API_KEY="ваш_ключ_здесь"
```
Либо экспортируйте переменную окружения в терминале перед запуском:
```bash
export EXCHANGERATE_API_KEY="ваш_ключ_здесь"
```

---

## Кэширование и политика TTL

- Все котировки кешируются в файле `data/rates.json`.
- Срок годности кэша (`rates_ttl_seconds`) задаётся в секции `[tool.valutatrade]` файла `pyproject.toml` (по умолчанию **300 секунд / 5 минут**) и загружается через синглтон `SettingsLoader`.
- Если при вызове `get-rate` данные старше порога TTL, система предупреждает пользователя о необходимости выполнить `update-rates`.
- Запись в `rates.json` и `exchange_rates.json` выполняется атомарно через временный `.tmp` файл.

---

## Примеры команд CLI

```text
> register --username alice --password 1234
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****

> login --username alice --password 1234
Вы вошли как 'alice'

> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2026-10-25T15:30:00Z

> show-rates --top 2
Rates from cache (updated at 2026-10-25T15:30:00Z):
- BTC_USD: 59337.21
- ETH_USD: 3720.00

> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
Оценочная стоимость покупки: 2,966.86 USD

> sell --currency BTC --amount 0.01
Продажа выполнена: 0.0100 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0500 → стало 0.0400
Оценочная выручка: 593.37 USD

> show-portfolio
Портфель пользователя 'alice' (база: USD):
- BTC: 0.0400  → 2373.49 USD
- USD: 593.37  → 593.37 USD
---------------------------------
ИТОГО: 2,966.86 USD

> get-rate --from USD --to BTC
Курс USD→BTC: 0.00001685 (обновлено: 2026-10-25 15:30:00)
Обратный курс BTC→USD: 59337.21
```

## Демонстрация работы системы (CLI Session Log)

Ниже зафиксирован полный протокол интерактивной сессии командной строки (эквивалент записи asciinema), демонстрирующий регистрацию, аутентификацию, работу парсера котировок, торговые операции и перехват исключений.

```text
$ uv run python main.py
Добро пожаловать в ValutaTrade Hub CLI! Введите 'help' для списка команд или 'exit' для выхода.

> register --username demo_user --password 1234
Пользователь 'demo_user' зарегистрирован (id=1). Войдите: login --username demo_user --password ****

> login --username demo_user --password 1234
Вы вошли как 'demo_user'

> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2026-10-25T15:30:00Z

> show-rates --top 2
Rates from cache (updated at 2026-10-25T15:30:00Z):
- BTC_USD: 59337.21
- ETH_USD: 3720.00

+---------+----------+----------------------+-----------+
| Pair    |     Rate | Updated At           | Source    |
+---------+----------+----------------------+-----------+
| BTC_USD | 59337.21 | 2026-10-25T15:30:00Z | CoinGecko |
| ETH_USD |  3720.00 | 2026-10-25T15:30:00Z | CoinGecko |
+---------+----------+----------------------+-----------+

> show-rates --currency RUB
Rates from cache (updated at 2026-10-25T15:30:00Z):
- RUB_USD: 0.01016

+---------+---------+----------------------+------------------+
| Pair    |    Rate | Updated At           | Source           |
+---------+---------+----------------------+------------------+
| RUB_USD | 0.01016 | 2026-10-25T15:30:00Z | ExchangeRate-API |
+---------+---------+----------------------+------------------+

> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
Оценочная стоимость покупки: 2,966.86 USD

> sell --currency BTC --amount 0.01
Продажа выполнена: 0.0100 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0500 → стало 0.0400
Оценочная выручка: 593.37 USD

> show-portfolio
Портфель пользователя 'demo_user' (база: USD):
- BTC: 0.0400  → 2373.49 USD
- USD: 593.37  → 593.37 USD
---------------------------------
ИТОГО: 2,966.86 USD

> get-rate --from USD --to BTC
Курс USD→BTC: 0.00001685 (обновлено: 2026-10-25 15:30:00)
Обратный курс BTC→USD: 59337.21

> sell --currency BTC --amount 100
Недостаточно средств: доступно 0.0400 BTC, требуется 100.0000 BTC

> get-rate --from USD --to UNKNOWN
Неизвестная валюта 'UNKNOWN'. Поддерживаемые коды валют: BTC, ETH, EUR, GBP, RUB, SOL, USD. Используйте 'get-rate --help' для справки.

> exit
Выход из ValutaTrade Hub.
```