package desktop

import (
	"bytes"
	"encoding/xml"
	"fmt"
)

func escaped(value string) string {
	var out bytes.Buffer
	_ = xml.EscapeText(&out, []byte(value))
	return out.String()
}
func toastXML(title, body, path, icon string) string {
	return fmt.Sprintf(`<toast activationType="foreground" launch="%s"><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text><image placement="appLogoOverride" src="%s"/></binding></visual><audio src="ms-winsoundevent:Notification.Default"/></toast>`, escaped(path), escaped(title), escaped(body), escaped(icon))
}
