# tgmon

CLI-инструмент для мониторинга Telegram чатов с пересылкой сообщений в агрегатор.

## Установка

```bash
pip install -e .
```

## Использование

### 1. Инициализация

```bash
tgmon init
```

Создаст папку `.tgmon/` в текущей директории с базой данных.

### 2. Добавление аккаунта

Получите `api_id` и `api_hash` на https://my.telegram.org/apps

```bash
tgmon account add myaccount --api-id 12345678 --api-hash abcdef1234567890
```

### 3. Авторизация

```bash
tgmon account login myaccount
```

Введите номер телефона, затем код из Telegram (и 2FA пароль, если есть).

### 4. Настройка агрегатора

Агрегатор — чат, куда будут пересылаться сообщения:

```bash
tgmon aggregator set --chat @my_private_channel --via myaccount
tgmon aggregator set --chat=-1001234567890 --via myaccount   # по ID
```

### 5. Добавление чатов для мониторинга

```bash
tgmon watch add myaccount --chat @news_channel
tgmon watch add myaccount --chat @another_chat
tgmon watch add myaccount --chat=-1001234567890   # по ID
```

### 6. Запуск мониторинга

```bash
tgmon run myaccount      # один аккаунт
tgmon run-all            # все enabled аккаунты
```

Остановка — `Ctrl+C`.

## Команды

### account

```bash
tgmon account add <name> --api-id <id> --api-hash <hash>   # добавить аккаунт
tgmon account login <name>                                  # авторизация
tgmon account list                                          # список аккаунтов
tgmon account dialogs <name>                                # группы и каналы с ID
tgmon account dialogs <name> --users                        # личные чаты
tgmon account dialogs <name> --limit 100                    # больше результатов
tgmon account enable <name>                                 # включить
tgmon account disable <name>                                # отключить
tgmon account remove <name> [--keep-session]                # удалить
```

### aggregator

```bash
tgmon aggregator set --chat <chat_ref> --via <account>   # установить агрегатор
tgmon aggregator show                                     # показать текущий
```

### watch

```bash
tgmon watch add <account> --chat <chat_ref>   # добавить чат
tgmon watch list <account>                    # список чатов
tgmon watch enable <account> <watch_id>       # включить
tgmon watch disable <account> <watch_id>      # отключить
tgmon watch remove <account> <watch_id>       # удалить
```

### run

```bash
tgmon run <account>   # запуск для одного аккаунта
tgmon run-all         # запуск для всех enabled аккаунтов
```

### web

```bash
tgmon web                          # запуск веб-интерфейса на http://127.0.0.1:5000
tgmon web --host 0.0.0.0           # доступ из сети
tgmon web --port 8080              # другой порт
tgmon web --debug                  # режим отладки
```

## Веб-интерфейс

Веб-интерфейс предоставляет удобное управление всеми функциями tgmon через браузер.

### Возможности

- **Dashboard** — статистика: количество аккаунтов, watches, статус агрегатора и монитора
- **Accounts** — управление Telegram аккаунтами:
  - Добавление аккаунтов с API credentials
  - Авторизация (телефон → код → 2FA)
  - Включение/отключение/удаление
  - Просмотр статуса авторизации
- **Watches** — управление отслеживаемыми чатами:
  - Добавление нескольких чатов сразу
  - Поиск и пагинация по диалогам
  - Включение/отключение/удаление
  - Групповое включение/отключение по аккаунту
- **Aggregator** — настройка чата для пересылки:
  - Выбор чата из списка групп/каналов
  - Выбор аккаунта для отправки
- **Monitor** — управление мониторингом:
  - Запуск/остановка
  - Просмотр логов в реальном времени (SSE)

## Формат сообщений в агрегаторе

```
• Имя Отправителя

Текст сообщения или [Фото]/[Видео]/[Документ]

Ссылка: https://t.me/channel/123
```

- Ссылка добавляется только для публичных чатов
- Медиа-файлы пересылаются с caption
- Превью ссылок отключено

## Хранение данных

- `.tgmon/tgmon.db` — база данных SQLite
- `.tgmon/sessions/` — сессии Telegram

## Зависимости

- **Telethon** — Telegram MTProto API
- **Flask** — веб-фреймворк
- **aiosqlite** — асинхронная работа с SQLite
- **Typer** — CLI фреймворк
- **Pydantic** — валидация данных
