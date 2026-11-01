# SessionLender — створення та оновлення сервера Vercel

Команди для Windows PowerShell. Усі Vercel-команди виконуйте в папці **server**, не в корені комплекту і не в android. У нашому випадку проєкт — sessionlender, домен — https://sessionlender.vercel.app. Якщо створюєте власний — замініть назву й домен у налаштуваннях та Android-збірці.

## 1. Що підготувати

Node.js із npm/npx, Python 3.13 для локальних команд, акаунт Vercel. Глобально встановлювати Vercel CLI не потрібно. Для хмари потрібні три окремі ресурси: PostgreSQL/Neon, Upstash Redis із TCP/TLS URL та public Vercel Blob. База SQLite у файлі не підходить для постійного збереження на Vercel.

```powershell
node --version
npm --version
py -3.13 --version
Set-Location "F:{Шлях_до_проекту}\SessionLender\server"
npx vercel@latest login
npx vercel@latest link
```

У login завершіть вхід у браузері. У link виберіть свій акаунт/team. Для вже створеного sessionlender виберіть підключення існуючого проєкту; для нового — створення. Назва має бути малими латинськими літерами, наприклад sessionlender; допустимі цифри, крапка, підкреслення, дефіс, але не `---`.

Якщо CLI показує `Detected Django (Output Directory: N/A)` і пропонує Customize settings — прийміть стандартні налаштування (`N`), якщо немає окремої причини їх змінювати. Не задавайте output directory вручну. У проєкті вже є pyproject.toml/vercel.json, ASGI entrypoint та build-команда. `python main.py` призначено для локального запуску; Vercel завантажує ASGI entrypoint.

Після link:

```powershell
npx vercel@latest whoami
npx vercel@latest project inspect
```

Перевірте, що підключено саме потрібний проєкт і team. Локальна .vercel створюється CLI та не входить у чистий архів.

## 2. Створити та приєднати сховища

У Vercel відкрийте Storage → Create Storage / Browse Storage. Назви пунктів UI можуть змінюватися; ключовий крок для кожного ресурсу — **Connect to Project → sessionlender**, із середовищем Production.

### Neon PostgreSQL

Виберіть Neon, створіть базу (у нас sessionlender-db), доступний вам тариф і регіон біля регіону функцій. Під’єднайте до проєкту. Переконайтеся, що у Production є DATABASE_URL або POSTGRES_URL із PostgreSQL connection string. Сервер спершу використовує DATABASE_URL, потім POSTGRES_URL. PGHOST/PGUSER окремо недостатньо: поточні settings читають повний URL.

Приклад формату (не справжні дані):

```text
postgresql://user:password@host/dbname?sslmode=require
```

### Upstash Redis

Виберіть Upstash → Upstash for Redis (не Vector, Search або QStash), створіть ресурс (у нас sessionlender-redis) та під’єднайте до проєкту. Потрібна саме REDIS_URL з протоколом redis:// або rediss://. У production використовуйте TLS rediss://, якщо провайдер його надає.

KV_REST_API_URL та KV_REST_API_TOKEN не замінюють REDIS_URL для channels-redis. Якщо інтеграція не створила REDIS_URL, візьміть TCP/TLS connection string у Redis-провайдера й додайте вручну як Secret.

### Vercel Blob

Виберіть Blob, створіть **Public** store (у нас sessionlender-media), під’єднайте до проєкту. Переконайтеся, що є **BLOB_READ_WRITE_TOKEN**. Якщо немає: відкрийте відповідний Blob store → Quickstart / .env.local або доступні налаштування токенів, отримайте read-write token та додайте його вручну до Production як Secret. Не використовуйте замість нього BLOB_STORE_ID чи BLOB_WEBHOOK_PUBLIC_KEY — вони мають інше призначення.

Public означає доступність медіа за їхнім URL. Це поточна реалізація; для приватних вкладень потрібні окремі зміни коду.

## 3. Змінні середовища

У нашому інтерфейсі: Project → Settings → Environments → Production → Environment Variables → Add Environment Variable. Якщо ваш UI відрізняється, знайдіть Environment Variables у налаштуваннях саме проєкту.

**Key і Value вставляйте без зовнішніх лапок.** Назви Secret/Config та Production також не вводяться в значення: це елементи вибору в інтерфейсі. Для токенів і паролів вибирайте Secret, для несекретних налаштувань — Config.

| Key | Value / призначення | Тип |
| --- | --- | --- |
| DJANGO_SETTINGS_MODULE | sessionlender.vercel_settings | Config |
| DJANGO_ALLOWED_HOSTS | sessionlender.vercel.app, без https:// і без шляху | Config |
| DJANGO_SECRET_KEY | Довгий постійний випадковий ключ | Secret |
| DATABASE_URL | Neon PostgreSQL URL; POSTGRES_URL — підтримувана альтернатива | Secret |
| REDIS_URL | TCP/TLS URL Redis, зазвичай rediss://… | Secret |
| REDIS_PREFIX | sessionlender-production | Config |
| BLOB_READ_WRITE_TOKEN | Read-write token під’єднаного public Blob store | Secret |
| RUN_MIGRATIONS | 1 | Config |

