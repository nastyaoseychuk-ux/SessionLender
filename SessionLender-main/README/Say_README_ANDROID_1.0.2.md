# SessionLender — Android: опис реалізації 1.0.2

Цей файл описує поточну реалізацію Java-клієнта. 1.0.2 — номер документації за запитом; поточний Android versionName у коді — 0.3.4, versionCode — 5. Номер APK автоматично не змінювався під номер документа.

## Архітектура

Додаток Java із системним Android WebView для екранів сайту та окремим foreground-сервісом для сповіщень. Це не незалежний нативний інтерфейс чату: форми, кімнати, профілі та переписка завантажуються із Django. Зміни HTML/CSS/JS після деплою стають доступні без нового APK; зміни Java, дозволів, адреси сервера чи launcher-іконки потребують збірки.

Адреса сервера задається під час збірки, за замовчуванням https://sessionlender.vercel.app. MainActivity відкриває потрібний розділ зі сповіщення, забезпечує вибір файлів для завантаження, системні відступи та навігацію назад по історії WebView.

SL-логотип — бірюзово-фіолетовий трикутник на прозорому тлі. Android launcher використовує стандартний adaptive icon зі статичним SL, без цифри непрочитаних. Форма й тло launcher-іконки залежать від оболонки телефона; прозорий PNG не скасовує маску Android. Маленька монохромна іконка системних сповіщень зберігається окремо.

## Файли і методи

| Файл / метод | Призначення |
| --- | --- |
| `MainActivity.java: onCreate()` | Створення WebView, налаштування cookies, дозволів, клієнтів та системних відступів |
| `sameServer(Uri)` | Перевірка scheme, host і port перед внутрішньою навігацією |
| `shouldOverrideUrlLoading()` | Сторінки свого сервера відкриває всередині; зовнішні HTTP/HTTPS — у браузері |
| `onPageFinished()` | Збереження cookies та синхронізація сервісу сповіщень |
| `syncNotifications()` | Бере лише sessionid із CookieManager; запускає сервіс після входу, зупиняє після виходу |
| `onShowFileChooser()` / `onActivityResult()` | Вибір і повернення файлів у вебформу |
| `openNotification()` / `onNewIntent()` | Відкриття відносного шляху зі сповіщення; відхиляє небезпечні форми шляху |
| `onRequestPermissionsResult()` | Запуск сповіщень після надання дозволу Android 13+ |
| `onResume()` | Повторна перевірка активної сесії |
| `onBackPressed()` / `onDestroy()` | Історія WebView, закриття callback вибору файлу та звільнення WebView |
| `ServerConfig.java` | Єдина базова URL-адреса із BuildConfig.SERVER_URL |
| `NotificationService.java` | Окреме з’єднання OkHttp WebSocket із `/ws/inbox/` |
| `NotificationService.onCreate()` | Канали connection/events і видиме постійне сповіщення foreground-сервісу |
| `onStartCommand()` | Зміна сесії, скасування старого сокета, завантаження списку оброблених подій |
| `connect()` | Cookie + Origin у WS-handshake; callbacks onOpen/onMessage/onClosed/onFailure |
| `reconnect()` | Повторне підключення з наростаючою затримкою до 30 секунд і випадковою добавкою |
| `receive()` | Розбір JSON notification, захист від повторів, створення системного сповіщення |
| `fingerprint()` | SHA-256 від сесійного cookie як ключ списку подій у SharedPreferences; це не шифрування повідомлень |
| `updateStatus()` | Текст стану foreground-сервісу |
| `open()` | Незмінний PendingIntent для відкриття відповідної сторінки |
| `onDestroy()` сервісу | Зупинка перепідключень, сокета, OkHttp та пов’язаних сповіщень |

### Допоміжні методи

| Метод | Відповідальність |
| --- | --- |
| MainActivity.createLayout() | Контейнер, WebView, системні відступи |
| MainActivity.configureWebView() | JavaScript, сховище, правила cookies та доступу |
| MainActivity.configureNavigation() | WebViewClient, внутрішня/зовнішня навігація та помилки |
| MainActivity.configureFileChooser() | WebChromeClient для вибору файлів |
| MainActivity.requestNotificationPermission() | Запит дозволу Android 13+ |
| NotificationService.changeSession(value) | Скасування старого з’єднання і запуск із поточною сесією |
| NotificationService.loadSeenEvents() | Відновлення оброблених ID із SharedPreferences |
| NotificationService.connectionListener(current) | Callbacks конкретного покоління WS-з’єднання |
| NotificationService.showEvent(event, id) | Побудова системного сповіщення для події |
| NotificationService.statusNotification(text) | Спільна побудова постійного сповіщення стану |

