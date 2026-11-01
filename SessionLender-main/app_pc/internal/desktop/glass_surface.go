package desktop

import (
	"image"
	"image/color"
	"math"
)

// Premultiplied RGBA: transparent antialiased corners, a soft rim and a dark tint.
func glassSurface(width, height, radius int) *image.RGBA {
	out := image.NewRGBA(image.Rect(0, 0, width, height))
	distance := func(x, y float64, inset float64) float64 {
		cx := math.Max(float64(radius), math.Min(float64(width-radius), x))
		cy := math.Max(float64(radius), math.Min(float64(height-radius), y))
		return math.Hypot(x-cx, y-cy) - float64(radius) + inset
	}
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			d := distance(float64(x)+.5, float64(y)+.5, 0)
			coverage := math.Max(0, math.Min(1, .5-d))
			if coverage == 0 {
				continue
			}
			rim := math.Max(0, math.Min(1, 1.25+d))
			highlight := 1 - float64(y)/float64(height)
			alpha := (185 + rim*40) * coverage
			shade := 20 + highlight*7 + rim*65
			a := uint8(alpha)
			out.SetRGBA(x, y, color.RGBA{uint8(shade * alpha / 255), uint8((shade + 1) * alpha / 255), uint8((shade + 4) * alpha / 255), a})
		}
	}
	return out
}
