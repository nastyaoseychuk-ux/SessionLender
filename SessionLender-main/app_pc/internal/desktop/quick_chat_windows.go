//go:build windows

package desktop

import (
	"encoding/json"
	"log"
	"runtime"
	"strings"
	"sync"
	"time"
	"unsafe"

	webview "github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
	"sessionlender/desktop/internal/config"
)

// QuickChat owns a separate UI thread and shares only the browser login profile.
// Its close button terminates that thread's message loop, never the main app.
type QuickChat struct {
	mu             sync.Mutex
	view           webview.WebView
	starting       bool
	generation     uint64
	path, dataPath string
	page           PageState
	activate       func(string)
}

func NewQuickChat(dataPath string, activate func(string)) *QuickChat {
	return &QuickChat{dataPath: dataPath, activate: activate}
}

func (q *QuickChat) Open(path string) {
	if !isChatPath(path) {
		return
	}
	q.mu.Lock()
	q.path = path
	if q.view != nil {
		view := q.view
		q.mu.Unlock()
		view.Dispatch(func() {
			target, _ := config.Destination(path)
			view.Navigate(target)
			showWindow.Call(uintptr(view.Window()), 9)
			user32.NewProc("SetForegroundWindow").Call(uintptr(view.Window()))
		})
		return
	}
	if q.starting {
		q.mu.Unlock()
		return
	}
	q.starting = true
	q.generation++
	generation := q.generation
	q.mu.Unlock()
	go q.run(generation)
}

func (q *QuickChat) run(generation uint64) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	// The dependency initializes COM only on the main thread. Each extra
	// WebView2 thread needs its own single-threaded COM apartment.
	ole32 := windows.NewLazySystemDLL("ole32.dll")
	result, _, _ := ole32.NewProc("CoInitializeEx").Call(0, 2)
	if int32(result) < 0 {
		log.Printf("Quick chat COM initialization: %08x", result)
		q.mu.Lock()
		if q.generation == generation {
			q.starting = false
		}
		q.mu.Unlock()
		return
	}
	defer ole32.NewProc("CoUninitialize").Call()
	view := webview.NewWithOptions(webview.WebViewOptions{
		DataPath: q.dataPath, TrustedOrigin: config.ServerURL, AutoFocus: true,
		WindowOptions: webview.WindowOptions{Title: "SessionLender — швидка відповідь", Width: 440, Height: 440, IconId: 1},
	})
	q.mu.Lock()
	if view == nil || q.generation != generation {
		if q.generation == generation {
			q.starting = false
		}
		q.mu.Unlock()
		if view != nil {
			user32.NewProc("DestroyWindow").Call(uintptr(view.Window()))
		}
		if view == nil {
			log.Print("Quick chat: WebView2 initialization failed")
		}
		return
	}
	q.view, q.starting = view, false
	path := q.path
	q.mu.Unlock()
	defer func() {
		q.mu.Lock()
		if q.view == view {
			q.view = nil
			q.page = PageState{}
		}
		q.mu.Unlock()
	}()
	hwnd := uintptr(view.Window())
	style := uintptr(0x80000000) // Frameless WS_POPUP; web content supplies controls.
	user32.NewProc("SetWindowLongPtrW").Call(hwnd, ^uintptr(15), style)
	user32.NewProc("SetWindowLongPtrW").Call(hwnd, ^uintptr(19), 0x80)
	positionQuickChat(hwnd)
	applyGlass(hwnd)
	// Windows 11 DWM corners; explicit region also supports Windows 10.
	region, _, _ := gdi32.NewProc("CreateRoundRectRgn").Call(0, 0, 441, 441, 40, 40)
	if region != 0 {
		user32.NewProc("SetWindowRgn").Call(hwnd, region, 1)
	}
	bind := func(name string, callback any) bool {
		if err := view.Bind(name, callback); err != nil {
			log.Printf("Quick chat binding: %v", err)
			return false
		}
		return true
	}
	if !bind("quickClose", func() { view.Dispatch(view.Destroy) }) ||
		!bind("quickOpen", func() { q.mu.Lock(); target := q.path; q.mu.Unlock(); q.activate(target) }) ||
		!bind("quickDrag", func() {
			view.Dispatch(func() { user32.NewProc("ReleaseCapture").Call(); user32.NewProc("SendMessageW").Call(hwnd, 0xA1, 2, 0) })
		}) ||
		!bind("quickPageState", func(raw string) {
			if len(raw) > 1024 {
				return
			}
			var state PageState
			if json.Unmarshal([]byte(raw), &state) != nil {
				return
			}
			state.Updated = time.Now()
			q.mu.Lock()
			q.page = state
			q.mu.Unlock()
		}) || !bind("quickExternal", func(target string) error { return OpenExternal(target) }) {
		user32.NewProc("DestroyWindow").Call(hwnd)
		return
	}
	script, _ := assets.ReadFile("quick_chat.js")
	origin, _ := json.Marshal(config.ServerURL)
	view.Init(strings.ReplaceAll(string(script), "__SERVER_ORIGIN__", string(origin)))
	target, _ := config.Destination(path)
	view.Navigate(target)
	view.Run()
}

func positionQuickChat(hwnd uintptr) {
	monitor, _, _ := user32.NewProc("MonitorFromWindow").Call(hwnd, 2)
	info := monitorInfo{}
	info.Size = uint32(unsafe.Sizeof(info))
	if result, _, _ := user32.NewProc("GetMonitorInfoW").Call(monitor, uintptr(unsafe.Pointer(&info))); result != 0 {
		user32.NewProc("SetWindowPos").Call(hwnd, ^uintptr(0), uintptr(info.Work.Right-456), uintptr(info.Work.Bottom-456), 440, 440, 0x20|0x40)
	}
}

func (q *QuickChat) Suppresses(path string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.view == nil || !q.page.Suppresses(path, time.Now()) {
		return false
	}
	foreground, _, _ := user32.NewProc("GetForegroundWindow").Call()
	return foreground == uintptr(q.view.Window())
}

func (q *QuickChat) Close() {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.generation++
	q.starting = false
	q.page = PageState{}
	if q.view != nil {
		view := q.view
		q.view = nil
		view.Dispatch(view.Destroy)
	}
}
