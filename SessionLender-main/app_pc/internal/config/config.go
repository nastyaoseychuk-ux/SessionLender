// Package config contains the server address compiled into the application.
package config

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

const ServerURL = "https://sessionlender.vercel.app"
const AppID = "MysterSay.SessionLender"
const Version = "1.0.0"

func WebSocketURL() string {
	return "wss://" + strings.TrimPrefix(ServerURL, "https://") + "/ws/inbox/"
}

// Destination never permits notifications to navigate to a different origin.
func Destination(path string) (string, error) {
	parsed, err := url.Parse(path)
	if err != nil || parsed.IsAbs() || parsed.Host != "" || !strings.HasPrefix(path, "/") || strings.HasPrefix(path, "//") || strings.ContainsAny(path, "\\\r\n") {
		return "", fmt.Errorf("invalid application path")
	}
	decoded, err := url.PathUnescape(parsed.Path)
	if err != nil || strings.HasPrefix(decoded, "//") || strings.ContainsAny(decoded, "\\\r\n") {
		return "", fmt.Errorf("invalid encoded path")
	}
	return ServerURL + path, nil
}

func DataDir() (string, error) {
	root, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(root, "SessionLender")
	return dir, os.MkdirAll(dir, 0700)
}
