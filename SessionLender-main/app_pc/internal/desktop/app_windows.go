//go:build windows

package desktop

import (
	"embed"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync/atomic"
	"time"
	"unsafe"

	webview "github.com/jchv/go-webview2"
	"sessionlender/desktop/internal/config"
	"sessionlender/desktop/internal/events"
)

//go:embed bridge.js quick_chat.js assets/logo.png assets/app.ico assets/notification.mp3
var assets embed.FS

type App struct {
	view     webview.WebView
	tray     *Tray
	client   *events.Client
	notifier *Notifier
	enabled  atomic.Bool
	closing  atomic.Bool
	account  string
	page     atomic.Value
	quick    *QuickChat
}

func Run() error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	shell32.NewProc("SetCurrentProcessExplicitAppUserModelID").Call(uintptr(unsafe.Pointer(utf16(config.AppID))))
	dir, err := config.DataDir()
	if err != nil {
		return err
	}
	a := &App{}
	a.enabled.Store(true)
	// Keep session renewal active while minimized; event reception itself is native Go.
	os.Setenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-background-timer-throttling --disable-renderer-backgrounding")
	a.view = webview.NewWithOptions(webview.WebViewOptions{
		DataPath: filepath.Join(dir, "WebView2"), AutoFocus: true,
		TrustedOrigin: config.ServerURL,
		WindowOptions: webview.WindowOptions{Title: "SessionLender", Width: 1280, Height: 820, Center: true, IconId: 1},
	})
	if a.view == nil {
		return fmt.Errorf("WebView2 не запустився. Встановіть Microsoft Edge WebView2 Runtime: https://developer.microsoft.com/microsoft-edge/webview2/")
	}
	defer a.view.Destroy()
	a.view.SetSize(820, 600, webview.HintMin)
	logo, err := writeAsset(dir, "logo.png")
	if err != nil {
		return err
	}
	icon, err := writeAsset(dir, "app.ico")
	if err != nil {
		return err
	}
	soundPath, err := writeAsset(dir, "notification.mp3")
	if err != nil {
		return err
	}
	sound := NewNotificationSound(soundPath)
	defer sound.Close()
	a.quick = NewQuickChat(filepath.Join(dir, "WebView2"), a.open)
	defer a.quick.Close()
	a.notifier, err = NewNotifier(uintptr(a.view.Window()), logo, func(path string) { a.open(path) }, a.openQuickChat, sound.Play, a.view.Dispatch)
	if err != nil {
		return fmt.Errorf("створення вікна сповіщень: %w", err)
	}
	defer a.notifier.Clear()
	a.client = events.NewClient(events.LoadHistory(filepath.Join(dir, "notification-history.json")), a.notify, a.setStatus)
	defer a.client.Stop()
	a.tray, err = NewTray(uintptr(a.view.Window()), icon, a.open, a.quit, a.toggleNotifications, a.testNotification)
	if err != nil {
		return err
	}
	defer a.tray.Close()
	if err = a.bindBridge(); err != nil {
		return err
	}
	script, _ := assets.ReadFile("bridge.js")
	origin, _ := json.Marshal(config.ServerURL)
	a.view.Init(strings.ReplaceAll(string(script), "__SERVER_ORIGIN__", string(origin)))
	a.view.Navigate(config.ServerURL)
	a.view.Run()
	a.closing.Store(true)
	return nil
}

func writeAsset(dir, name string) (string, error) {
	data, err := assets.ReadFile("assets/" + name)
	if err != nil {
		return "", err
	}
	path := filepath.Join(dir, name)
	return path, os.WriteFile(path, data, 0600)
}

func (a *App) bindBridge() error {
	// TrustedOrigin is enforced by native WebView2's message source, not a JS claim.
	if err := a.view.Bind("desktopSession", func(raw string) error {
		var session events.Session
		if raw != "" {
			if len(raw) > 4096 {
				return fmt.Errorf("invalid session response")
			}
			if err := json.Unmarshal([]byte(raw), &session); err != nil {
				return err
			}
			if session.Ticket == "" || len(session.Account) > 50 {
				return fmt.Errorf("invalid session")
			}
		}
		if a.account != session.Account {
			a.notifier.Clear()
			a.quick.Close()
			a.account = session.Account
		}
		a.notifier.ticket = session.Ticket
		a.client.ReplaceSession(session)
		return nil
	}); err != nil {
		return err
	}
	if err := a.view.Bind("desktopStatus", func(message string) {
		if len(message) < 150 {
			a.setStatus(message)
		}
	}); err != nil {
		return err
	}
	if err := a.view.Bind("desktopPageState", func(raw string) error {
		if len(raw) > 1024 {
			return fmt.Errorf("invalid page state")
		}
		var state PageState
		if err := json.Unmarshal([]byte(raw), &state); err != nil {
			return err
		}
		state.Updated = time.Now()
		a.page.Store(state)
		return nil
	}); err != nil {
		return err
	}
	return a.view.Bind("desktopOpenExternal", func(target string) error { return OpenExternal(target) })
}

func (a *App) notify(event events.Event) error {
	if !a.enabled.Load() {
		return nil
	}
	if a.quick.Suppresses(event.Path) {
		return nil
	}
	if state, ok := a.page.Load().(PageState); ok && state.Suppresses(event.Path, time.Now()) {
		// A hidden/minimized app or a different chat must still show the notification.
		foreground, _, _ := user32.NewProc("GetForegroundWindow").Call()
		if foreground == uintptr(a.view.Window()) {
			return nil
		}
	}
	return a.notifier.Show(event)
}

func (a *App) setStatus(status string) {
	log.Printf("Notification connection: %s", status)
	if a.closing.Load() {
		return
	}
	a.view.Dispatch(func() {
		a.view.SetTitle("SessionLender — " + status)
		if a.tray != nil {
			a.tray.SetStatus(status)
		}
	})
}

func (a *App) open(path string) {
	if path == "" {
		path = "/"
	}
	target, err := config.Destination(path)
	if err != nil {
		return
	}
	if a.closing.Load() {
		return
	}
	a.view.Dispatch(func() { a.tray.Show(); a.view.Navigate(target) })
}

func (a *App) quit() { a.closing.Store(true); a.view.Terminate() }
func (a *App) toggleNotifications() {
	next := !a.enabled.Load()
	a.enabled.Store(next)
	a.tray.NotificationsEnabled = next
	if !next {
		a.notifier.Clear()
	}
	if next {
		a.setStatus("Сповіщення увімкнено")
	} else {
		a.setStatus("Сповіщення вимкнено")
	}
}
func (a *App) testNotification() {
	go func() {
		if err := a.notifier.Show(events.Event{Title: "Тестове сповіщення", Nickname: "@SessionLender", Body: "Власні сповіщення працюють. Натисніть, щоб відкрити подію.", Path: "/messages/notifications/"}); err != nil {
			log.Printf("Test notification: %v", err)
			a.view.Dispatch(func() { MessageBox("Сповіщення Windows", strings.TrimSpace(err.Error())) })
		}
	}()
}

func (a *App) openQuickChat(path string) {
	if !isChatPath(path) {
		a.open(path)
		return
	}
	a.quick.Open(path)
}
