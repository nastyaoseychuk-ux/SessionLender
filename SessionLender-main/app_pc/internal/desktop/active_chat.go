package desktop

import (
	"net/url"
	"regexp"
	"time"
)

var chatPath = regexp.MustCompile(`^/messages/[0-9]+/$`)

type PageState struct {
	Path    string    `json:"path"`
	Visible bool      `json:"visible"`
	Focused bool      `json:"focused"`
	Updated time.Time `json:"-"`
}

func (state PageState) Suppresses(path string, now time.Time) bool {
	current, err := url.Parse(state.Path)
	if err != nil || current.IsAbs() || current.Host != "" {
		return false
	}
	target, err := url.Parse(path)
	if err != nil {
		return false
	}
	return state.Visible && state.Focused && now.Sub(state.Updated) < 45*time.Second && chatPath.MatchString(current.Path) && current.Path == target.Path
}

func isChatPath(path string) bool { return chatPath.MatchString(path) }
