# SessionLender — сервер: опис реалізації 1.0.2

Опис поточної реалізації серверної частини. 1.0.2 — номер документації; технічна версія pyproject.toml — 0.3.4.

## Конфігурація сервера

Django-проєкт працює на Vercel через ASGI. `main.py` використовується для локальної розробки.

| Компонент | Реалізація |
| --- | --- |
| HTTP + WebSocket | Django 5.2, Channels 4; ProtocolTypeRouter, AuthMiddlewareStack, AllowedHostsOriginValidator |
| База | PostgreSQL/Neon через dj-database-url і psycopg; conn_max_age=0, SSL у хмарі |
| Обмін між інстансами | channels-redis через TCP/TLS REDIS_URL; окремий Redis prefix |
| Медіафайли | Vercel Blob, власний Django Storage backend |
| Статичні файли | Збирання статичних ресурсів платформою Vercel |
| Вхідна точка | sessionlender.vercel_asgi:application у pyproject.toml |
| Підготовка БД | deploy_build.py під час build, а не на кожному HTTP-запиті |

`vercel_settings.py` вимагає постійний DJANGO_SECRET_KEY, PostgreSQL, Redis та Blob token. Якщо немає критичної змінної, видає явну помилку конфігурації. SQLite й in-memory channels дозволені лише в локальному режимі; на Vercel це не постійне сховище. Установлено secure cookies, перевірку hosts/CSRF origins, DEBUG=False. Ліміти зображень у коді: дописи 4 MiB, аватари 2 MiB; запит із файлом повинен також вкладатися в обмеження платформи.

## Надійне надсилання повідомлень

### messenger/sending.py

`SendError(message, status=400)` — контрольовані помилки валідації та доступу.

`store_message(user, chat_id, text, nonce=None)` — спільний шлях запису для HTTP і WebSocket. Перевіряє текст до 2000 символів через ChatMessageForm, активність користувача, бан і членство в чаті. Виконує запис у transaction.atomic. UUID client_nonce використовується в get_or_create; повтор того самого тексту з тим самим ключем повертає існуюче повідомлення. Спроба змінити текст для вже використаного ключа повертає 409. При OperationalError/InterfaceError закриває DB connections і один раз повторює через 0.2 секунди, тільки коли є ключ ідемпотентності. WS-запити можуть надсилатися без nonce; для них повтор не захищений від дублювання.

`payload(message, viewer_id)` — серіалізація повідомлення: id, client_nonce, author, initials, avatar, text, time, created_at, mine, read. Аватар повертається як окремий URL, тому отримання Blob metadata не блокує підтвердження надсилання. read визначається за last_read_at іншого учасника.

### messenger/send_api.py

`send(request, chat_id)` — авторизований POST `/messages/<id>/send/`, звичайний Django CSRF захист. JSON містить text і client_nonce. Повертає sent з повідомленням або контрольовані 400/403/409; тимчасова помилка БД — retry/503. HTTP — резервний шлях для відправлення, а не polling.

`avatar(request, user_id)` — авторизований запит з перенаправленням на URL аватара. Помилка сховища повертає 404 і не перетворює успішне надсилання тексту на помилку.

### messenger/delivery.py

`relay(events)` — відправляє пакет подій у channel layer з обмеженням очікування 1.5 секунди. Помилка Redis записується в журнал, але не викидається назад після успішного commit у БД. transaction.on_commit(..., robust=True) ізолює доставку від транзакції запису.

Це не постійна черга гарантованої доставки. При аварії Redis live-подія може бути втрачена; повідомлення залишається в БД та повертається при наступній синхронізації. Durable outbox не реалізовано.

## WebSocket: messenger/realtime.py

`session_valid(scope)` перевіряє поточну сесію, її строк, активність користувача та відповідність auth hash після зміни пароля.

### ChatConsumer — /ws/chats/<id>/

