# Локальні зміни WebView2

Збирайте через `-mod=vendor`. У `github.com/jchv/go-webview2` додано перевірку справжнього Source для Go bridge: TrustedOrigin перевіряється в COM-обробнику, а не за даними JavaScript. Прибрано автоматичний доступ до буфера обміну, виправлено вказівник GetPermissionKind. При повторному `go mod vendor` ці зміни потрібно зберегти.

Власні сповіщення використовують Win32/DWM/GDI без toast-бібліотеки, COM-реєстрації банерів та PowerShell. WebP декодується через `golang.org/x/image/webp`; решта форматів — стандартною бібліотекою Go. Ліцензії залежностей збережені.
