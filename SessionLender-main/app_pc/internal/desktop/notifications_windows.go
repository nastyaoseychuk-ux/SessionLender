//go:build windows

package desktop

import (
	"fmt"
	"image"
	"log"
	"os"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
	"sessionlender/desktop/internal/events"
)

const (
	popupWidth             = 420
	popupHeight            = 148
	popupLifetime          = 9 * time.Second
	popupMessagePaint      = 0x0f
	popupMessageDestroy    = 2
	popupMessageTimer      = 0x113
	popupMessageMouseMove  = 0x200
	popupMessageMouseLeave = 0x2a3
	popupMessageClick      = 0x202
)

type rectangle struct{ Left, Top, Right, Bottom int32 }
type paintStruct struct {
	DC                 uintptr
	Erase              int32
	Paint              rectangle
	Restore, IncUpdate int32
	Reserved           [32]byte
}
type windowClass struct {
	Size, Style                        uint32
	Procedure                          uintptr
	ClassExtra, WindowExtra            int32
	Instance, Icon, Cursor, Background uintptr
	MenuName, ClassName                *uint16
	SmallIcon                          uintptr
}
type monitorInfo struct {
	Size          uint32
	Monitor, Work rectangle
	Flags         uint32
}
type mouseTracking struct {
	Size, Flags uint32
	Window      uintptr
	HoverTime   uint32
}

type Notifier struct {
	parent        uintptr
	dispatch      func(func())
	activate      func(string)
	quickReply    func(string)
	playSound     func()
	defaultAvatar image.Image
	windows       map[uintptr]*popup
	queue         []events.Event
	procedure     uintptr
	className     *uint16
	instance      uintptr
	ticket        string
	sequence      uint64
}
type popup struct {
	owner                         *Notifier
	hwnd                          uintptr
	order                         uint64
	event                         events.Event
	avatar                        image.Image
	ticket                        string
	hover                         bool
	deadline                      time.Time
	scale                         int32
	bodyFont, nameFont, smallFont uintptr
}

func NewNotifier(parent uintptr, icon string, activate, quickReply func(string), playSound func(), dispatch func(func())) (*Notifier, error) {
	file, err := os.Open(icon)
	if err != nil {
		return nil, err
	}
	avatar, _, err := image.Decode(file)
	file.Close()
	if err != nil {
		return nil, err
	}
	n := &Notifier{parent: parent, activate: activate, quickReply: quickReply, playSound: playSound, dispatch: dispatch, defaultAvatar: avatar, windows: map[uintptr]*popup{}, className: utf16("SessionLender.Notification.v2")}
	n.procedure = syscall.NewCallback(n.windowProcedure)
	var module windows.Handle
	err = windows.GetModuleHandleEx(0, nil, &module)
	if err != nil {
		return nil, err
	}
	n.instance = uintptr(module)
	cursor, _, _ := user32.NewProc("LoadCursorW").Call(0, 32512)
	class := windowClass{Procedure: n.procedure, Instance: n.instance, Cursor: cursor, ClassName: n.className}
	class.Size = uint32(unsafe.Sizeof(class))
	result, _, err := user32.NewProc("RegisterClassExW").Call(uintptr(unsafe.Pointer(&class)))
	if result == 0 {
		return nil, fmt.Errorf("notification window registration: %w", err)
	}
	return n, nil
}

// Show may be called by a background receiver. All window work runs on the UI thread.
func (n *Notifier) Show(event events.Event) error {
	result := make(chan error, 1)
	n.dispatch(func() {
		if len(n.windows) >= 3 {
			if len(n.queue) >= 30 {
				n.queue = n.queue[1:]
			}
			n.queue = append(n.queue, event)
			result <- nil
			return
		}
		result <- n.createPopup(event)
	})
	return <-result
}

func (n *Notifier) Clear() {
	n.queue = nil
	for hwnd := range n.windows {
		user32.NewProc("DestroyWindow").Call(hwnd)
	}
}

