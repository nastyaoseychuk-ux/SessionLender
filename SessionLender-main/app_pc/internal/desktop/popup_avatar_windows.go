//go:build windows

package desktop

func (n *Notifier) loadAvatar(p *popup, address string) {
	if address == "" {
		return
	}
	avatar, err := fetchAvatar(address, p.ticket)
	if err != nil {
		return
	}
	n.dispatch(func() {
		if n.windows[p.hwnd] != p {
			return
		}
		p.avatar = avatar
		p.render()
	})
}
