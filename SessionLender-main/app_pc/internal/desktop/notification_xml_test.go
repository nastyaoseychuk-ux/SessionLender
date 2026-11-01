package desktop

import (
	"encoding/xml"
	"strings"
	"testing"
)

func TestToastEscapesServerContent(t *testing.T) {
	value := toastXML(`A & B`, `</text><script>attack</script>`, `/messages/3/?x="a"`, `C:\Users\test\logo.png`)
	decoder := xml.NewDecoder(strings.NewReader(value))
	for {
		_, err := decoder.Token()
		if err != nil {
			if err.Error() != "EOF" {
				t.Fatal(err)
			}
			break
		}
	}
	if strings.Contains(value, "<script>") {
		t.Fatal("unescaped server content")
	}
	if !strings.Contains(value, "ToastGeneric") {
		t.Fatal("missing native toast template")
	}
}
