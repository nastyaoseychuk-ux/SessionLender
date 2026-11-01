//go:build windows

package desktop

import (
	"golang.org/x/sys/windows"
	"image"
	"image/color"
	"image/draw"
	"sort"
	"strings"
	"unsafe"
)

var gdi32 = windows.NewLazySystemDLL("gdi32.dll")

type bitmapHeader struct {
	Size                   uint32
	Width, Height          int32
	Planes, BitCount       uint16
	Compression, SizeImage uint32
	X, Y                   int32
	Used, Important        uint32
}
type compositionData struct {
	Attribute uint32
	Data      unsafe.Pointer
	Size      uintptr
}
type accentPolicy struct{ State, Flags, Color, Animation uint32 }

func applyGlass(hwnd uintptr) {
	// Apply blur to the whole translucent card. The overlay keeps per-pixel alpha.
	proc := user32.NewProc("SetWindowCompositionAttribute")
	if proc.Find() == nil {
		policy := accentPolicy{State: 3, Flags: 2, Color: 0x50181818}
		data := compositionData{Attribute: 19, Data: unsafe.Pointer(&policy), Size: unsafe.Sizeof(policy)}
		proc.Call(hwnd, uintptr(unsafe.Pointer(&data)))
	}
}
func createFont(height, weight int32) uintptr {
	font, _, _ := gdi32.NewProc("CreateFontW").Call(uintptr(-height), 0, 0, 0, uintptr(weight), 0, 0, 0, 1, 0, 0, 4, 0, uintptr(unsafe.Pointer(utf16("Segoe UI"))))
	return font
}

type rasterDC struct {
	dc, bitmap, old uintptr
	pixels          []byte
	width, height   int
}

func newRasterDC(width, height int) *rasterDC {
	dc, _, _ := gdi32.NewProc("CreateCompatibleDC").Call(0)
	header := bitmapHeader{Size: 40, Width: int32(width), Height: -int32(height), Planes: 1, BitCount: 32}
	var pixels unsafe.Pointer
	bitmap, _, _ := gdi32.NewProc("CreateDIBSection").Call(dc, uintptr(unsafe.Pointer(&header)), 0, uintptr(unsafe.Pointer(&pixels)), 0, 0)
	if bitmap == 0 || pixels == nil {
		gdi32.NewProc("DeleteDC").Call(dc)
		return nil
	}
	old, _, _ := gdi32.NewProc("SelectObject").Call(dc, bitmap)
	return &rasterDC{dc: dc, bitmap: bitmap, old: old, pixels: unsafe.Slice((*byte)(pixels), width*height*4), width: width, height: height}
}
func (r *rasterDC) close() {
	gdi32.NewProc("SelectObject").Call(r.dc, r.old)
	gdi32.NewProc("DeleteObject").Call(r.bitmap)
	gdi32.NewProc("DeleteDC").Call(r.dc)
}

