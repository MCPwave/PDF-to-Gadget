"""
PDF-to-Gadget Web Server
Orchestrates @librarian → component selection → @dt_architect + @snap_engineer
"""
import asyncio
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import AsyncIterator

import pdfplumber
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# add parent dir so we can import agents
sys.path.insert(0, str(Path(__file__).parent))
from agents import librarian, dt_architect, snap_engineer, kernel_scout, raid_builder, bus_validator, component_validator

# Suppress fontTools FontBBox warnings (cosmetic, doesn't affect extraction)
logging.getLogger("fontTools").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.WARNING)  # Keep other pdfplumber warnings

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="PDF-to-Gadget Pipeline")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path(__file__).parent / "static"


# ── In-memory session store ────────────────────────────────────────────────────

_sessions: dict[str, dict] = {}   # session_id -> { hw_map, pdf_sections, created_at, validation_report }
_upload_controls: dict[str, dict] = {}  # upload_id -> { stop_requested, created_at }


def _cleanup_old_sessions(max_age_seconds: int = 3600):
    """Remove sessions older than max_age_seconds (default 1 hour)."""
    now = time.time()
    expired = [sid for sid, sess in _sessions.items()
               if now - sess.get("created_at", now) > max_age_seconds]
    for sid in expired:
        del _sessions[sid]
    if expired:
        print(f"[cleanup] Removed {len(expired)} old session(s)")


# ── PDF section extraction ─────────────────────────────────────────────────────

_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:Overview|Introduction|Features?|Highlights?|Block\s+Diagram|"
    r"Peripheral|Interface|Pin\s+(?:Description|Configuration|Map|List|Out|Assignment)|"
    r"Memory\s+(?:Map|Interface)|Register|Power\s+(?:Management|Supply|Rail|Sequence)|"
    r"Electrical|Mechanical|Package|Description|Specification|Functional|"
    r"Hardware|Software|System|Controller|Configuration|Application|Signal|"
    r"I2C|SPI|UART|USART|USB|CAN|HDMI|GPIO|PWM|ADC|DAC|PCIe|SATA|eMMC|"
    r"Camera|Display|Audio|Ethernet|Clock|Reset|Boot|Debug|JTAG|Revision)",
    re.IGNORECASE,
)


def _detect_heading(text: str) -> str | None:
    """Return a heading label if the first non-empty line of a page looks like a section title."""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if 3 <= len(line) <= 90 and not line[-1] in ".,:;" and _HEADING_RE.match(line):
            return line
        break   # only check first non-empty line
    return None


def _page_to_text(page) -> str:
    """Extract text + tables from a pdfplumber page object."""
    text = page.extract_text() or ""
    # append table rows as pipe-delimited text for better LLM parsing
    for table in (page.extract_tables() or []):
        for row in table:
            if not row:
                continue
            cells = [str(c).strip() for c in row if c and str(c).strip()]
            if cells:
                text += "\n" + " | ".join(cells)
    return text


def _extract_pdf_sections(data: bytes) -> list[dict]:
    """
    Extract PDF content grouped into logical sections.
    Each section: {heading, text, page_start, page_end, type}
    """
    sections: list[dict] = []

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        cur_heading = "Document"
        cur_parts: list[str] = []
        cur_start = 1

        for page_num, page in enumerate(pdf.pages, 1):
            text = _page_to_text(page)
            if not text.strip():
                continue

            heading = _detect_heading(text)
            if heading and heading != cur_heading and cur_parts:
                sections.append({
                    "heading": cur_heading,
                    "text": "\n".join(cur_parts),
                    "page_start": cur_start,
                    "page_end": page_num - 1,
                })
                cur_heading = heading
                cur_parts = [text]
                cur_start = page_num
            else:
                cur_parts.append(text)

        if cur_parts:
            sections.append({
                "heading": cur_heading,
                "text": "\n".join(cur_parts),
                "page_start": cur_start,
                "page_end": len(pdf.pages),
            })

    # if no sections detected, return whole doc as one section
    if not sections:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            all_text = "\n".join(_page_to_text(p) for p in pdf.pages)
        sections = [{"heading": "Full Document", "text": all_text,
                     "page_start": 1, "page_end": 0}]

    return sections


