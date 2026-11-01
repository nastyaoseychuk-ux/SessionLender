package events

import (
	"context"
	"encoding/json"
	"github.com/gorilla/websocket"
	"log"
	"math/rand/v2"
	"net/http"
	"sessionlender/desktop/internal/config"
	"sync"
	"time"
)

type Client struct {
	endpoint       string
	streamEndpoint string
	pending        map[string]bool
	mu             sync.Mutex
	cancel         context.CancelFunc
	session        Session
	history        *History
	notify         func(Event) error
	status         func(string)
}

func NewClient(history *History, notify func(Event) error, status func(string)) *Client {
	return &Client{endpoint: config.WebSocketURL(), streamEndpoint: config.ServerURL + "/desktop/events/", pending: map[string]bool{}, history: history, notify: notify, status: status}
}

// ReplaceSession is called only after a same-origin, CSRF-protected login exchange.
func (c *Client) ReplaceSession(next Session) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if next == c.session {
		return
	}
	if c.cancel != nil {
		c.cancel()
	}
	c.session = next
	if next.Ticket == "" || next.Account == "" {
		c.status("Увійдіть для сповіщень")
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	c.cancel = cancel
	go c.run(ctx, next)
}

func (c *Client) Stop() { c.ReplaceSession(Session{}) }

func (c *Client) run(ctx context.Context, session Session) {
	delay := time.Second
	for ctx.Err() == nil {
		connected, unauthorized := c.connect(ctx, session)
		if !connected && ctx.Err() == nil {
			c.status("WebSocket недоступний — підключення потоку…")
			connected, unauthorized = c.stream(ctx, session)
		}
		if ctx.Err() != nil {
			return
		}
		if unauthorized {
			c.status("Сесію завершено — відкрийте додаток")
			return
		}
		if connected {
			delay = time.Second
		}
		c.status("Відновлення з’єднання…")
		wait := delay + time.Duration(rand.IntN(700))*time.Millisecond
		timer := time.NewTimer(wait)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
		}
		delay = min(delay*2, 30*time.Second)
	}
}

func (c *Client) connect(ctx context.Context, session Session) (bool, bool) {
	headers := http.Header{"Origin": {config.ServerURL}, "Authorization": {"Bearer " + session.Ticket}}
	dialer := websocket.Dialer{HandshakeTimeout: 15 * time.Second, Proxy: http.ProxyFromEnvironment}
	conn, response, err := dialer.DialContext(ctx, c.endpoint, headers)
	if err != nil {
		if response != nil {
			log.Printf("WebSocket handshake HTTP %d", response.StatusCode)
			response.Body.Close()
			return false, response.StatusCode == 401 || response.StatusCode == 403
		}
		log.Printf("WebSocket transport unavailable: %v", err)
		return false, false
	}
	defer conn.Close()
	done := make(chan struct{})
	defer close(done)
	go c.keepAlive(ctx, conn, done)
	conn.SetReadLimit(64 * 1024)
	conn.SetReadDeadline(time.Now().Add(90 * time.Second))
	conn.SetPongHandler(func(string) error { return conn.SetReadDeadline(time.Now().Add(90 * time.Second)) })
	c.status("Сповіщення підключені")
	for ctx.Err() == nil {
		_, raw, err := conn.ReadMessage()
		if err != nil {
			return true, websocket.IsCloseError(err, 4403, 1008)
		}
		c.consume(ctx, session, raw)
	}
	return true, false
}

func (c *Client) keepAlive(ctx context.Context, conn *websocket.Conn, done <-chan struct{}) {
	ticker := time.NewTicker(25 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			conn.Close()
			return
		case <-done:
			return
		case <-ticker.C:
			// Protocol-level pings keep the socket healthy; they do not query messages.
			if conn.WriteControl(websocket.PingMessage, nil, time.Now().Add(5*time.Second)) != nil {
				conn.Close()
				return
			}
		}
	}
}

func (c *Client) deliver(ctx context.Context, account string, event Event) {
	key := account + "/" + event.ID
	c.mu.Lock()
	if ctx.Err() != nil || c.history.Has(account, event.ID) || c.pending[key] {
		c.mu.Unlock()
		return
	}
	c.pending[key] = true
	c.mu.Unlock()
	// Native painting runs on the UI thread. Never hold the session mutex while
	// waiting for it, because login/renewal callbacks also run on that thread.
	err := c.notify(event)
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.pending, key)
	if err != nil {
		log.Printf("Notification window failed: %v", err)
		return
	}
	if err = c.history.Remember(account, event.ID); err != nil {
		log.Printf("Notification history: %v", err)
	}
}

func (c *Client) consume(ctx context.Context, session Session, raw []byte) {
	var event Event
	if json.Unmarshal(raw, &event) != nil || !event.Valid() {
		return
	}
	if _, err := config.Destination(event.Path); err != nil {
		return
	}
	log.Printf("Server event received: %s", event.ID)
	c.deliver(ctx, session.Account, event)
}
