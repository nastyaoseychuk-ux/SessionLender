//go:build windows

package desktop

import (
	"fmt"
	"unsafe"
)

// Let a temporary native Edit control own the clipboard allocation and lifetime.
func copyText(owner uintptr, value string) error {
	edit, _, _ := user32.NewProc("CreateWindowExW").Call(0,
		uintptr(unsafe.Pointer(utf16("EDIT"))), uintptr(unsafe.Pointer(utf16(value))),
		0x40000000|0x4|0x800, 0, 0, 1, 1, owner, 0, 0, 0)
	if edit == 0 {
		return fmt.Errorf("clipboard control creation failed")
	}
	defer user32.NewProc("DestroyWindow").Call(edit)
	user32.NewProc("SendMessageW").Call(edit, 0xB1, 0, ^uintptr(0)) // EM_SETSEL: all text.
	user32.NewProc("SendMessageW").Call(edit, 0x301, 0, 0)          // WM_COPY.
	return nil
}
