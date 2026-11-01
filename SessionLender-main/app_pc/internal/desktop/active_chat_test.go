package desktop

import (
	"testing"
	"time"
)

func TestOnlyTheVisibleFocusedChatIsSuppressed(t *testing.T) {
	now := time.Now()
	state := PageState{Path: "/messages/12/", Visible: true, Focused: true, Updated: now}
	if !state.Suppresses("/messages/12/", now) {
		t.Fatal("active chat not suppressed")
	}
	for _, path := range []string{"/messages/13/", "/rooms/12/", "/messages/notifications/"} {
		if state.Suppresses(path, now) {
			t.Fatal("unrelated event suppressed")
		}
	}
	state.Visible = false
	if state.Suppresses("/messages/12/", now) {
		t.Fatal("hidden chat suppressed")
	}
	state.Visible = true
	state.Focused = false
	if state.Suppresses("/messages/12/", now) {
		t.Fatal("background chat suppressed")
	}
	state.Focused = true
	state.Updated = now.Add(-time.Minute)
	if state.Suppresses("/messages/12/", now) {
		t.Fatal("stale page suppressed")
	}
}
func TestGlassHasTransparentCornersAndTranslucentCenter(t *testing.T) {
	surface := glassSurface(420, 178, 24)
	if surface.RGBAAt(0, 0).A != 0 {
		t.Fatal("square opaque corner")
	}
	center := surface.RGBAAt(200, 80)
	if center.A == 0 || center.A == 255 {
		t.Fatal("opaque glass background")
	}
}

func TestQuickReplyAcceptsOnlyChatDestinations(t *testing.T) {
	for _, path := range []string{"/messages/1/", "/messages/1234/"} {
		if !isChatPath(path) {
			t.Errorf("chat rejected: %q", path)
		}
	}
	for _, path := range []string{"/", "/messages/notifications/", "/rooms/1/", "https://example.com/messages/1/", "//example.com/messages/1/", "/messages/1/?next=/", "/messages/1/extra"} {
		if isChatPath(path) {
			t.Errorf("non-chat accepted: %q", path)
		}
	}
}
