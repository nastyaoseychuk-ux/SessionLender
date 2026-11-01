package events

import (
	"encoding/json"
	"os"
	"path/filepath"
)

const historyLimit = 500

type History struct {
	path     string
	Accounts map[string][]string `json:"accounts"`
}

func LoadHistory(path string) *History {
	h := &History{path: path, Accounts: map[string][]string{}}
	if data, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(data, h)
	}
	if h.Accounts == nil {
		h.Accounts = map[string][]string{}
	}
	return h
}

func (h *History) Has(account, id string) bool {
	for _, value := range h.Accounts[account] {
		if value == id {
			return true
		}
	}
	return false
}

func (h *History) Remember(account, id string) error {
	list := append(h.Accounts[account], id)
	if len(list) > historyLimit {
		list = list[len(list)-historyLimit:]
	}
	h.Accounts[account] = list
	data, err := json.Marshal(h)
	if err != nil {
		return err
	}
	temp := filepath.Join(filepath.Dir(h.path), "notification-history.tmp")
	if err = os.WriteFile(temp, data, 0600); err != nil {
		return err
	}
	return os.Rename(temp, h.path)
}