Інтеграційні змінні, які вже створені з правильними значеннями, вдруге не додавайте. Якщо DATABASE_URL і POSTGRES_URL задані одночасно, пріоритет має DATABASE_URL. Якщо інший домен — замініть DJANGO_ALLOWED_HOSTS. Кілька hosts перелічуються через кому. Додаткові HTTPS origins можна задати через DJANGO_CSRF_TRUSTED_ORIGINS, також через кому; це зазвичай не потрібно для стандартного домену.

Генерація ключа локально:

```powershell
py -3.13 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Скопіюйте результат як DJANGO_SECRET_KEY. Не генеруйте новий ключ при кожному деплої: його зміна скидає чинні сесії. Не встановлюйте LOCAL_DEVELOPMENT=1 у Production. Системні VERCEL/VERCEL_URL платформа задає сама.

Альтернативно додавання через CLI (значення буде запитано інтерактивно):

```powershell
npx vercel@latest env add DJANGO_SETTINGS_MODULE production --no-sensitive
npx vercel@latest env add DJANGO_ALLOWED_HOSTS production --no-sensitive
npx vercel@latest env add DJANGO_SECRET_KEY production --sensitive
npx vercel@latest env add DATABASE_URL production --sensitive
npx vercel@latest env add REDIS_URL production --sensitive
npx vercel@latest env add REDIS_PREFIX production --no-sensitive
npx vercel@latest env add BLOB_READ_WRITE_TOKEN production --sensitive
npx vercel@latest env add RUN_MIGRATIONS production --no-sensitive
npx vercel@latest env ls production
```

Виконуйте env add тільки для відсутніх змінних. Для зміни існуючої використайте `env update KEY production` із тим самим --sensitive для секрету або інтерфейс Vercel. Не передавайте справжні секрети буквальним текстом командного рядка.

Змінні набувають чинності в новому деплої; одного Save недостатньо для вже запущеної версії.

## 4. Створити адміністратора

Перед першим production-деплоєм додайте:

| Key | Значення | Тип |
| --- | --- | --- |
| DJANGO_SUPERUSER_USERNAME | Ваш username, наприклад admin | Config |
| DJANGO_SUPERUSER_PASSWORD | Новий сильний пароль | Secret |
| DJANGO_SUPERUSER_EMAIL | Пошта, необов’язково | Config |

Або CLI:

```powershell
npx vercel@latest env add DJANGO_SUPERUSER_USERNAME production --no-sensitive
npx vercel@latest env add DJANGO_SUPERUSER_PASSWORD production --sensitive
```

build створить адміністратора, тільки якщо такого username ще немає. Наявному акаунту пароль не змінюється. Стару SQLite та старі акаунти до чистого архіву не включено; чинні акаунти Neon залишаться в Neon.

## 5. Деплой Production

```powershell
npx vercel@latest --prod
```

Дочекайтеся успішного завершення та відкривайте Production URL, який надрукує CLI. `deploy_build.py` застосовує міграції при RUN_MIGRATIONS=1 і за потреби створює адміністратора. Міграція 0004 потрібна для client_nonce та захисту від дублів; усі міграції вже в проєкті.

Після створення адміністратора видаліть bootstrap-пароль із Environment Variables і задеплойте повторно:

```powershell
npx vercel@latest env rm DJANGO_SUPERUSER_PASSWORD production
npx vercel@latest --prod
```

Можна також видалити bootstrap username/email. Сам акаунт від цього не видаляється.

Вхід на сайті: https://sessionlender.vercel.app/login/ . Для штатної адмінки Django використовуйте `/admin/`; у вебінтерфейсі є також власна панель адміністрування.

## 6. Оновлення чинного проєкту

Розпакуйте чистий вихідний код у робочу папку, зберігаючи свою локальну прив’язку .vercel, приватні налаштування й Android local.properties. Якщо їх немає, повторіть link для існуючого проєкту. Не створюйте новий сервер при кожному оновленні.

```powershell
Set-Location "F:\Data\ProjectDock\1\projects\SessionLender\server"
npx vercel@latest env ls production
npx vercel@latest --prod
```

Neon і Blob при оновленні коду не очищаються. У цьому коді немає команди автоматичного видалення бази. Імпорт старих даних не запускається автоматично. Перед змінами схеми робіть резервну копію засобами провайдера.

Preview (`npx vercel@latest` без --prod) використовуйте тільки з окремими preview-БД, Redis prefix та Blob: не підключайте тестові міграції до production-бази. Для Preview потрібні власні змінні відповідного середовища.

## 7. Локальна робота з production-БД — за потреби

Це не обов’язковий крок деплою. Потрібен, наприклад, для зміни пароля існуючого адміністратора. У server:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npx vercel@latest env pull .env.local --environment=production
```

