package events

import (
	"bufio"
	"context"
	"log"
	"net/http"

	"strings"
	"sync/atomic"
	"time"
)

// One open stream receives server events; this never polls for messages.
func (c *Client) stream(ctx context.Context, session Session) (bool, bool) {
	readContext, cancelRead := context.WithCancel(ctx)
	defer cancelRead()
	request, err := http.NewRequestWithContext(readContext, http.MethodGet, c.streamEndpoint, nil)
	if err != nil {
		return false, false
	}
	request.Header.Set("Authorization", "Bearer "+session.Ticket)
	request.Header.Set("Accept", "text/event-stream")
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = 20 * time.Second
	client := http.Client{Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	defer transport.CloseIdleConnections()
	response, err := client.Do(request)
	if err != nil {
		log.Printf("Event stream transport: %v", err)
		return false, false
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		log.Printf("Event stream HTTP %d", response.StatusCode)
		return false, response.StatusCode == 401 || response.StatusCode == 403
	}
	if !strings.HasPrefix(response.Header.Get("Content-Type"), "text/event-stream") {
		log.Print("Unexpected event stream content type")
		return false, false
	}
	c.status("Сповіщення підключені — потік SSE")
	var lastFrame atomic.Int64
	lastFrame.Store(time.Now().UnixNano())
	done := make(chan struct{})
	defer close(done)
	go func() {
		timer := time.NewTicker(10 * time.Second)
		defer timer.Stop()
		for {
			select {
			case <-done:
				return
			case <-readContext.Done():
				return
			case <-timer.C:
				if time.Since(time.Unix(0, lastFrame.Load())) > 65*time.Second {
					cancelRead()
					return
				}
			}
		}
	}()
	scanner := bufio.NewScanner(response.Body)
	scanner.Buffer(make([]byte, 4096), 64*1024)
	var data strings.Builder
	for scanner.Scan() {
		lastFrame.Store(time.Now().UnixNano())
		line := scanner.Text()
		if line == "" {
			if data.Len() > 0 {
				c.consume(ctx, session, []byte(data.String()))
				data.Reset()
			}
		} else if strings.HasPrefix(line, "data:") {
			if data.Len()+len(line) > 64*1024 {
				log.Print("Oversized event stream frame")
				return true, false
			}
			if data.Len() > 0 {
				data.WriteByte('\n')
			}
			data.WriteString(strings.TrimPrefix(strings.TrimPrefix(line, "data:"), " "))
		}
	}
	if err := scanner.Err(); err != nil && ctx.Err() == nil {
		log.Printf("Event stream ended: %v", err)
	}
	return true, false
}