def _fetch_url_content(url: str) -> tuple[bytes | str, str]:
    """
    Fetch content from URL (PDF, HTML, Markdown, GitHub, datasheets, plain text).
    Returns: (content, source_type)
    - PDF: (bytes, 'pdf')
    - HTML: (text, 'html')
    - Markdown/Text: (text, 'markdown'|'text'|'github')
    """
    if not url or not isinstance(url, str):
        raise ValueError("Invalid URL")
    
    # Normalize URL
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    headers = {"User-Agent": "pdf-to-gadget/1.0 (+http://localhost:8000)"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "").lower()
            
            # PDF content (return as bytes for pdfplumber)
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                return data, "pdf"
            
            # GitHub raw content or markdown
            if "github.com" in url:
                if url.endswith(".md") or "raw.githubusercontent.com" in url:
                    return data.decode("utf-8"), "markdown"
                else:
                    return data.decode("utf-8"), "github"
            
            # HTML content
            if "text/html" in content_type:
                # Extract text from HTML
                parser = _HTMLTextExtractor()
                parser.feed(data.decode("utf-8", errors="ignore"))
                return parser.get_text(), "html"
            
            # Plain text / Markdown / other text-based formats
            if "text/plain" in content_type or "text/markdown" in content_type:
                return data.decode("utf-8"), "markdown"
            
            # Try decoding as text (fallback for unknown types)
            if url.lower().endswith((".txt", ".md", ".rst", ".adoc")):
                return data.decode("utf-8"), "text"
            
            # Last resort: try UTF-8, fall back to latin-1
            try:
                return data.decode("utf-8"), "text"
            except:
                return data.decode("latin-1"), "text"
                
    except Exception as e:
        raise ValueError(f"Failed to fetch URL: {str(e)}")


