"""
PDF-to-Gadget Web Server
Orchestrates @librarian → component selection → @dt_architect + @snap_engineer
"""
import asyncio
import io
import json
import os
import re
import sys
import uuid
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
from agents import librarian, dt_architect, snap_engineer, kernel_scout, raci_builder

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="PDF-to-Gadget Pipeline")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path(__file__).parent / "static"


# ── In-memory session store ────────────────────────────────────────────────────

_sessions: dict[str, dict] = {}   # session_id -> { hw_map, pdf_sections }


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


async def _upload_stream(
    data: bytes,
    filename: str,
    model: str,
    api_key: str,
) -> AsyncIterator[str]:
    """Stream section-by-section extraction progress then return the final hw_map."""

    yield _event(f"📄 Parsing PDF: {filename}", "log")
    await asyncio.sleep(0)

    is_pdf = filename.lower().endswith(".pdf")
    if is_pdf:
        try:
            sections = await asyncio.get_event_loop().run_in_executor(
                None, _extract_pdf_sections, data
            )
        except Exception as e:
            yield _event(f"PDF parse error: {e}", "error")
            return
        yield _event(f"📑 Found {len(sections)} sections: "
                     + ", ".join(f'"{s["heading"]}"' for s in sections[:6])
                     + ("…" if len(sections) > 6 else ""), "log")
    else:
        text = data.decode("utf-8", errors="replace")
        sections = [{"heading": "Full Text", "text": text,
                     "page_start": 1, "page_end": 1}]
        yield _event("📄 Plain-text file — treating as single section", "log")

    await asyncio.sleep(0)

    if not any(s["text"].strip() for s in sections):
        yield _event("No extractable text found in file.", "error")
        return

    yield _event(f"🤖 @librarian — extracting hardware map section by section "
                 f"(model: {model or 'auto-detect'})…", "log")
    await asyncio.sleep(0)

    # run_sections is CPU-bound; run in executor so we don't block the event loop
    def _run():
        return librarian.run_sections(sections, model_override=model, api_key=api_key)

    try:
        hw_map, mode, section_log = await asyncio.get_event_loop().run_in_executor(
            None, _run
        )
    except Exception as e:
        yield _event(f"@librarian failed: {e}", "error")
        return

    for entry in section_log:
        yield _event(entry, "log")
        await asyncio.sleep(0)

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"hw_map": hw_map, "sections": sections}

    payload = {
        "type":        "upload_done",
        "session_id":  session_id,
        "mode":        mode,
        "board_name":  hw_map.get("board_name", f"Custom {hw_map.get('arch','arm64')}"),
        "soc":         hw_map.get("soc", "Unknown SoC"),
        "arch":        hw_map.get("arch", "arm64"),
        "cpu_core":    hw_map.get("cpu_core", ""),
        "cpu_count":   hw_map.get("cpu_count", None),
        "cpu_freq_mhz": hw_map.get("cpu_freq_mhz", None),
        "ram_mb":      hw_map.get("ram_mb", None),
        "peripherals": hw_map.get("peripherals", []),
        "power_rails": hw_map.get("power_rails", []),
        "text_preview": sections[0]["text"][:500] if sections else "",
        "sections_processed": len(sections),
    }
    yield f"data: {json.dumps(payload)}\n\n"


