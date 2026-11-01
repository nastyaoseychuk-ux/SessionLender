package desktop

import (
	"image"
	"image/color"
	"testing"
)

func TestAvatarHosts(t *testing.T) {
	for _, address := range []string{"https://sessionlender.vercel.app/image.png", "https://test.public.blob.vercel-storage.com/avatar.webp"} {
		if !trustedAvatarURL(address) {
			t.Fatal(address)
		}
	}
	for _, address := range []string{"http://sessionlender.vercel.app/a", "https://127.0.0.1/a", "https://sessionlender.vercel.app.evil.test/a", "https://name:password@sessionlender.vercel.app/a", "https://sessionlender.vercel.app:444/a"} {
		if trustedAvatarURL(address) {
			t.Fatal("untrusted avatar accepted", address)
		}
	}
}
func TestAvatarCenterCrop(t *testing.T) {
	src := image.NewRGBA(image.Rect(0, 0, 8, 4))
	for y := 0; y < 4; y++ {
		for x := 0; x < 8; x++ {
			src.Set(x, y, color.RGBA{R: 255, A: 255})
		}
	}
	data := avatarPixels(src, 54)
	if len(data) != 54*54*4 || data[0] != 0 || data[2] != 255 || data[3] != 255 {
		t.Fatal("invalid BGRA avatar")
	}
}
