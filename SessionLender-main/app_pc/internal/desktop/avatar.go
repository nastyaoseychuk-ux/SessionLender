package desktop

import (
	"bytes"
	"fmt"
	_ "golang.org/x/image/webp"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sessionlender/desktop/internal/config"
	"strings"
	"time"
)

func trustedAvatarURL(address string) bool {
	u, err := url.Parse(address)
	if err != nil || u.Scheme != "https" || u.User != nil || u.Port() != "" {
		return false
	}
	base, _ := url.Parse(config.ServerURL)
	host := strings.ToLower(u.Hostname())
	return host == base.Hostname() || strings.HasSuffix(host, ".public.blob.vercel-storage.com")
}
func fetchAvatar(address, ticket string) (image.Image, error) {
	private := regexp.MustCompile(`^/desktop/avatar/[0-9]+/$`).MatchString(address)
	if private {
		address = config.ServerURL + address
	}
	if !trustedAvatarURL(address) {
		return nil, fmt.Errorf("untrusted avatar URL")
	}
	client := http.Client{Timeout: 5 * time.Second, CheckRedirect: func(request *http.Request, via []*http.Request) error {
		if len(via) > 2 || !trustedAvatarURL(request.URL.String()) || !strings.HasSuffix(request.URL.Hostname(), ".public.blob.vercel-storage.com") {
			return http.ErrUseLastResponse
		}
		request.Header.Del("Authorization")
		return nil
	}}
	request, err := http.NewRequest(http.MethodGet, address, nil)
	if err != nil {
		return nil, err
	}
	if private {
		request.Header.Set("Authorization", "Bearer "+ticket)
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("avatar HTTP %d", response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 2*1024*1024+1))
	if err != nil || len(data) > 2*1024*1024 {
		return nil, fmt.Errorf("avatar too large")
	}
	dimensions, _, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil || dimensions.Width <= 0 || dimensions.Height <= 0 || dimensions.Width > 4096 || dimensions.Height > 4096 || dimensions.Width*dimensions.Height > 4_000_000 {
		return nil, fmt.Errorf("invalid avatar dimensions")
	}
	result, _, err := image.Decode(bytes.NewReader(data))
	return result, err
}

// Center-crop and composite alpha onto the black notification card.
func avatarPixels(source image.Image, size int) []byte {
	bounds := source.Bounds()
	side := min(bounds.Dx(), bounds.Dy())
	left := bounds.Min.X + (bounds.Dx()-side)/2
	top := bounds.Min.Y + (bounds.Dy()-side)/2
	pixels := make([]byte, size*size*4)
	for y := 0; y < size; y++ {
		for x := 0; x < size; x++ {
			r, g, b, _ := source.At(left+x*side/size, top+y*side/size).RGBA()
			offset := (y*size + x) * 4
			pixels[offset] = byte(b >> 8)
			pixels[offset+1] = byte(g >> 8)
			pixels[offset+2] = byte(r >> 8)
			pixels[offset+3] = 255
		}
	}
	return pixels
}