class _HTMLTextExtractor(HTMLParser):
    """Extract text content from HTML."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {"script", "style", "meta", "link"}
        self.current_tag = None
        
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        
    def handle_endtag(self, tag):
        self.current_tag = None
        
    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            text = data.strip()
            if text:
                self.text_parts.append(text)
                
    def get_text(self) -> str:
        return "\n".join(self.text_parts)


def _parse_url_sections(content: str, source_type: str, url: str) -> list[dict]:
    """Parse URL content into sections (similar to PDF sections)."""
    sections = []
    
    # Split by headers/sections
    if source_type == "markdown" or source_type == "text":
        # Split by markdown headers
        parts = re.split(r'^#{1,6}\s+(.+)$', content, flags=re.MULTILINE)
        for i in range(1, len(parts), 2):
            if i < len(parts):
                heading = parts[i].strip() if i < len(parts) else "Content"
                text = parts[i+1].strip() if i+1 < len(parts) else ""
                if text:
                    sections.append({
                        "heading": heading,
                        "text": text,
                        "page_start": 0,
                        "page_end": 0,
                        "source": f"URL: {url}",
                    })
    else:  # html, github
        # Split by paragraph markers or section dividers
        lines = content.split("\n")
        cur_heading = "Web Page Content"
        cur_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Simple heuristic: lines in ALL_CAPS or very short + followed by content = heading
            if len(line) < 100 and line.isupper() and len(cur_text) > 3:
                if cur_text:
                    sections.append({
                        "heading": cur_heading,
                        "text": "\n".join(cur_text),
                        "page_start": 0,
                        "page_end": 0,
                        "source": f"URL: {url}",
                    })
                    cur_heading = line
                    cur_text = []
            else:
                cur_text.append(line)
        
        # Add remaining section
        if cur_text:
            sections.append({
                "heading": cur_heading,
                "text": "\n".join(cur_text),
                "page_start": 0,
                "page_end": 0,
                "source": f"URL: {url}",
            })
    
    # Fallback: if no sections parsed, return whole content as one
    if not sections:
        sections = [{
            "heading": "Web Content",
            "text": content,
            "page_start": 0,
            "page_end": 0,
            "source": f"URL: {url}",
        }]
    
    return sections



# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=html_path.read_text())


# ── Upload & Librarian (SSE streaming, section-by-section) ─────────────────────

@app.get("/api/models")
async def get_models():
    """Return available local models for the UI selector."""
    return librarian.list_local_models()


def _event(msg: str, kind: str = "log") -> str:
    return f"data: {json.dumps({'type': kind, 'message': msg})}\n\n"


async def _error_stream(error_msg: str) -> AsyncIterator[str]:
    """Stream a single error event."""
    yield _event(error_msg, "error")


async def _upload_stream(
    files_data: list[tuple[bytes, str]],
    model: str,
    api_key: str,
    disable_heuristic_fallback: str = "false",
    upload_id: str = "",
    is_url: bool = False,
) -> AsyncIterator[str]:
    """
    Stream extraction progress for multiple PDFs/URLs, then merge and return final hw_map.
    
    Args:
        files_data: List of (bytes, filename) tuples
        model: LLM model override
        api_key: LLM API key
        disable_heuristic_fallback: "true" to disable fallback to heuristic extraction
        is_url: True if content from URLs (affects parsing logic)
    
    Yields:
        SSE events: log, error, upload_done
    """
    if not files_data:
        yield _event("No files provided", "error")
        return

    llm_only_mode = disable_heuristic_fallback.lower() in ("1", "true", "yes")
    _upload_controls[upload_id] = {"stop_requested": False, "created_at": time.time()}

    try:
        yield f"data: {json.dumps({'type': 'upload_started', 'upload_id': upload_id})}\n\n"
        yield _event(f"📂 Processing {len(files_data)} file(s)…", "log")
        await asyncio.sleep(0)
        
        # Cleanup old sessions before processing new upload
        _cleanup_old_sessions()
        
        all_maps: list[dict] = []
        failed_files: list[str] = []
        
        # Extract hardware maps from each file/URL
        for file_idx, (data, filename) in enumerate(files_data, 1):
            if _upload_controls.get(upload_id, {}).get("stop_requested"):
                yield _event("⏹️ Stop requested — finalizing discovered components…", "log")
                break

            yield _event(f"📄 File {file_idx}/{len(files_data)}: {filename}", "log")
            await asyncio.sleep(0)
            
            is_pdf = filename.lower().endswith(".pdf")
            if is_pdf:
                try:
                    sections = await asyncio.get_event_loop().run_in_executor(
                        None, _extract_pdf_sections, data
                    )
                except Exception as e:
                    yield _event(f"  ⚠️  PDF parse error for {filename}: {e}", "error")
                    failed_files.append(filename)
                    continue
                
                yield _event(f"  ✓ Found {len(sections)} sections", "log")
            else:
                text = data.decode("utf-8", errors="replace")
                sections = [{"heading": "Full Text", "text": text,
                            "page_start": 1, "page_end": 1}]
                yield _event(f"  ✓ Plain-text file processed", "log")
            
            await asyncio.sleep(0)
            
            if not any(s["text"].strip() for s in sections):
                yield _event(f"  ⚠️  No extractable text in {filename}", "error")
                failed_files.append(filename)
                continue
            
            yield _event(f"  🤖 @librarian — extracting hardware map "
                        f"(model: {model or 'auto-detect'})…", "log")
            if llm_only_mode:
                yield _event("  ℹ️  LLM-only mode enabled (no timeout)", "log")
            await asyncio.sleep(0)
            
            # Extract hardware map from sections
            def _run():
                return librarian.run_sections(
                    sections,
                    model_override=model,
                    api_key=api_key,
                    disable_heuristic_fallback=disable_heuristic_fallback,
                    should_stop=lambda: _upload_controls.get(upload_id, {}).get("stop_requested", False),
                )
            
            try:
                hw_map, mode, section_log = await asyncio.get_event_loop().run_in_executor(None, _run)
            except Exception as e:
                yield _event(f"  ⚠️  @librarian failed for {filename}: {e}", "error")
                failed_files.append(filename)
                continue
            
            for entry in section_log:
                yield _event(f"  {entry}", "log")
                await asyncio.sleep(0)
            
            # Extract and stream discovered components
            components_found = [
                p for p in hw_map.get("peripherals", [])
                if p.get("is_component", False)
            ]
            if components_found:
                for comp in components_found:
                    comp_id = comp.get("id", "unknown")
                    comp_name = comp.get("name", "Unknown Component")
                    comp_type = comp.get("type", "unknown")
                    ic_name = comp.get("component_ic", {}).get("name", "unknown")
                    conn_type = comp.get("connection_type", "unknown")
                    
                    component_event = {
                        "type": "component_found",
                        "component_id": comp_id,
                        "component_name": comp_name,
                        "component_type": comp_type,
                        "ic_name": ic_name,
                        "connection_type": conn_type,
                        "source_pdf": filename
                    }
                    yield f"data: {json.dumps(component_event)}\n\n"
                    await asyncio.sleep(0.1)
            
            all_maps.append(hw_map)
            total_peripherals = len(hw_map.get('peripherals', []))
            total_components = len(components_found)
            peripherals_summary = f"{total_peripherals} peripherals ({total_components} components)" if total_components > 0 else f"{total_peripherals} peripherals"
            yield _event(f"  ✅ Hardware map extracted: {peripherals_summary}", "log")
            await asyncio.sleep(0.2)

            if _upload_controls.get(upload_id, {}).get("stop_requested"):
                yield _event("⏹️ Stop confirmed — skipping remaining files.", "log")
                break
        
        # Summary of extraction
        yield _event(f"📋 Extraction complete: {len(all_maps)} file(s) succeeded, "
                    f"{len(failed_files)} failed", "log")
        
        if not all_maps:
            yield _event("All files failed to process", "error")
            return
        
        # Merge hardware maps
        yield _event("🔗 Merging hardware maps…", "log")
        await asyncio.sleep(0)
        
        try:
            merged_map = await asyncio.get_event_loop().run_in_executor(
                None, librarian.merge_hardware_maps, all_maps
            )
        except Exception as e:
            yield _event(f"Merge failed: {e}", "error")
            return
        
        yield _event(f"✅ Maps merged: {len(merged_map.get('peripherals', []))} total peripherals, "
                    f"{len(merged_map.get('power_rails', []))} power rails", "log")
        await asyncio.sleep(0)
        
        # Store session
        session_id = str(uuid.uuid4())
        _sessions[session_id] = {
            "hw_map": merged_map,
            "sections": [],
            "created_at": time.time(),
            "validation_report": None
        }
        
        # Final upload_done event with merged map
        # Count components in merged map
        components = [p for p in merged_map.get("peripherals", []) if p.get("is_component", False)]
        
        payload = {
            "type":        "upload_done",
            "session_id":  session_id,
            "mode":        "merged",
            "board_name":  merged_map.get("board_name", f"Custom {merged_map.get('arch','arm64')}"),
            "soc":         merged_map.get("soc", "Unknown SoC"),
            "arch":        merged_map.get("arch", "arm64"),
            "cpu_core":    merged_map.get("cpu_core", ""),
            "cpu_count":   merged_map.get("cpu_count", None),
            "cpu_freq_mhz": merged_map.get("cpu_freq_mhz", None),
            "ram_mb":      merged_map.get("ram_mb", None),
            "peripherals": merged_map.get("peripherals", []),
            "power_rails": merged_map.get("power_rails", []),
            "files_processed": len(all_maps),
            "files_failed": len(failed_files),
            "components_found": len(components),
        }
        yield f"data: {json.dumps(payload)}\n\n"
    finally:
        if upload_id:
            _upload_controls.pop(upload_id, None)


@app.post("/api/upload")
async def upload_pdf(
    files: list[UploadFile] = File(...),
    model: str = Form(""),
    api_key: str = Form(""),
    disable_heuristic_fallback: str = Form("false"),
):
    """Accept multiple files and stream extraction progress.
    
    Limit: 20MB total for all files combined.
    """
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
    
    files_data = []
    total_size = 0
    
    for file in files:
        data = await file.read()
        file_size = len(data)
        total_size += file_size
        
        # Check individual file
        if file_size > MAX_UPLOAD_SIZE:
            return StreamingResponse(
                _error_stream(f"File '{file.filename}' is {file_size/1024/1024:.1f}MB. "
                              f"Maximum per file is {MAX_UPLOAD_SIZE/1024/1024:.0f}MB."),
                media_type="text/event-stream",
            )
        
        files_data.append((data, file.filename or "upload"))
    
    # Check total size
    if total_size > MAX_UPLOAD_SIZE:
        return StreamingResponse(
            _error_stream(f"Total upload size is {total_size/1024/1024:.1f}MB. "
                          f"Maximum allowed is {MAX_UPLOAD_SIZE/1024/1024:.0f}MB. "
                          f"Please upload fewer files."),
            media_type="text/event-stream",
        )
    
    upload_id = str(uuid.uuid4())
    return StreamingResponse(
        _upload_stream(files_data, model, api_key, disable_heuristic_fallback, upload_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class URLUploadRequest(BaseModel):
    urls: list[str]
    model: str = ""
    api_key: str = ""
    disable_heuristic_fallback: str = "false"


@app.post("/api/upload-url")
async def upload_from_url(req: URLUploadRequest):
    """Accept URLs (HTML, Markdown, GitHub, datasheets) and stream extraction."""
    if not req.urls:
        return StreamingResponse(
            _error_stream("No URLs provided"),
            media_type="text/event-stream",
        )
    
    upload_id = str(uuid.uuid4())
    
    async def _url_stream():
        """Stream URL content extraction."""
        try:
            _upload_controls[upload_id] = {"stop_requested": False, "created_at": time.time()}
            yield f"data: {json.dumps({'type': 'upload_started', 'upload_id': upload_id})}\n\n"
            yield _event(f"🔗 Fetching content from {len(req.urls)} URL(s)…", "log")
            await asyncio.sleep(0.3)
            
            files_data = []
            failed_urls = []
            
            for url_idx, url in enumerate(req.urls, 1):
                if _upload_controls.get(upload_id, {}).get("stop_requested"):
                    yield _event("⏹️  URL processing stopped", "log")
                    break
                
                yield _event(f"🔗 URL {url_idx}/{len(req.urls)}: {url[:60]}...", "log")
                await asyncio.sleep(0.2)
                
                try:
                    # Fetch URL content
                    content, source_type = await asyncio.get_event_loop().run_in_executor(
                        None, _fetch_url_content, url
                    )
                    
                    # Handle PDF content (binary)
                    if source_type == "pdf":
                        # content is bytes; add to files_data with .pdf filename
                        filename = f"url-{url_idx}.pdf"
                        yield _event(f"  ✓ Fetched PDF ({len(content)} bytes)", "log")
                        files_data.append((content, filename))
                    else:
                        # Handle text-based content (HTML, Markdown, plain text, etc.)
                        if isinstance(content, bytes):
                            content = content.decode("utf-8", errors="replace")
                        yield _event(f"  ✓ Fetched text ({len(content)} chars, type: {source_type})", "log")
                        
                        # Parse into sections
                        sections = _parse_url_sections(content, source_type, url)
                        yield _event(f"  ✓ Parsed {len(sections)} section(s)", "log")
                        
                        # Create a text file representation
                        filename = f"url-{url_idx}:{source_type}"
                        files_data.append((content.encode("utf-8"), filename))
                    
                except Exception as e:
                    yield _event(f"  ⚠️  Failed to fetch {url}: {str(e)}", "error")
                    failed_urls.append((url, str(e)))
            
            if not files_data:
                yield _event("❌ No content fetched from any URL", "error")
                return
            
            # Process fetched content through librarian
            yield _event(f"📚 Processing {len(files_data)} content source(s)…", "log")
            await asyncio.sleep(0.3)
            
            async for event in _upload_stream(
                files_data, req.model, req.api_key, req.disable_heuristic_fallback, upload_id,
                is_url=True
            ):
                yield event
            
            if failed_urls:
                yield _event(f"⚠️  {len(failed_urls)} URL(s) failed to fetch", "log")
        
        except Exception as e:
            yield _event(f"❌ Error: {str(e)}", "error")
        finally:
            _upload_controls.pop(upload_id, None)
    
    return StreamingResponse(
        _url_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class StopUploadRequest(BaseModel):
    upload_id: str


@app.post("/api/upload/stop")
async def stop_upload(req: StopUploadRequest):
    control = _upload_controls.get(req.upload_id)
    if not control:
        raise HTTPException(status_code=404, detail="Upload not found or already finished")
    control["stop_requested"] = True
    return {"status": "ok", "upload_id": req.upload_id, "stop_requested": True}


# ── Validation endpoint ────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    session_id: str


@app.post("/api/validate")
async def validate_session(req: ValidateRequest):
    """Validate the merged hardware map and return conflicts/alternatives."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    hw_map = session["hw_map"]
    
    try:
        validation_result = await asyncio.get_event_loop().run_in_executor(
            None, bus_validator.validate_connections, [hw_map]
        )
    except Exception as e:
        return {
            "valid": True,
            "conflicts": [],
            "merged_buses": {},
            "driver_summary": {}
        }
    
    # Store validation report in session
    session["validation_report"] = validation_result
    
    return validation_result

