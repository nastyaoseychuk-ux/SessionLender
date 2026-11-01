//go:build windows

package desktop

import (
	"fmt"
	"golang.org/x/sys/windows"
	"net/url"
	"strings"
	"syscall"
	"unsafe"
)

var (
	user32           = windows.NewLazySystemDLL("user32.dll")
	shell32          = windows.NewLazySystemDLL("shell32.dll")
	comctl32         = windows.NewLazySystemDLL("comctl32.dll")
	showWindow       = user32.NewProc("ShowWindow")
	foregroundWindow = user32.NewProc("SetForegroundWindow")
	registerMessage  = user32.NewProc("RegisterWindowMessageW")
)

func utf16(s string) *uint16 { value, _ := windows.UTF16PtrFromString(s); return value }
func MessageBox(title, body string) {
	user32.NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(utf16(body))), uintptr(unsafe.Pointer(utf16(title))), 0x10)
}
func OpenExternal(target string) error {
	u, err := url.Parse(target)
	if err != nil || u.Host == "" || u.User != nil || (u.Scheme != "https" && u.Scheme != "http") || strings.ContainsAny(target, "\r\n") {
		return fmt.Errorf("unsupported external link")
	}
	result, _, _ := shell32.NewProc("ShellExecuteW").Call(0, uintptr(unsafe.Pointer(utf16("open"))), uintptr(unsafe.Pointer(utf16(target))), 0, 0, 1)
	if result <= 32 {
		return fmt.Errorf("не вдалося відкрити посилання: %d", result)
	}
	return nil
}
func SingleInstance() (func(), bool, error) {
	handle, err := windows.CreateMutex(nil, false, utf16("Local\\MysterSay.SessionLender.Desktop"))
	if err == windows.ERROR_ALREADY_EXISTS {
		if handle != 0 {
			windows.CloseHandle(handle)
		}
		message, _, _ := registerMessage.Call(uintptr(unsafe.Pointer(utf16("SessionLender.ShowWindow.v1"))))
		user32.NewProc("SendNotifyMessageW").Call(0xffff, message, 0, 0)
		return func() {}, true, nil
	}
	if err != nil {
		return func() {}, false, err
	}
	return func() { windows.CloseHandle(handle) }, false, nil
}

type point struct{ X, Y int32 }
type notifyIconData struct {
	Size                uint32
	Window              uintptr
	ID, Flags, Callback uint32
	Icon                uintptr
	Tip                 [128]uint16
	State, StateMask    uint32
	Info                [256]uint16
	Timeout             uint32
	InfoTitle           [64]uint16
	InfoFlags           uint32
	GUID                windows.GUID
	BalloonIcon         uintptr
}

const (
	wmClose           = 0x10
	wmTray            = 0x8000 + 17
	menuOpen          = 1
	menuNotifications = 2
	menuToggle        = 3
	menuTest          = 4
	menuExit          = 5
)

type Tray struct {
	hwnd, icon, callback, showMessage, taskbarMessage uintptr
	data                                              notifyIconData
	NotificationsEnabled                              bool
	open                                              func(string)
	quit, toggle, test                                func()
}

