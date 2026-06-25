# Screenshot OCR: Vision Model Fallback

When Hermes cannot analyze images (e.g., vision analysis returns 400 from upstream provider — common with non-vision models like DeepSeek V4 Pro via Manifest routing), fall back to tesseract OCR with ImageMagick preprocessing.

## Quick Start

```bash
# Install dependencies
apt-get install -y tesseract-ocr imagemagick

# Basic OCR (may be poor)
tesseract screenshot.jpg stdout --psm 6
```

## Preprocessing Pipeline

Raw screenshots often OCR poorly. Apply preprocessing to improve results:

### Approach 1: Grayscale + Upscale + Contrast (best general purpose)
```bash
convert screenshot.jpg -colorspace Gray -resize 200% -contrast-stretch 15%x5% /tmp/ocr_input.png
tesseract /tmp/ocr_input.png stdout --psm 6
```

### Approach 2: Threshold (high contrast, binary — best for dark text on light bg)
```bash
convert screenshot.jpg -colorspace Gray -threshold 50% /tmp/ocr_input.png
tesseract /tmp/ocr_input.png stdout --psm 6
```

### Approach 3: Negate + Upscale (inverts colors — try when Approach 1 fails)
```bash
convert screenshot.jpg -negate -resize 200% /tmp/ocr_input.png
tesseract /tmp/ocr_input.png stdout --psm 6
```

## Tesseract PSM Modes

| PSM | Description | Best For |
|-----|-------------|----------|
| 3 | Fully automatic page segmentation | Full documents, mixed content |
| 4 | Single column of variable sizes | Chat screenshots, single-column text |
| 6 | Uniform block of text | Error messages, clean text blocks |

Start with `--psm 6` for error messages; fall back to `--psm 4` if that yields nothing.

## Cropping for Better Results

For mobile screenshots (portrait), crop to the relevant section to reduce noise:

```bash
# Get image dimensions first
identify screenshot.jpg
# Example: 591x1280

# Crop top half (y=0 to y=640)
convert screenshot.jpg -crop 591x640+0+0 -colorspace Gray -resize 200% -contrast-stretch 15%x5% /tmp/crop.png

# Crop middle section (y=500 to y=700)
convert screenshot.jpg -crop 591x200+0+500 -colorspace Gray -resize 200% -contrast-stretch 15%x5% /tmp/crop.png
```

## Browser Screenshot Fallback

When `browser_vision` fails, the screenshot is still saved to disk (see the `screenshot_path` in the error response). OCR it directly:

```bash
tesseract /root/.hermes/cache/screenshots/browser_screenshot_*.png stdout --psm 6
```

## Notes

- ImageMagick `convert` is from the `imagemagick` package — installing it pulls in ~100MB of dependencies
- tesseract has no model download — works immediately after apt install
- For mobile screenshots (portrait orientation), crop first to isolate error messages — full-screen OCR of a chat UI produces noisy output
- If no approach works, tell the user honestly and ask them to describe the error in text
