package events

import (
	"context"
	"github.com/gorilla/websocket"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestHistoryIsAccountScopedAndPersistent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "seen.json")
	h := LoadHistory(path)
	if err := h.Remember("1", "message:8"); err != nil {
		t.Fatal(err)
	}
	h = LoadHistory(path)
	if !h.Has("1", "message:8") || h.Has("2", "message:8") {
		t.Fatal("account isolation failed")
	}
}

func TestSocketFiltersDuplicatesAndUnsafeLinks(t *testing.T) {
	upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-ticket" {
			t.Error("missing authorization")
		}
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		notice := Event{Type: "notification", ID: "message:1", Title: "Привіт", Body: "Текст", Path: "/messages/1/"}
		conn.WriteJSON(notice)
		conn.WriteJSON(notice)
		notice.ID = "message:2"
		notice.Path = "//evil.test/"
		conn.WriteJSON(notice)
		conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
	}))
	defer server.Close()
	var shown []Event
	client := NewClient(LoadHistory(filepath.Join(t.TempDir(), "seen.json")), func(e Event) error { shown = append(shown, e); return nil }, func(string) {})
	client.endpoint = "ws" + strings.TrimPrefix(server.URL, "http")
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	connected, denied := client.connect(ctx, Session{Ticket: "test-ticket", Account: "1"})
	if !connected || denied || len(shown) != 1 {
		t.Fatalf("unexpected delivery: connected=%v denied=%v events=%d", connected, denied, len(shown))
	}
}

func TestSessionCanChangeWhileNotificationWaitsForUI(t *testing.T) {
	started, release, finished := make(chan struct{}), make(chan struct{}), make(chan struct{})
	client := NewClient(LoadHistory(filepath.Join(t.TempDir(), "seen.json")), func(Event) error { close(started); <-release; return nil }, func(string) {})
	ctx, cancel := context.WithCancel(context.Background())
	client.session = Session{Ticket: "old", Account: "1"}
	client.cancel = cancel
	go func() { client.deliver(ctx, "1", Event{ID: "one"}); close(finished) }()
	<-started
	swapped := make(chan struct{})
	go func() { client.Stop(); close(swapped) }()
	select {
	case <-swapped:
	case <-time.After(time.Second):
		t.Error("UI/session deadlock")
	}
	close(release)
	<-finished
}

func TestEventStreamDeliversAndDeduplicates(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer opaque" {
			t.Error("stream missing key")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		event := `data: {"type":"notification","id":"message:4","title":"Message","body":"Stream text","path":"/messages/4/"}` + "\n\n"
		w.Write([]byte("data: {\"type\":\"ready\"}\n\n" + event + event))
	}))
	defer server.Close()
	shown := 0
	client := NewClient(LoadHistory(filepath.Join(t.TempDir(), "seen.json")), func(e Event) error {
		shown++
		if e.Body != "Stream text" {
			t.Error(e.Body)
		}
		return nil
	}, func(string) {})
	client.streamEndpoint = server.URL
	connected, denied := client.stream(context.Background(), Session{Account: "1", Ticket: "opaque"})
	if !connected || denied || shown != 1 {
		t.Fatalf("stream delivery: connected=%v denied=%v shown=%d", connected, denied, shown)
	}
}
