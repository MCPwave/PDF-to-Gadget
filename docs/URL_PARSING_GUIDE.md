# URL Datasheet Parsing Guide

Parse hardware datasheets from URLs — PDF, HTML, Markdown, plain text, or any text format supported.

## Features

- **PDF datasheets** — Direct PDF download and parsing (e.g., manufacturer datasheets)
- **Markdown files** — GitHub READMEs, `.md` files, technical specs
- **HTML pages** — Auto-extracts text from web pages
- **Plain text files** — `.txt`, `.rst`, `.adoc` formats
- **GitHub content** — Raw GitHub URLs, repo pages, gists

## Web UI Usage

1. **Open** → http://localhost:8000
2. **Click** "📎 Add URL" tab (next to "Upload PDF")
3. **Paste URL(s)** — One per line or comma-separated
4. **Click** "Fetch & Parse"
5. **Select components** from results
6. **Generate** Device Tree + Snap artifacts

## API Usage

### Single URL

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/datasheet.pdf"]}' \
  http://localhost:8000/api/upload-url \
  -N  # -N = no-buffer, to see SSE stream in real-time
```

### Multiple URLs

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": [
    "https://raw.github.com/vendor/repo/main/DATASHEET.md",
    "https://cdn.example.com/spec.pdf",
    "https://docs.example.com/hardware.html"
  ]}' \
  http://localhost:8000/api/upload-url \
  -N
```

### With LLM Model Override

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com/datasheet.pdf"],
    "model": "openai:gpt-4o",
    "api_key": "sk-..."
  }' \
  http://localhost:8000/api/upload-url
```

## Supported Formats

### PDF

**Detection**: Automatic (by MIME type or `.pdf` extension)
```
https://example.com/BCM2711-datasheet.pdf
https://cdn.arm.com/Cortex-A72-TRM.pdf
```

### Markdown

**Detection**: `.md` extension or `text/markdown` MIME type
```
https://raw.githubusercontent.com/vendor/repo/main/README.md
https://raw.github.com/...hardware-specs.md
```

### HTML

**Detection**: `text/html` MIME type
```
https://docs.example.com/board-specs.html
https://wiki.example.com/hardware
```

### Plain Text

**Detection**: `.txt`, `.rst`, `.adoc` extensions or `text/plain` MIME type
```
https://example.com/pinout.txt
https://raw.github.com/vendor/repo/datasheet.txt
```

### GitHub Special Cases

Raw GitHub URLs and markdown files are auto-detected and optimized:
```
https://raw.githubusercontent.com/user/repo/branch/path/to/file.md
https://github.com/user/repo/blob/main/HARDWARE.md
```

## Examples

### Raspberry Pi Compute Module

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": [
    "https://raw.githubusercontent.com/raspberrypi/documentation/develop/documentation/asciidoc/computers/compute-module/overview.adoc"
  ]}' \
  http://localhost:8000/api/upload-url
```

### STM32MP1 Multi-Document

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": [
    "https://www.st.com/resource/en/datasheet/stm32mp157d.pdf",
    "https://raw.githubusercontent.com/STMicroelectronics/STM32CubeMX/master/readme.md",
    "https://wiki.st.com/stm32mp1/wiki/Category:Datasheets"
  ]}' \
  http://localhost:8000/api/upload-url
```

### NVIDIA Jetson from Web

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": [
    "https://developer.nvidia.com/downloads/embedded/L4T/r36.3/jetson-orin-nano-product-brief.pdf"
  ]}' \
  http://localhost:8000/api/upload-url
```

## Processing Flow

```
URL
  ↓
1. Download (with User-Agent, 15s timeout)
  ↓
2. Detect format (MIME type, file extension)
  ↓
  ├─→ PDF → Extract text sections with pdfplumber
  │
  └─→ Text (HTML/MD/TXT) → Parse into sections by headings
  ↓
3. Stream to @librarian (LLM-based extraction)
  ↓
4. Merge with other uploads (if multi-PDF)
  ↓
5. Generate hardware_map.json
```

## Error Handling

**Failed to fetch URL**:
- Check URL is publicly accessible
- Verify CORS headers (if same-origin issue)
- Confirm timeout (15 seconds max per URL)

**Failed to parse content**:
- Check content is valid text/PDF
- Verify file encoding (UTF-8 preferred)
- Try uploading PDF directly instead of HTML wrapper

**No sections extracted**:
- URL might contain binary or compressed data
- Try downloading manually and uploading as PDF
- Check `@librarian` logs for details

## Streaming Response (SSE)

The `/api/upload-url` endpoint returns **Server-Sent Events**:

```json
data: {"type": "upload_started", "upload_id": "abc-123"}

data: {"type": "log", "message": "🔗 Fetching content from 2 URL(s)…"}

data: {"type": "log", "message": "🔗 URL 1/2: https://...pdf"}

data: {"type": "log", "message": "  ✓ Fetched PDF (45678 bytes)"}

data: {"type": "log", "message": "📚 Processing 2 content source(s)…"}

data: {"type": "log", "message": "  🤖 @librarian — extracting hardware map…"}

data: {"type": "result", "data": {"session_id": "...", "hw_map": {...}}}
```

## Limitations & Notes

- **Timeout**: 15 seconds per URL
- **Max content**: No hard limit, but large PDFs (>50MB) may be slow
- **Headers**: Custom User-Agent sent; respects HTTP redirects
- **Encoding**: UTF-8 preferred; falls back to latin-1
- **Authentication**: Public URLs only (no HTTP basic auth or OAuth)
- **SSL/TLS**: Full verification enabled

## Troubleshooting

### "Failed to fetch URL: HTTP Error 403: Forbidden"

Some servers block requests without proper headers. Try:
```bash
# Add GitHub token (if fetching private repos)
curl -H "Authorization: token YOUR_GITHUB_TOKEN" ...
```

### "Failed to fetch URL: 'NoneType' object is not subscriptable"

Usually means invalid URL format. Verify:
- URL starts with `http://` or `https://`
- No spaces or special characters (URL-encode if needed)

### Markdown sections not parsed correctly

Plain text fallback is used if markdown parsing fails. Check:
- Markdown headers start with `#` at line beginning
- No malformed heading syntax

### PDF extraction slow

Large PDFs processed sequentially. For batch:
- Upload multiple PDFs via web UI (parallel processing)
- Or use `/api/upload` endpoint with multiple files

## Performance Tips

1. **Combine URLs** — Send 5 URLs in one request instead of 5 separate requests
2. **Prefer markdown** — Smaller files, faster parsing than HTML
3. **Direct PDF links** — Avoids HTML parsing overhead
4. **Local LLM** — Use Ollama for faster extraction (no network latency)
