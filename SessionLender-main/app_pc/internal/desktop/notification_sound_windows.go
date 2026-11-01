//go:build windows

package desktop

import (
	"fmt"
	"log"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
)

var mciSendString = windows.NewLazySystemDLL("winmm.dll").NewProc("mciSendStringW")

type NotificationSound struct{ ready bool }

func soundCommand(command string) error {
	result, _, _ := mciSendString.Call(uintptr(unsafe.Pointer(utf16(command))), 0, 0, 0)
	if result != 0 {
		return fmt.Errorf("MCI error %d", result)
	}
	return nil
}

func NewNotificationSound(path string) *NotificationSound {
	sound := &NotificationSound{}
	if strings.Contains(path, `"`) {
		return sound
	}
	err := soundCommand(`open "` + path + `" type mpegvideo alias sessionlender_notice`)
	if err != nil {
		log.Printf("Notification sound: %v", err)
		return sound
	}
	sound.ready = true
	return sound
}

// MCI playback is asynchronous. A burst restarts one sound instead of stacking it.
func (sound *NotificationSound) Play() {
	if !sound.ready {
		return
	}
	if err := soundCommand("play sessionlender_notice from 0"); err != nil {
		log.Printf("Notification sound: %v", err)
	}
}
func (sound *NotificationSound) Close() {
	if sound.ready {
		_ = soundCommand("close sessionlender_notice")
		sound.ready = false
	}
}