`generation` відкидає callbacks старого з’єднання після зміни сесії. Останні 200 ID подій зберігаються для усунення повторних сповіщень. OkHttp надсилає WS ping кожні 30 секунд; це підтримання каналу, а не HTTP-опитування сервера.

## Чат усередині WebView

`server/static/chat.js` реалізує спільну поведінку браузера і додатка:

- Миттєва локальна бульбашка повідомлення, поле відразу готове до наступного тексту.
- Стани ◷ надсилається, ✓ збережено сервером, ✓✓ прочитано, ✕ помилка.
- Повтор натисканням ✕; однаковий client_nonce у WS та резервному HTTP-запиті запобігає дублюванню.
- Черга незавершених відправлень у sessionStorage; це сховище вкладки, не повноцінна постійна офлайн-база.
- HTTP використовується лише як резерв надсилання, не для регулярного опитування.
- Підтвердження прочитання надсилається у видимому чаті. Це сигнал клієнта про показ, а не доказ фактичного прочитання людиною.

Лічильник у назві сторінки та favicon працює у вебчастині. Launcher-іконка Android залишається звичайною.

## Визначення застосунку сервером

configureWebView() додає до стандартного User-Agent маркер `SessionLenderAndroid/<version>`. Сервер використовує його для приховування кнопки завантаження додатка всередині Android-клієнта. Звичайний браузер на телефоні отримує APK-посилання, браузер на ПК — тестовий EXE. Розпізнавання не застосовується для авторизації.

## Безпека та обмеження

HTTPS/WSS; заборонено cleartext і mixed content. Вимкнено доступ WebView до file://, сторонні cookies; немає JavaScript bridge і обходу перевірки TLS-сертифікатів. Сервер перевіряє сесію та доступ до кожного чату. Session cookie не вбудовується в APK і не записується в лог.

Наскрізне шифрування повідомлень не реалізовано. TLS захищає передавання, але сервер має доступ до тексту повідомлень.

Сповіщення реалізовано через foreground WebSocket-сервіс, не через FCM. Після force-stop, завершення процесу ОС, обмежень Xiaomi або заборони сповіщень доставка не гарантована. Сервіс використовує START_NOT_STICKY. Після наступного відкриття відновлює з’єднання; сервер повертає до 20 пропущених непрочитаних повідомлень. Події дописів/коментарів/вподобань не мають повного постійного журналу повторного відтворення.

## Вимоги до збірки

JDK 17, Android SDK Platform 35, Build Tools, Android command-line tools, PowerShell і доступ до інтернету. minSdk 26 (Android 8), targetSdk/compileSdk 35. Android Studio не потрібна. Використано Android Gradle Plugin 8.7.3, Gradle 8.9 та OkHttp 4.12.0.

Перевірка в PowerShell:

```powershell
java -version
$env:JAVA_HOME
$env:ANDROID_HOME
```

JAVA_HOME має вказувати на корінь JDK 17, ANDROID_HOME — на ваш каталог SDK. За потреби створіть `android/local.properties` (приклад шляху замініть на свій):

```properties
sdk.dir=C:/Users/sanya/AppData/Local/Android/Sdk
```

Ліцензії та компоненти через наявний sdkmanager:

```powershell
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --licenses
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

## Зібрати й установити

Перейдіть у папку `android`:

```powershell
.\build.ps1
```

Для іншого домену:

```powershell
.\build.ps1 -ServerUrl "https://your-project.vercel.app"
```

Якщо PowerShell блокує скрипт, одноразово для поточного процесу:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

Скрипт завантажує Gradle 8.9, перевіряє SHA-256 архіву та виконує assembleDebug. Не потрібен глобально встановлений Gradle. APK: `app/build/outputs/apk/debug/app-debug.apk`.

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Для оновлення поверх старого APK потрібен той самий applicationId та ключ підпису. Збережіть debug keystore на машині збірки; для релізу налаштуйте окремий release-підпис і зберігайте його приватно. Підготовленого release-підпису та готового APK в архіві немає. Для релізу збільшуйте versionCode; versionName змінюйте за вашою схемою версій.

Після встановлення увійдіть в акаунт, надайте дозвіл на сповіщення. Перевірте обмін двома акаунтами, згортання додатка, відкриття зі сповіщення, відновлення після втрати мережі. У середовищі підготовки Android SDK відсутній, тому APK не компілювався; XML-ресурси перевірено.