| Метод | Дія |
| --- | --- |
| permitted() | Перевірка сесії, бану та членства |
| connect() / disconnect() | Авторизація й підписка на групу chat_<id>, відписка |
| read_through() | Остання позначка прочитання іншого учасника для відновлення статусів |
| messages(after) | До 200 повідомлень після ID з БД, без автоматичного прочитання |
| save_message(text, nonce) | Виклик спільного store_message, перетворення помилок на WS-відповіді |
| receive_json() | Обробка send, sync та read; перевірка доступу після підключення |
| chat_message() | Реакція на Redis-подію нового повідомлення та передавання актуальних записів |
| mark_read(message_id) | Рухає last_read_at тільки вперед до наявного повідомлення цього чату; публікує read і оновлення unread |
| chat_read() | Доставляє підтвердження прочитання авторизованому клієнту |

Клієнт надсилає `{type:"send", text, client_nonce}`, `{type:"sync", after:0}` або `{type:"read", id}`. Сервер відповідає ready, messages, sent, error, retry, read. messages може містити sync/after/more для посторінкового відновлення. read містить user_id і through. Підтвердження видимості — клієнтська домовленість, а не гарантія уваги людини.

### InboxConsumer — /ws/inbox/

`unread()` перевіряє доступ і рахує непрочитані повідомлення. connect()/disconnect() керують підпискою user_<id>. `inbox_changed()` передає актуальний count. `missed_messages()` повертає до 20 останніх непрочитаних повідомлень для відновлення сповіщень. `notification(event)` формує title/body/path лише після перевірки прав; `server_notice()` передає готовий notification клієнту.

Події: нове особисте повідомлення, додавання до кімнати, допис, коментар, вподобання. Особисті/кімнатні дані перевіряються перед доставкою; власні дії не дублюються як сторонні сповіщення. Повного replay-журналу кімнатних подій немає.

## Сигнали та сховище

`signals.py`: ensure_profile() підтримує профіль і роль адміністратора; touch_chat() оновлює час чату та позначку автора; broadcast_message() після commit одним пакетом публікує chat.message, inbox.changed і server.notice; cleanup_empty_chat() видаляє порожній чат після commit.

`notifications.py`: publish() відкладає relay до commit. new_post(), new_comment(), new_like(), room_added() визначають адресатів подій. Приватність перевіряється також в InboxConsumer, а не тільки під час формування списку адресатів.

`blob_storage.py`: VercelBlobStorage використовує синхронний SDK vercel==0.12.1. get_available_name() формує унікальне ім’я; _save() записує Blob; _open() читає; url(), size(), exists(), delete() забезпечують стандартний Storage API; metadata() кешує метадані. Поточне Blob-сховище public: доступ за URL не є перевіркою прав Django. Для приватних медіа перед релізом потрібна окрема схема зберігання/видачі.

## Клієнтський код сайту

`static/chat.js`: createBubble()/addPending() відразу показують текст; outbox Map підтримує кілька одночасних відправлень; persist() зберігає незавершені пакети у sessionStorage; transmit()/scheduleRetry() керують WS, HTTP fallback та повторними спробами (до 6); accept()/showMessage() об’єднують локальну бульбашку з серверним записом за nonce та ID. setState() показує статус біля повідомлення; acknowledgeRead()/updateReadStates() обробляють прочитання. connect() відновлює WS і синхронізацію. Позначка прочитання оновлюється явним підтвердженням клієнта у видимому чаті.

`static/inbox.js`: один WS-канал на авторизовану сторінку для лічильників навігації; подія inbox:unread передає число оформленню вкладки. Регулярних HTTP-запитів немає.

`static/tab-status.js`: render() повертає звичайний title/favicon при нулі або показує «N Нових повідомлень» і малює цифру на порожньому трикутному логотипі через canvas. Повне число зберігається; шрифт зменшується для довгих чисел.

`templates/base.html`, `auth.html`, `chat_detail.html`, `static/app.css`, `static/brand/`: прозорі логотипи, favicon, статуси повідомлень, дані для JS; версійні URL обходять старий кеш ресурсів.

## Міграції й облікові записи

`0004_chatmessage_client_nonce_and_more.py`: nullable UUID client_nonce та унікальне обмеження `(author, chat, client_nonce)`. Поле допускає NULL для записів без ключа повторного надсилання. Усі міграції включено в чистий проєкт.

`deploy_build.py` виконує migrate при RUN_MIGRATIONS=1. Якщо задано DJANGO_SUPERUSER_USERNAME/PASSWORD, створює суперкористувача тільки за відсутності такого username. Пароль наявного акаунта не скидає й не друкує. Паролі в Django зберігаються як хеші; отримати початковий пароль із хешу неможливо.