manage.py завантажує .env.local через python-dotenv. **Перевірте повноту файлу приватно:** значення змінних типу Secret можуть не експортуватися CLI. У такому разі внесіть відсутні значення зі своїх захищених джерел/налаштувань провайдера. Не публікуйте файл і не покладайтеся на env pull як на резервну копію секретів. Потрібні DJANGO_SECRET_KEY, DATABASE_URL або POSTGRES_URL, REDIS_URL, BLOB_READ_WRITE_TOKEN та налаштування домену.

Після коректного налаштування:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py changepassword admin
```

changepassword діє на базу, URL якої завантажено; переконайтеся, що обрали потрібну базу. Початковий пароль із Django-хешу дістати неможливо. Не запускайте main.py з production .env.local для звичайних локальних експериментів — він теж використовуватиме ці підключення.

## 8. Перевірка після публікації

Відкрийте сайт і увійдіть. З двох акаунтів перевірте відправлення до готовності WS, кілька повідомлень підряд, відновлення мережі, відсутність дублів, статуси ◷/✓/✓✓/✕. Відкрийте чат одержувача у видимій вкладці — має прийти read. Перевірте число у title/favicon і скидання після прочитання. Окремо перевірте аватар, допис із зображенням і Android-сповіщення.

При помилці: Project → Logs / Observability → запис ERROR або traceback за потрібний час. Для діагностики:

```powershell
npx vercel@latest ls
npx vercel@latest inspect https://sessionlender.vercel.app
npx vercel@latest logs https://sessionlender.vercel.app
```

Якщо CLI не приймає production alias у конкретній операції, підставте точний deployment URL із виводу deploy/ls. Не надсилайте секрети чи повний .env.local разом із журналом.

| Симптом | Що перевірити |
| --- | --- |
| DEPLOYMENT_NOT_FOUND | Успіх deploy, точний Production URL та прив’язку домену до актуального deployment |
| Помилка build / ImproperlyConfigured | Усі обов’язкові Production-змінні та підключення ресурсів |
| relation/column does not exist | RUN_MIGRATIONS=1, успіх міграцій і правильну DATABASE_URL |
| WS не підключається | ASGI entrypoint, Origin/hosts, чинну сесію, Redis TCP URL, конфігурацію/ліміти runtime платформи |
| Текст записаний, live-події немає | Помилки Redis в логах; relay не скасовує commit, синхронізація повертає збережене |
| Медіа не працюють | Public store, BLOB_READ_WRITE_TOKEN, обсяг/тип файла |
| Android не сповіщає | Дозвіл сповіщень, вхід, роботу foreground-сервісу та обмеження батареї |
| Старий логотип | Оновлення сторінки/кешу favicon; для Android launcher — новий APK |

## 9. Що вже є в коді

Не створюйте заново vercel.json, requirements.txt чи ASGI-файли. Vercel використовує `sessionlender.vercel_asgi:application` та build `python deploy_build.py`. Конфіг maxDuration=300 — запитана межа, а не обіцянка безмежного WS; доступні режими/тривалість залежать від поточного тарифу та runtime. Клієнти вже перепідключаються після закриття каналу. Перевірте підтримку WS/Fluid compute у своєму проєкті за актуальною документацією.

## Офіційні джерела

- Django на Vercel: https://vercel.com/docs/frameworks/full-stack/django
- WebSockets: https://vercel.com/docs/functions/websockets
- CLI login: https://vercel.com/docs/cli/login
- CLI link: https://vercel.com/docs/cli/link
- CLI env: https://vercel.com/docs/cli/env
- CLI deploy: https://vercel.com/docs/cli/deploy
- Environment variables: https://vercel.com/docs/environment-variables
- Blob: https://vercel.com/docs/vercel-blob

Команди env/link/deploy звірено з офіційними матеріалами Vercel. Точні назви кнопок і доступні тарифи можуть відрізнятися від показаних у нашій сесії.

## Посилання на Android та ПК-збірки

Кнопка завантаження працює зі стандартними Google Drive адресами з коду. Додавати змінні для цього не обов’язково. Для заміни файла без правок шаблону задайте Config-змінні ANDROID_DOWNLOAD_URL та/або DESKTOP_DOWNLOAD_URL у Production, збережіть і виконайте новий деплой. Для Drive можна використати формат `https://drive.google.com/uc?export=download&id=FILE_ID`.

Обидва файла мають бути доступні всім за посиланням. Поточний EXE тестовий; при заміні можна змінити URL на інший файл. Google Drive може вимагати підтвердження завантаження та має власні квоти. Для приховування кнопки у встановленому Android-клієнті із власним User-Agent маркером зберіть актуальний APK.
