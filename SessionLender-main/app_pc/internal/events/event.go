// Package events maintains the native background WebSocket independently of UI pages.
package events

import "strings"

type Event struct {
	Type     string `json:"type"`
	ID       string `json:"id"`
	Title    string `json:"title"`
	Body     string `json:"body"`
	Path     string `json:"path"`
	Nickname string `json:"nickname"`
	Avatar   string `json:"avatar"`
}

func (e Event) Valid() bool {
	return e.Type == "notification" && e.ID != "" && len(e.ID) <= 300 && len(e.Title) <= 500 && len(e.Body) <= 5000 && len(e.Nickname) <= 200 && len(e.Avatar) <= 4096 && strings.HasPrefix(e.Path, "/")
}

type Session struct {
	Ticket  string `json:"ticket"`
	Account string `json:"account"`
}