@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    model: str = Form(""),
    api_key: str = Form(""),
):
    data = await file.read()
    return StreamingResponse(
        _upload_stream(data, file.filename or "upload", model, api_key),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Generate pipeline (SSE streaming) ─────────────────────────────────────────

class GenerateRequest(BaseModel):
    session_id: str
    selected_ids: list[str]


async def _pipeline_stream(session_id: str, selected_ids: list[str]) -> AsyncIterator[str]:
    def event(msg: str, kind: str = "log") -> str:
        return f"data: {json.dumps({'type': kind, 'message': msg})}\n\n"

    session = _sessions.get(session_id)
    if not session:
        yield event("Session not found. Re-upload your PDF.", "error")
        return

    hw_map = session["hw_map"]

    yield event(f"🔍 @librarian  — hardware map loaded: {len(hw_map['peripherals'])} peripherals", "log")
    await asyncio.sleep(0.3)

    # ── Pinmux conflict check ──────────────────────────────────────────────────
    selected_peripherals = [p for p in hw_map["peripherals"] if p["id"] in selected_ids]
    conflicts = dt_architect.check_pinmux_conflicts(selected_peripherals)

    if conflicts:
        for pin, a, b in conflicts:
            yield event(
                f"⚠️  PIN CONFLICT detected — address {pin} shared by '{a}' and '{b}'. "
                "Resolve before proceeding.",
                "conflict"
            )
        yield event("Pipeline paused: resolve pin conflicts above and resubmit.", "error")
        return

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

    # ── @kernel_scout + @raci_builder ─────────────────────────────────────────
    yield event("🔬 @kernel_scout — looking up upstream Linux kernel drivers…", "log")
    await asyncio.sleep(0.3)
    try:
        drivers    = kernel_scout.lookup_drivers(filtered_map, online=False)
        raci_data  = raci_builder.build(filtered_map, drivers)
        raci_path  = OUTPUT_DIR / f"{session_id}_raci.csv"
        raci_path.write_text(raci_data["raci_csv"])
        mainline_n = sum(1 for d in drivers if d.get("status") == "mainline")
        rec        = raci_data.get("recommended_uc", "")
        yield event(
            f"✅ RACI matrix built — {len(drivers)} drivers "
            f"({mainline_n} mainline, {len(drivers)-mainline_n} need work)"
            + (f" | recommended: {rec}" if rec else ""),
            "log"
        )
        # store in session for /api/raci
        _sessions[session_id]["raci"] = raci_data
    except Exception as e:
        yield event(f"⚠️  @kernel_scout skipped: {e}", "log")
        raci_data = {"raci_html": "", "raci_csv": "", "raci_json": []}

    await asyncio.sleep(0.2)

    yield event("🎉 Pipeline complete!", "done")

    # ── final result payload ───────────────────────────────────────────────────
    payload = {
        "type":            "result",
        "dts":             dts_content,
        "gadget_yaml":     snap_files["gadget_yaml"],
        "snapcraft_yaml":  snap_files["snapcraft_yaml"],
        "mermaid":         snap_files["mermaid"],
        "hardware_map":    filtered_map,
        "raci_html":       raci_data.get("raci_html", ""),
        "raci_json":       raci_data.get("raci_json", []),
        "recommended_uc":  raci_data.get("recommended_uc", ""),
        "files": {
            "dts":       f"/api/download/{session_id}_board.dts",
            "gadget":    f"/api/download/{session_id}_gadget.yaml",
            "snapcraft": f"/api/download/{session_id}_snapcraft.yaml",
            "map":       f"/api/download/{session_id}_hardware_map.json",
            "raci":      f"/api/download/{session_id}_raci.csv",
        },
    }
    yield f"data: {json.dumps(payload)}\n\n"


@app.post("/api/generate")
async def generate_pipeline(req: GenerateRequest):
    return StreamingResponse(
        _pipeline_stream(req.session_id, req.selected_ids),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── RACI ───────────────────────────────────────────────────────────────────────

class RaciRequest(BaseModel):
    session_id: str

@app.post("/api/raci")
async def get_raci(req: RaciRequest):
    """Re-generate (or return cached) RACI matrix for a session."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return cached if available
    if "raci" in session:
        return session["raci"]

    # Generate on demand
    hw_map = session["hw_map"]
    try:
        drivers   = kernel_scout.lookup_drivers(hw_map, online=False)
        raci_data = raci_builder.build(hw_map, drivers)
        session["raci"] = raci_data
        return raci_data
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
