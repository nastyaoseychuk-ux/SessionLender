# SessionLender — оптимізація навантаження на сервер (Vercel)

Документ описує, що генерувало навантаження, які зміни було зроблено в коді та як вони відображаються на метриках тарифу Vercel. Стан вимірювань — знімок «Usage / Last 30 days» продакшн-проєкту sessionlender на момент початку оптимізації.

## 1. Вихідні метрики (Last 30 days)

| Метрика | Спожито | Ліміт | % ліміту |
|---|---|---|---|
| Fluid Active CPU | 1h 34m | 4h | ~39% |
| Functions Storage | 2,69 GB | 10 GB | ~27% |
| Fluid Provisioned Memory | 95,6 GB-Hrs | 360 GB-Hrs | ~27% |
| Blob Simple Operations | 1,1K | 10K | ~11% |
| CDN Requests | 76K | 1M | ~8% |
| Fast Origin Transfer | 633,78 MB | 10 GB | ~6% |
| Function Invocations | 59K | 1M | ~6% |
| Blob Data Transfer | 532,46 MB | 10 GB | ~5% |
| Blob Advanced Operations | 37 | 2K | ~2% |
| CDN Request CPU Duration | 44s | 1h | ~1% |

Найшвидше вичерпуються **Fluid Active CPU** (39%) та **Functions Storage / Provisioned Memory** (27%). Решта метрик має запас, але рухається лінійно від кількості запитів і клієнтів.

## 2. Що генерувало навантаження

1. **Опитування чату кожні 3 секунди** (`static/chat.js` → `messages/<id>/poll/`). Кожен відкритий чат і кожне вікно ПК-додатка давало ~20 запитів/хв. Стара вʼюха `chat_poll` навіть без нових повідомлень виконувала ~10 запитів до БД **і 2 UPDATE** (`last_read_at`, прочитані нотифікації) — це основний споживач Active CPU на рівному місці.
2. **Фонові вікна**. ПК-додаток (WebView2) тримає чати відкритими постійно, включно з мінімізованими/прихованими — опитування не зупинялися ніколи.
3. **Медіа без кешу**. Віддачі файлів (`private_media`, `/people/<id>/avatar/`) мала `Cache-Control: private, max-age=60` — кожна картинка/аватар/вкладення перекачувалися щохвилини: зайві Function Invocations, Fast Origin Transfer, Blob Data Transfer і Blob Simple Operations.
4. **Статика без кешу**. WhiteNoise за замовчуванням віддає CSS/JS/фавіконки з 60-секундним кешем — це більшість із 76K CDN Requests (ресурси версіються через `?v=…` у URL).
5. **Повторні дрібні запити на сторінці**: два окремих запити `Friendship` у context processor та повторні `Profile.for_user` (middleware + context processor + перевірки ролей) у кожному запиті.

## 3. Внесені зміни

### 3.1 Швидкий шлях у `chat_poll` (`server/messenger/views.py`)

Якщо після переданого `after` немає нових повідомлень — відповідь `{"messages": [], "last": …}` повертається одразу, **без серіалізації, без UPDATE `last_read_at` і без `mark_chat_notifications_read`**. Додатково `select_related('chat')` та `values_list('created_at')` замість завантаження повного обʼєкта.

Очікуване idle-опитування: **2 SELECT замість ~10 запитів + 2 записи**. Поведінку закріплено регресійним тестом `test_poll_fast_path_has_no_writes_when_idle` (перевіряє відсутність записів і стелю запитів через `CaptureQueriesContext`).

### 3.2 Пауза опитувань у прихованих вкладках/вікнах (`server/static/chat.js`)

`poll()` ігнорується, коли `document.hidden`; при поверненні вікна одразу виконується один «доганяльний» запит (`visibilitychange`). Для згорнутого ПК-додатка це **20 запитів/хв → 0**.

### 3.3 Кешування медіа (`server/messenger/private_media.py`, `server/messenger/send_api.py`)

Імʼя файлів у сховищі незмінні (унікальні після `get_available_name`), тому:

| Ресурс | Було | Стало |
|---|---|---|
| Вкладення чату (`chat/…`) | 60 с | **24 год** |
| Аватари кімнат, фото дописів | 60 с | 1 год |
| Аватар профілю (`/people/<id>/avatar/`) | 60 с | 1 год |

Значення `private` збережено — доступ залежить від учасника, CDN-кеш не використовується, але кеш браузера/WebView прибирає повторні завантаження між відкриттями сторінок і запусками додатків.

### 3.4 Кеш статичних файлів (`server/sessionlender/settings.py`)

```python
WHITENOISE_MAX_AGE = 3600
```

CSS/JS/фавіконки версіються через `?v=…` (і ManifestStaticFilesStorage у локальному режимі), тому годинний кеш безпечний; оновлення стилю — нове значення `?v=` у `base.html`.

### 3.5 Дрібніші оптимізації запитів

- `context_processors.navigation`: два запити `Friendship` (outgoing + incoming) обʼєднано в один `Q(owner=…) | Q(friend=…)`.
- `Profile.for_user` кешує результат на екземплярі `request.user` (один SELECT на запит замість 2–3).
- `send_request` у дружбах: `Profile.for_user(owner)` замість `owner.profile.nickname` (менше повторний SELECT).

## 4. Очікуваний ефект по метриках

| Метрика | Основний драйвер | Очікуване зниження |
|---|---|---|
| Fluid Active CPU | idle-опитування чату | ~3–8× на відкритий чат (знімок 1h34m/4h → у запас) |
| Function Invocations | фонові вікна + опитування | помітне (приховані вікна → 0 запитів) |
| CDN Requests | статика з 60-с кешем | у рази (1 год кеш) |
| Fast Origin Transfer / Blob Data Transfer / Blob Simple Ops | повторне завантаження медіа | у рази (кеш 1 год–24 год) |

Перевіряти через **Vercel → Usage** за наступні 30 днів; для нових релізів порівнювати динаміку, а не абсолютні значення (вони накопичуються).

## 5. Що можна зробити далі (не впроваджено)

1. **Throttle `last_seen`** у `ActiveUserMiddleware` — зараз це 1 UPDATE на кожен запит. Достатньо оновлювати не частіше ніж раз на 60–120 с (онлайн-статус має вікно 5 хвилин).
2. **WebSocket-push замість poll** — `realtime.py` уже існує; poll лишився fallback для serverless Vercel. Повна відмова від опитувань у чатах при живому WS зріже ще ~95% цих запитів.
3. **`vercel.json`**: `maxDuration: 300` потрібен websocket-функціям; для звичайних ASGI-запитів менший duration не економить Fluid-метрики напряму, але стримує викиди завислих запитів.
4. **Locust** (`server/locustfile.py`) — профілювати `chat-poll` під навантаженням перед подальшими змінами.
5. **Neon**: довгі неактивні зʼєднання (pool mode) — перевірити `CONN_MAX_AGE=0`/`DISABLE_SERVER_SIDE_CURSORS`, вже налаштовано у `vercel_settings.py`.

## 6. Як не зіпсувати

- Не прибирати `document.hidden`-перевірку в `chat.js` — це головна економія на ПК-клієнтах.
- Нові медіа-шляхи в `private_media` кешувати лише якщо їхнє імʼя незмінне (інакше повертати 60 с).
- Пороги контролюють тести з `CaptureQueriesContext` (`test_new_features`, `test_poll_fast_path_has_no_writes_when_idle`) — зростання числа запитів одразу падатиме в CI.