func (n *Notifier) createPopup(event events.Event) error {
	n.sequence++
	p := &popup{owner: n, event: event, avatar: n.defaultAvatar, deadline: time.Now().Add(popupLifetime), scale: 96, order: n.sequence, ticket: n.ticket}
	if proc := user32.NewProc("GetDpiForWindow"); proc.Find() == nil {
		dpi, _, _ := proc.Call(n.parent)
		if dpi > 0 {
			p.scale = int32(dpi)
		}
	}
	// TOOLWINDOW keeps it out of Alt+Tab; NOACTIVATE preserves the current input focus.
	hwnd, _, err := user32.NewProc("CreateWindowExW").Call(0x80|0x08000000|0x8|0x80000, uintptr(unsafe.Pointer(n.className)), uintptr(unsafe.Pointer(utf16("SessionLender"))), 0x80000000, 0, 0, uintptr(p.px(popupWidth)), uintptr(p.px(popupHeight)), 0, 0, n.instance, 0)
	if hwnd == 0 {
		return fmt.Errorf("notification window: %w", err)
	}
	p.hwnd = hwnd
	n.windows[hwnd] = p
	p.bodyFont = createFont(p.px(14), 400)
	p.nameFont = createFont(p.px(15), 650)
	p.smallFont = createFont(p.px(11), 400)
	applyGlass(hwnd)
	n.reposition()
	p.render()
	showWindow.Call(hwnd, 4)
	user32.NewProc("SetTimer").Call(hwnd, 1, 150, 0)
	go n.loadAvatar(p, event.Avatar)
	if n.playSound != nil {
		n.playSound()
	}
	return nil
}

// Keep drawing, window size and pointer coordinates on the same 77% scale (10% larger than the compact layout).
func (p *popup) px(value int32) int32 { return value * p.scale * 77 / (96 * 100) }
func (n *Notifier) reposition() {
	monitor, _, _ := user32.NewProc("MonitorFromWindow").Call(n.parent, 2)
	info := monitorInfo{}
	info.Size = uint32(unsafe.Sizeof(info))
	if result, _, _ := user32.NewProc("GetMonitorInfoW").Call(monitor, uintptr(unsafe.Pointer(&info))); result == 0 {
		return
	}
	// Creation order, rather than map order, keeps positions stable.
	popups := n.orderedPopups()
	bottom := info.Work.Bottom
	for i := len(popups) - 1; i >= 0; i-- {
		p := popups[i]
		bottom -= p.px(popupHeight + 12)
		x := info.Work.Right - p.px(popupWidth+16)
		user32.NewProc("SetWindowPos").Call(p.hwnd, ^uintptr(0), uintptr(x), uintptr(bottom), 0, 0, 0x1|0x10)
	}
}
func (n *Notifier) windowProcedure(hwnd, msg, wp, lp uintptr) uintptr {
	p := n.windows[hwnd]
	if p == nil {
		result, _, _ := user32.NewProc("DefWindowProcW").Call(hwnd, msg, wp, lp)
		return result
	}
	switch msg {
	case 0x14:
		return 1 // Background is supplied by DWM, not a window frame brush.
	case popupMessagePaint:
		p.paint()
		return 0
	case popupMessageMouseMove:
		p.hover = true
		tracking := mouseTracking{Flags: 2, Window: hwnd}
		tracking.Size = uint32(unsafe.Sizeof(tracking))
		user32.NewProc("TrackMouseEvent").Call(uintptr(unsafe.Pointer(&tracking)))
		return 0
	case popupMessageMouseLeave:
		p.hover = false
		p.deadline = time.Now().Add(3 * time.Second)
		return 0
	case popupMessageTimer:
		if !p.hover && time.Now().After(p.deadline) {
			user32.NewProc("DestroyWindow").Call(hwnd)
		}
		return 0
	case popupMessageClick:
		x := int32(int16(lp&0xffff)) * (96 * 100) / (p.scale * 77)
		y := int32(int16((lp>>16)&0xffff)) * (96 * 100) / (p.scale * 77)
		if x >= 379 && y < 39 {
			user32.NewProc("DestroyWindow").Call(hwnd)
			return 0
		}
		if x >= 345 && x < 379 && y < 39 {
			n.activate(p.event.Path)
		} else {
			n.quickReply(p.event.Path)
		}
		user32.NewProc("DestroyWindow").Call(hwnd)
		return 0
	case popupMessageDestroy:
		user32.NewProc("KillTimer").Call(hwnd, 1)
		for _, font := range []uintptr{p.bodyFont, p.nameFont, p.smallFont} {
			gdi32.NewProc("DeleteObject").Call(font)
		}
		delete(n.windows, hwnd)
		if len(n.queue) > 0 {
			event := n.queue[0]
			n.queue = n.queue[1:]
			if err := n.createPopup(event); err != nil {
				log.Print(err)
			}
		}
		n.reposition()
		return 0
	}
	result, _, _ := user32.NewProc("DefWindowProcW").Call(hwnd, msg, wp, lp)
	return result
}
