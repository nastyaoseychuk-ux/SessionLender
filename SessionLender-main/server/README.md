# SessionLender — сервер

Django-застосунок (Channels + ASGI) для спільнот, кімнат, дописів, особистих і групових чатів, сповіщень та аудиту дій. Надсилання повідомлень має ідемпотентні ключі, автоматичні повтори і HTTP-fallback; вкладення обслуговуються лише через захищений проксій-View з перевіркою учасника.

Хмарна конфігурація: Vercel ASGI, PostgreSQL/Neon, Redis (Upstash) та Vercel Blob із **приватним доступом** (файли віддаються короткодіючими signed `download_url`, старі публічні об'єкти залишаються читабельними). Для локальної розробки — SQLite й uvicorn.

## Realtime-архітектура (рішення)

- **Vercel (prod):** serverless-функції не тримають WebSocket-з'єднання. Чати працюють через HTTP-polling (`/messages/<id>/poll/`, крок 3 с у `chat.js`), а лічильник непрочитаних у `inbox.js` після 3 невдалих спроб WS автоматично перемикається на опитування `/messages/unread-count/` кожні 30 с.
- **Self-host / локальний `main.py` (uvicorn + daphne/channels + Redis):** повноцінні WebSocket `/ws/chat/<id>/` і `/ws/inbox/` з fallback на той самий HTTP-шлях. Логіка доставки в `messenger/delivery.py` не ламається при відсутності relay.

Тобто WS — оптимізація, а не вимога: весь функціонал чатів працює і без нього.

## Запуск локально (PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Адреса: http://127.0.0.1:8000. Для звичайного локального тестування не використовуйте production `.env.local`.

## Тести

```powershell
$env:DJANGO_SETTINGS_MODULE='sessionlender.settings'
.\.venv\Scripts\python.exe manage.py test messenger
```

116 тестів: чати й вкладення (`tests_chat`), групи та аудит груп (`test_groups`), сповіщення/health/cleanup (`test_new_features`), throttling HTTP-view (`test_throttling`), запрошення (`test_invitations`), надійна доставка (`test_delivery`), основні сценарії (`tests`). У test-режимі rate limiting обходиться через `settings.TEST`; окремі тести перевіряють throttling через `override_settings(TEST=False)`.

## Rate limiting

Кеш (LocMem / django-redis) на IP+користувача, фіксоване вікно. Змінні середовища:

| Ефект | Змінні | За замовчуванням |
|---|---|---|
| HTTP + WS повідомлення | `MESSAGE_RATE_LIMIT` / `MESSAGE_RATE_WINDOW` | 30 / 60 с |
| Коментарі та дописи | `COMMENT_RATE_LIMIT` / `COMMENT_RATE_WINDOW` | 20 / 60 с |
| Створення кімнат | `ROOM_CREATE_RATE_LIMIT` / `ROOM_CREATE_RATE_WINDOW` | 5 / 3600 с |
| Завантаження вкладень | `UPLOAD_RATE_LIMIT` / `UPLOAD_RATE_WINDOW` | 10 / 60 с |
| Підбір пароля | `LOGIN_FAILURE_LIMIT` / `LOGIN_LOCKOUT_SECONDS` | 5 / 900 с |

## Приватність вкладень

- `ChatAttachment` зберігається у Vercel Blob з `access="private"`.
- Шаблони й WS-публікації посилаються лише на `/messages/attachments/<id>/` (`views.chat_attachment`) — view вимагає вхід учасника чату, віддає `FileResponse` з `nosniff` і `Cache-Control: private, no-store`.
- Аватари/зображення дописів через `storage.url()` отримують короткодіючий signed `download_url`; у payload чатів аватар — редірект-ендпоінт `/people/<id>/avatar/` без викликів Blob API.
- HTML-файли заборонені до завантаження; підписи файлів не є публічними URL.

## Моніторинг

- **Health-check:** `GET /health/` (і `/healthz/`) без автентифікації; JSON `{"status":"ok","db":"ok"}` або `degraded` при недоступній БД.
- **Sentry:** ініціалізується, якщо встановлено `sentry-sdk` і задано `SENTRY_DSN` (або `DJANGO_SENTRY_DSN`). `SENTRY_TRACES_SAMPLE_RATE=0` за замовчуванням, `send_default_pii=False`.
- **Structured logging:** `LOGGING` у `sessionlender/settings.py` пише JSON у stdout (`messenger.logging_config.JsonFormatter`), рівень через `LOG_LEVEL`.

## Сповіщення

- Пагінація 50/сторінку з навігацією; кнопка «Прибрати старі (30 днів)» видаляє власні сповіщення старіші 30 днів.
- Фонове очищення: `python manage.py cleanup_notifications --days 30` (поставте в cron/Vercel Cron). Індекси `messenger_notif_created_idx`, `notif_user_created_idx` прискорюють обидва шляхи.

## База даних та індекси

- N+1 у `/messages/` усунено: останнє повідомлення, непрочитані й кількість учасників зчитуються `Subquery`-анотаціями + одним пакетним запитом (тест `ChatsNPlusOneTests` фіксує константну кількість запитів).
- Індекси `ChatMessage(chat, created_at)`, `ChatMessage(author, created_at)` — міграція 0007.

## Резервні копії PostgreSQL

- Windows: `.\backup_postgres.ps1` (потрібні `pg_dump` і `tar` з Windows 10+).
- Linux/macOS: `./backup_postgres.sh`.

Обидва скрипти читають `DATABASE_URL`, створюють `backups/db_<timestamp>.sql.gz` і видаляють копії старіші за `KEEP_DAYS` (14). Додайте за планувальником: Windows Task Scheduler (`powershell -File backup_postgres.ps1`, щодня) або cron (`0 3 * * * .../backup_postgres.sh`).

## Завантаження додатків

Вебвідвідувачі бачать кнопку біля «Створити»: телефон отримує Google Drive посилання на APK, ПК — на тестовий EXE. В Android WebView додатка кнопка прихована. Розпізнавання за User-Agent/Client Hints — підказка для інтерфейсу, не перевірка безпеки.

Стандартні посилання задано в `sessionlender/settings.py`. Змінити їх можна через необов'язкові `ANDROID_DOWNLOAD_URL` і `DESKTOP_DOWNLOAD_URL` у Vercel з наступним деплоєм.

## Публікація

Із папки server після налаштування ресурсів і змінних:

```powershell
npx vercel@latest --prod
```

Повна інструкція: [VERCEL_PUSH.md](../VERCEL_PUSH.md). Опис методів: [Say_README_SERVER_1.0.2.md](../Say_README_SERVER_1.0.2.md).

Змінні середовища prod: `DJANGO_SECRET_KEY` (обов'язково), `DATABASE_URL`/`POSTGRES_URL` (Neon), `REDIS_URL`, `BLOB_READ_WRITE_TOKEN`, `DJANGO_ALLOWED_HOSTS`, за потреби `SENTRY_DSN`, `LOG_LEVEL`, ліміти з таблиці вище. `build.sh` виконує `pip install`, `collectstatic` і `migrate` під час деплою.
