package config

import "testing"

func TestDestinationStaysOnServer(t *testing.T) {
	for _, path := range []string{"/", "/messages/4/", "/rooms/2/?tab=posts"} {
		got, err := Destination(path)
		if err != nil || got != ServerURL+path {
			t.Fatalf("valid path rejected: %q", path)
		}
	}
	for _, path := range []string{"https://evil.test/", "//evil.test/", "/\\evil.test/", "/%2f%2fevil.test/", "/%5cevil.test/", "/\n/", "javascript:alert(1)"} {
		if _, err := Destination(path); err == nil {
			t.Fatalf("unsafe path accepted: %q", path)
		}
	}
}