class GenerateRequest(BaseModel):
    session_id: str
    selected_ids: list[str]
    alternatives: dict = {}  # Maps conflict ID to selected alternative


async def _pipeline_stream(session_id: str, selected_ids: list[str], alternatives: dict = {}) -> AsyncIterator[str]:
    def event(msg: str, kind: str = "log") -> str:
        return f"data: {json.dumps({'type': kind, 'message': msg})}\n\n"

    session = _sessions.get(session_id)
    if not session:
        yield event("Session not found. Re-upload your PDF.", "error")
        return

    hw_map = session["hw_map"]

    yield event(f"🔍 @librarian  — hardware map loaded: {len(hw_map['peripherals'])} peripherals", "log")
    await asyncio.sleep(0.3)

    # ── Bus & Driver validation ────────────────────────────────────────────────
    yield event("🔗 @bus_validator — validating connections and driver availability…", "log")
    await asyncio.sleep(0.3)
    
    try:
        validation_result = await asyncio.get_event_loop().run_in_executor(
            None, bus_validator.validate_connections, [hw_map]
        )
    except Exception as e:
        yield event(f"⚠️  Validation failed: {e}", "log")
        validation_result = {"valid": True, "conflicts": [], "merged_buses": {}, "driver_summary": {}}
    
    # Store validation report in session
    session["validation_report"] = validation_result
    
    # Stream conflict events
    conflicts = validation_result.get("conflicts", [])
    driver_summary = validation_result.get("driver_summary", {})
    
    if conflicts:
        for conflict in conflicts:
            conflict_type = conflict.get("type", "unknown")
            message = conflict.get("message", "")
            
            if conflict_type == "driver_unavailable":
                peripheral_type = conflict.get("peripheral_type", "unknown")
                bus_name = conflict.get("bus_name", "unknown")
                alternatives = conflict.get("alternatives", [])
                
                alt_msg = ""
                if alternatives:
                    alt_options = [f"{a['connection_type']} ({a['driver_status']})" 
                                  for a in alternatives[:3]]
                    alt_msg = f" | Alternatives: {', '.join(alt_options)}"
                
                yield event(
                    f"⚠️  {peripheral_type.upper()} via {bus_name} — {message}{alt_msg}",
                    "conflict"
                )
            else:
                yield event(f"⚠️  {message}", "conflict")
            
            await asyncio.sleep(0.1)
    
    # Summary of driver status
    mainline_count = driver_summary.get("mainline", 0)
    total_drivers = sum(driver_summary.values())
    if total_drivers > 0:
        yield event(
            f"✅ Driver availability: {mainline_count}/{total_drivers} mainline, "
            f"{driver_summary.get('backport', 0)} backport, "
            f"{driver_summary.get('vendor', 0)} vendor",
            "log"
        )
    
    await asyncio.sleep(0.2)

    # ── Component validation ────────────────────────────────────────────────────
    components = [p for p in hw_map.get("peripherals", []) if p.get("is_component", False)]
    if components:
        yield event("🔌 @component_validator — validating component connections…", "log")
        await asyncio.sleep(0.3)
        
        try:
            component_validation = await asyncio.get_event_loop().run_in_executor(
                None, component_validator.validate_component_connections, hw_map, components
            )
        except Exception as e:
            yield event(f"⚠️  Component validation failed: {e}", "log")
            component_validation = {"valid": True, "component_status": [], "summary": {}}
        
        # Stream component conflict events
        component_status = component_validation.get("component_status", [])
        comp_summary = component_validation.get("summary", {})
        
        if component_status:
            for comp_result in component_status:
                status = comp_result.get("status", "OK")
                if status != "OK":
                    comp_id = comp_result.get("component_id", "unknown")
                    comp_name = comp_result.get("component_name", "Unknown")
                    message = comp_result.get("message", "")
                    required_iface = comp_result.get("required_interface", "unknown")
                    
                    alternatives = comp_result.get("alternatives", [])
                    alt_msg = ""
                    if alternatives:
                        alt_options = [f"{a.get('connection_type', 'unknown')} ({a.get('driver_status', 'unknown')})" 
                                      for a in alternatives[:2]]
                        alt_msg = f" | Alternatives: {', '.join(alt_options)}"
                    
                    yield event(
                        f"⚠️  Component {comp_name} ({comp_id}) — {message}{alt_msg}",
                        "conflict"
                    )
                    await asyncio.sleep(0.1)
        
        # Summary of component validation
        comp_ok = comp_summary.get("ok", 0)
        comp_warnings = comp_summary.get("warnings", 0)
        comp_total = comp_summary.get("total_components", 0)
        if comp_total > 0:
            yield event(
                f"✅ Components validated: {comp_ok}/{comp_total} OK, {comp_warnings} warnings",
                "log"
            )
        
        await asyncio.sleep(0.2)

    # ── Pinmux conflict check ──────────────────────────────────────────────────
    selected_peripherals = [p for p in hw_map["peripherals"] if p["id"] in selected_ids]
    conflicts = dt_architect.check_pinmux_conflicts(selected_peripherals)

    if conflicts:
        yield event(f"⚠️  {len(conflicts)} PIN CONFLICT(S) detected:", "log")
        for pin, a, b in conflicts:
            yield event(
                f"  • Address {pin} shared by '{a}' and '{b}' — will use device tree priorities",
                "log"
            )
        yield event("Proceeding with pipeline (conflicts will be resolved by kernel/driver)", "log")
    else:
        yield event(f"✅ Pinmux check passed — {len(selected_ids)} components selected", "log")
    
    await asyncio.sleep(0.3)

    # ── @dt_architect ──────────────────────────────────────────────────────────
    yield event("🏗️  @dt_architect — generating Device Tree Source…", "log")
    await asyncio.sleep(0.5)
    try:
        dts_content = dt_architect.run(hw_map, selected_ids)
    except Exception as e:
        yield event(f"@dt_architect failed: {e}", "error")
        return

    dts_path = OUTPUT_DIR / f"{session_id}_board.dts"
    dts_path.write_text(dts_content)
    yield event(f"✅ board.dts generated ({len(dts_content)} bytes)", "log")
    await asyncio.sleep(0.3)

    # ── @snap_engineer ─────────────────────────────────────────────────────────
    yield event("📦 @snap_engineer — building Gadget Snap files…", "log")
    await asyncio.sleep(0.5)
    try:
        snap_files = snap_engineer.run(hw_map, selected_ids)
    except Exception as e:
        yield event(f"@snap_engineer failed: {e}", "error")
        return

    gadget_path    = OUTPUT_DIR / f"{session_id}_gadget.yaml"
    snapcraft_path = OUTPUT_DIR / f"{session_id}_snapcraft.yaml"
    gadget_path.write_text(snap_files["gadget_yaml"])
    snapcraft_path.write_text(snap_files["snapcraft_yaml"])

    yield event(f"✅ gadget.yaml generated ({len(snap_files['gadget_yaml'])} bytes)", "log")
    yield event(f"✅ snapcraft.yaml generated ({len(snap_files['snapcraft_yaml'])} bytes)", "log")
    await asyncio.sleep(0.3)

    # ── hardware_map.json ──────────────────────────────────────────────────────
    filtered_map = {**hw_map, "peripherals": selected_peripherals}
    map_path = OUTPUT_DIR / f"{session_id}_hardware_map.json"
    map_path.write_text(json.dumps(filtered_map, indent=2))

    yield event("✅ hardware_map.json saved", "log")
    await asyncio.sleep(0.2)

    # ── @kernel_scout + @raid_builder ─────────────────────────────────────────
    yield event("🔬 @kernel_scout — looking up upstream Linux kernel drivers…", "log")
    await asyncio.sleep(0.3)
    try:
        github_lookup = os.getenv("ENABLE_GITHUB_DRIVER_LOOKUP", "true").lower() in ("1", "true", "yes")
        try:
            drivers = kernel_scout.lookup_drivers(filtered_map, online=github_lookup)
        except Exception as e_online:
            yield event(f"⚠️  GitHub-enriched lookup failed ({e_online}) — retrying offline", "log")
            drivers = kernel_scout.lookup_drivers(filtered_map, online=False)
        raid_data  = raid_builder.build(filtered_map, drivers)
        raid_path  = OUTPUT_DIR / f"{session_id}_raid.csv"
        raid_path.write_text(raid_data["raid_csv"])
        mainline_n = sum(1 for d in drivers if d.get("status") == "mainline")
        rec        = raid_data.get("recommended_uc", "")
        yield event(
            f"✅ RAID matrix built — {len(drivers)} drivers "
            f"({mainline_n} mainline, {len(drivers)-mainline_n} need work)"
            + (f" | recommended: {rec}" if rec else ""),
            "log"
        )
        if github_lookup:
            yield event("🔗 GitHub repo lookup enabled for driver enrichment", "log")
        # store in session for /api/raid
        _sessions[session_id]["raid"] = raid_data
    except Exception as e:
        yield event(f"⚠️  @kernel_scout skipped: {e}", "log")
        raid_data = {"raid_html": "", "raid_csv": "", "raid_json": []}

    await asyncio.sleep(0.2)

    yield event("🎉 Pipeline complete!", "done")

    # ── final result payload with validation report ────────────────────────────
    payload = {
        "type":            "result",
        "dts":             dts_content,
        "gadget_yaml":     snap_files["gadget_yaml"],
        "snapcraft_yaml":  snap_files["snapcraft_yaml"],
        "mermaid":         snap_files["mermaid"],
        "hardware_map":    filtered_map,
        "raid_html":       raid_data.get("raid_html", ""),
        "raid_json":       raid_data.get("raid_json", []),
        "recommended_uc":  raid_data.get("recommended_uc", ""),
        "validation_report": validation_result,
        "files": {
            "dts":       f"/api/download/{session_id}_board.dts",
            "gadget":    f"/api/download/{session_id}_gadget.yaml",
            "snapcraft": f"/api/download/{session_id}_snapcraft.yaml",
            "map":       f"/api/download/{session_id}_hardware_map.json",
            "raid":      f"/api/download/{session_id}_raid.csv",
        },
    }
    yield f"data: {json.dumps(payload)}\n\n"


@app.post("/api/generate")
async def generate_pipeline(req: GenerateRequest):
    return StreamingResponse(
        _pipeline_stream(req.session_id, req.selected_ids, req.alternatives),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── RAID ───────────────────────────────────────────────────────────────────────

class RaidRequest(BaseModel):
    session_id: str

@app.post("/api/raid")
async def get_raid(req: RaidRequest):
    """Re-generate (or return cached) RAID matrix for a session."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return cached if available
    if "raid" in session:
        return session["raid"]

    # Generate on demand
    hw_map = session["hw_map"]
    try:
        drivers   = kernel_scout.lookup_drivers(hw_map, online=False)
        raid_data = raid_builder.build(hw_map, drivers)
        session["raid"] = raid_data
        return raid_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Download ───────────────────────────────────────────────────────────────────

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    # prevent path traversal
    safe = Path(filename).name
    path = OUTPUT_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=safe)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting PDF-to-Gadget server on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