func NewTray(hwnd uintptr, iconPath string, open func(string), quit, toggle, test func()) (*Tray, error) {
	t := &Tray{hwnd: hwnd, open: open, quit: quit, toggle: toggle, test: test, NotificationsEnabled: true}
	t.icon, _, _ = user32.NewProc("LoadImageW").Call(0, uintptr(unsafe.Pointer(utf16(iconPath))), 1, 0, 0, 0x10|0x40)
	if t.icon == 0 {
		return nil, fmt.Errorf("не вдалося завантажити іконку трея")
	}
	user32.NewProc("SendMessageW").Call(hwnd, 0x80, 0, t.icon)
	user32.NewProc("SendMessageW").Call(hwnd, 0x80, 1, t.icon)
	t.data = notifyIconData{Window: hwnd, ID: 1, Flags: 1 | 2 | 4, Callback: wmTray, Icon: t.icon}
	t.data.Size = uint32(unsafe.Sizeof(t.data))
	t.showMessage, _, _ = registerMessage.Call(uintptr(unsafe.Pointer(utf16("SessionLender.ShowWindow.v1"))))
	t.taskbarMessage, _, _ = registerMessage.Call(uintptr(unsafe.Pointer(utf16("TaskbarCreated"))))
	t.callback = syscall.NewCallback(t.windowProcedure)
	ok, _, _ := comctl32.NewProc("SetWindowSubclass").Call(hwnd, t.callback, 1, 0)
	if ok == 0 {
		return nil, fmt.Errorf("не вдалося підключити обробник вікна")
	}
	t.SetStatus("Увійдіть для сповіщень")
	ok, _, _ = shell32.NewProc("Shell_NotifyIconW").Call(0, uintptr(unsafe.Pointer(&t.data)))
	if ok == 0 {
		t.Close()
		return nil, fmt.Errorf("Windows не створив іконку трея")
	}
	return t, nil
}
func (t *Tray) SetStatus(status string) {
	t.data.Tip = [128]uint16{}
	text, _ := windows.UTF16FromString("SessionLender — " + status)
	copy(t.data.Tip[:127], text)
	shell32.NewProc("Shell_NotifyIconW").Call(1, uintptr(unsafe.Pointer(&t.data)))
}
func (t *Tray) Show() { showWindow.Call(t.hwnd, 9); foregroundWindow.Call(t.hwnd) }
func (t *Tray) Close() {
	shell32.NewProc("Shell_NotifyIconW").Call(2, uintptr(unsafe.Pointer(&t.data)))
	comctl32.NewProc("RemoveWindowSubclass").Call(t.hwnd, t.callback, 1)
	if t.icon != 0 {
		user32.NewProc("DestroyIcon").Call(t.icon)
		t.icon = 0
	}
}
func (t *Tray) windowProcedure(hwnd, msg, wp, lp, id, data uintptr) uintptr {
	switch msg {
	case wmClose:
		showWindow.Call(hwnd, 0)
		return 0
	case t.showMessage:
		t.Show()
		return 0
	case t.taskbarMessage:
		shell32.NewProc("Shell_NotifyIconW").Call(0, uintptr(unsafe.Pointer(&t.data)))
		return 0
	case wmTray:
		if lp == 0x203 {
			t.Show()
		}
		if lp == 0x205 {
			t.showMenu()
		}
		return 0
	}
	result, _, _ := comctl32.NewProc("DefSubclassProc").Call(hwnd, msg, wp, lp)
	return result
}
func (t *Tray) showMenu() {
	menu, _, _ := user32.NewProc("CreatePopupMenu").Call()
	defer user32.NewProc("DestroyMenu").Call(menu)
	add := func(id uintptr, title string, flags uintptr) {
		user32.NewProc("AppendMenuW").Call(menu, flags, id, uintptr(unsafe.Pointer(utf16(title))))
	}
	add(menuOpen, "Відкрити SessionLender", 0)
	add(menuNotifications, "Сповіщення", 0)
	flags := uintptr(0)
	if t.NotificationsEnabled {
		flags = 8
	}
	add(menuToggle, "Увімкнути сповіщення", flags)
	add(menuTest, "Перевірити власне сповіщення", 0)
	add(0, "", 0x800)
	add(menuExit, "Вийти", 0)
	var cursor point
	user32.NewProc("GetCursorPos").Call(uintptr(unsafe.Pointer(&cursor)))
	foregroundWindow.Call(t.hwnd)
	selected, _, _ := user32.NewProc("TrackPopupMenu").Call(menu, 0x100|0x2, uintptr(cursor.X), uintptr(cursor.Y), 0, t.hwnd, 0)
	switch selected {
	case menuOpen:
		t.Show()
	case menuNotifications:
		t.open("/messages/notifications/")
	case menuToggle:
		t.toggle()
	case menuTest:
		t.test()
	case menuExit:
		t.quit()
	}
	user32.NewProc("PostMessageW").Call(t.hwnd, 0, 0, 0)
}