func (p *popup) paint() {
	var state paintStruct
	user32.NewProc("BeginPaint").Call(p.hwnd, uintptr(unsafe.Pointer(&state)))
	user32.NewProc("EndPaint").Call(p.hwnd, uintptr(unsafe.Pointer(&state)))
}
func (p *popup) render() {
	width, height := int(p.px(popupWidth)), int(p.px(popupHeight))
	canvas := glassSurface(width, height, int(p.px(24)))
	mask := newRasterDC(width, height)
	if mask == nil {
		return
	}
	defer mask.close()
	p.drawAvatar(canvas)
	p.drawText(canvas, mask, "SessionLender", 20, 12, 340, 31, p.smallFont, color.RGBA{167, 171, 180, 255}, 0x20)
	name := p.event.Nickname
	if name == "" {
		name = nicknameFromTitle(p.event.Title)
	}
	p.drawText(canvas, mask, name, 102, 43, 383, 67, p.nameFont, color.RGBA{244, 245, 247, 255}, 0x20|0x8000)
	// Fixed body rectangle: wrap complete lines and ellipsize overflow; never resize the popup.
	p.drawText(canvas, mask, p.event.Body, 102, 72, 391, 130, p.bodyFont, color.RGBA{215, 218, 225, 255}, 0x10|0x2000|0x8000)
	p.drawOpenIcon(canvas)
	p.drawCloseIcon(canvas)
	// GDI draws only the text mask. The final image retains correct alpha for every
	// pixel, so no black rectangles appear behind text on the glass surface.
	for i := 0; i < len(canvas.Pix); i += 4 {
		mask.pixels[i] = canvas.Pix[i+2]
		mask.pixels[i+1] = canvas.Pix[i+1]
		mask.pixels[i+2] = canvas.Pix[i]
		mask.pixels[i+3] = canvas.Pix[i+3]
	}
	size := point{int32(width), int32(height)}
	origin := point{}
	blend := uint32(0x01FF0000) // AC_SRC_OVER, constant alpha 255, per-pixel source alpha.
	user32.NewProc("UpdateLayeredWindow").Call(p.hwnd, 0, 0, uintptr(unsafe.Pointer(&size)), mask.dc, uintptr(unsafe.Pointer(&origin)), 0, uintptr(unsafe.Pointer(&blend)), 2)
}
func (p *popup) drawText(canvas *image.RGBA, mask *rasterDC, value string, left, top, right, bottom int32, font uintptr, ink color.RGBA, flags uint32) {
	clear(mask.pixels)
	rect := rectangle{p.px(left), p.px(top), p.px(right), p.px(bottom)}
	gdi32.NewProc("SelectObject").Call(mask.dc, font)
	gdi32.NewProc("SetBkMode").Call(mask.dc, 1)
	gdi32.NewProc("SetTextColor").Call(mask.dc, 0xFFFFFF)
	user32.NewProc("DrawTextW").Call(mask.dc, uintptr(unsafe.Pointer(utf16(value))), ^uintptr(0), uintptr(unsafe.Pointer(&rect)), uintptr(flags|0x800))
	gdi32.NewProc("GdiFlush").Call()
	for y := int(rect.Top); y < int(rect.Bottom); y++ {
		for x := int(rect.Left); x < int(rect.Right); x++ {
			i := (y*mask.width + x) * 4
			coverage := max(mask.pixels[i], mask.pixels[i+1], mask.pixels[i+2])
			if coverage == 0 {
				continue
			}
			alpha := uint32(coverage)
			old := canvas.RGBAAt(x, y)
			inv := 255 - alpha
			canvas.SetRGBA(x, y, color.RGBA{uint8((uint32(ink.R)*alpha + uint32(old.R)*inv) / 255), uint8((uint32(ink.G)*alpha + uint32(old.G)*inv) / 255), uint8((uint32(ink.B)*alpha + uint32(old.B)*inv) / 255), uint8(alpha + uint32(old.A)*inv/255)})
		}
	}
}
func (p *popup) drawAvatar(canvas *image.RGBA) {
	if p.avatar == nil {
		return
	}
	size := int(p.px(66))
	left, top := int(p.px(20)), int(p.px(45))
	radius := int(p.px(14))
	pixels := avatarPixels(p.avatar, size)
	avatar := image.NewRGBA(image.Rect(0, 0, size, size))
	for y := 0; y < size; y++ {
		for x := 0; x < size; x++ {
			// A rounded-square avatar follows the album artwork proportions in the player.
			dx := max(radius-x, 0, x-(size-radius-1))
			dy := max(radius-y, 0, y-(size-radius-1))
			if dx*dx+dy*dy > radius*radius {
				continue
			}
			i := (y*size + x) * 4
			avatar.SetRGBA(x, y, color.RGBA{pixels[i+2], pixels[i+1], pixels[i], 255})
		}
	}
	draw.Draw(canvas, image.Rect(left, top, left+size, top+size), avatar, image.Point{}, draw.Over)
}
func nicknameFromTitle(title string) string {
	for _, word := range strings.Fields(title) {
		if strings.HasPrefix(word, "@") {
			return strings.TrimRight(word, ":,.")
		}
	}
	if title != "" {
		return title
	}
	return "SessionLender"
}
func (n *Notifier) orderedPopups() []*popup {
	list := make([]*popup, 0, len(n.windows))
	for _, p := range n.windows {
		list = append(list, p)
	}
	sort.Slice(list, func(i, j int) bool { return list[i].order < list[j].order })
	return list
}

// Square with an arrow pointing outward from its center.
func (p *popup) drawOpenIcon(canvas *image.RGBA) {
	ink := image.NewUniform(color.RGBA{221, 226, 238, 255})
	line := func(x, y, w, h int32) {
		draw.Draw(canvas, image.Rect(int(p.px(x)), int(p.px(y)), int(p.px(x))+max(1, int(p.px(w))), int(p.px(y))+max(1, int(p.px(h)))), ink, image.Point{}, draw.Over)
	}
	line(356, 20, 1, 8)
	line(356, 27, 8, 1)
	line(356, 20, 4, 1)
	line(363, 24, 1, 4)
	line(361, 18, 6, 1)
	line(366, 18, 1, 6)
	for i := int32(0); i < 8; i++ {
		line(359+i, 25-i, 1, 1)
	}
}

// Match the open icon's visual size and stroke instead of relying on a font glyph.
func (p *popup) drawCloseIcon(canvas *image.RGBA) {
	ink := image.NewUniform(color.RGBA{221, 226, 238, 255})
	for i := int32(0); i < 11; i++ {
		for _, x := range []int32{391 + i, 401 - i} {
			left, top := int(p.px(x)), int(p.px(18+i))
			draw.Draw(canvas, image.Rect(left, top, left+max(1, int(p.px(1))), top+max(1, int(p.px(1)))), ink, image.Point{}, draw.Over)
		}
	}
}