`export_sqlite.py` експортує стару SQLite: робить тимчасову копію, мігрує копію та зберігає fixture без сесій та службових записів. `import_legacy` завантажує її лише в базу без користувачів; при наявних акаунтах припиняє імпорт. `import_media` переносить старі файли в Blob і оновлює посилання. Ці утиліти залишено, але приватна база, медіа й експорт до архіву не включені.

## Локальна розробка

У папці server (PowerShell):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

main.py створює локальний секрет, застосовує міграції та запускає Uvicorn на http://127.0.0.1:8000. Для чистого локального режиму не створюйте .env.local з production-підключеннями. Локальні файли з’являються під час запуску; до поставки вони не входять.

Для локального адміністратора/тестів в іншому вікні PowerShell задайте локальний режим і використайте той самий створений ключ:

```powershell
$env:LOCAL_DEVELOPMENT = "1"
$env:DJANGO_SECRET_KEY = (Get-Content .django-secret -Raw).Trim()
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py test messenger
```

## Організація коду

Наявні методи, URL, JSON-пакети, коди помилок і правила доступу збережено. Допоміжні функції відокремлюють перевірку вхідних даних від збереження, транспорту та відображення.

| Функція / метод | Відповідальність |
| --- | --- |
| sending.validate_text(text) | Перевірка тексту через ChatMessageForm та збирання помилок |
| sending.parse_nonce(nonce) | Розбір UUID або відсутнього ключа |
| sending.require_chat_access(user, chat_id) | Активність акаунта, бан, членство у чаті |
| sending.save_once(user, chat_id, text, nonce) | Створення або повернення того самого повідомлення за ключем |
| ChatConsumer.receive_read(content) | Обробка read-пакета |
| ChatConsumer.receive_send(content) | Обробка send-пакета |
| ChatConsumer.receive_sync(content) | Валідація курсора і сторінка синхронізації |
| InboxConsumer.message_notice(user, pk) | Дані та права особистого повідомлення |
| InboxConsumer.post_notice(user, pk) | Дані та права допису |
| InboxConsumer.reaction_notice(user, pk, kind) | Дані та права коментаря/вподобання |
| InboxConsumer.room_notice(user, pk) | Дані та права додавання до кімнати |
| chat.js sendHttp(item, packet) | HTTP-запит, таймаут та обробка відповіді |
| chat.js receivePacket(current, event) | Обробка вхідного WS-пакета |
| chat.js createNonce() | Генерація UUID для однієї спроби відправлення |
| chat.js restoreOutbox() | Відновлення незавершених пакетів із sessionStorage |

## Перевірки та межі реалізації

Unit-тести сервера: messenger/tests.py і test_delivery.py. Основні сценарії: доступ до приватних даних, ролі, повторне надсилання без дубля, HTTP/WS із тим самим ключем, CSRF, валідація, збереження при помилці relay, незалежність від доступності аватара. Команда запуску наведена вище.

E2EE немає; HTTPS/WSS не замінює наскрізне шифрування. FCM немає; Android використовує foreground WS. Durable outbox для Redis-подій не реалізовано. Для експлуатації потрібні резервні копії PostgreSQL/Blob та моніторинг помилок. Перед змінами схеми слід робити резервну копію; preview має використовувати окремі ресурси.

## Кнопка завантаження програми

`messenger/downloads.py: application_download(request)` — template context processor. За маркером SessionLenderAndroid/ або стандартною ознакою Android WebView приховує кнопку. Для веббраузерів визначає телефон через Sec-CH-UA-Mobile або User-Agent та повертає app_download з url, label і title. Телефон отримує APK; ПК — тестовий EXE. Це оформлення інтерфейсу, не контроль доступу.

`ANDROID_DOWNLOAD_URL` та `DESKTOP_DOWNLOAD_URL` у settings.py мають стандартні адреси завантаження Google Drive; однойменні необов’язкові змінні середовища замінюють їх. base.html показує посилання поруч із кнопкою «Створити». На вузьких екранах залишається іконка з aria-label. Google Drive може показувати власне підтвердження завантаження. Тести вибору посилань і приховування кнопки — messenger/test_downloads.py.
