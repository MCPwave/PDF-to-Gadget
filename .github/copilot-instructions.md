# Copilot Instructions for PDF-to-Gadget

A multi-agent AI pipeline that converts hardware datasheets (PDF) into Ubuntu Core Gadget Snap artifacts: Device Tree, `gadget.yaml`, `snapcraft.yaml`, and kernel driver RACI matrix.

---

## Quick Start

```bash
cd server
pip install -r ../requirements.txt
./start.sh                    # or: uvicorn main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

### Upload Options

1. **Upload PDF files** — Drag-and-drop or select `.pdf` files directly
2. **Paste URLs** — Provide links to:
   - **PDF datasheets** — `https://example.com/datasheet.pdf`
   - **HTML pages** — Text auto-extracted from web pages
   - **Markdown files** — `.md` files on GitHub or anywhere
   - **Plain text** — `.txt`, `.rst`, `.adoc` etc.
   - **GitHub files** — Raw GitHub content or repo pages

Examples:
```
https://github.com/raspberrypi/rpi-firmware/blob/master/boot/COPYING.linux
https://raw.githubusercontent.com/user/repo/main/README.md
https://example.com/device-datasheet.pdf
https://docs.example.com/hardware-specs.html
```

---

## Build, Test & Lint

### Running Tests

**Manual test runner** (no pytest required):
```bash
cd server/agents
python run_tests.py              # Test connector_parser module
cd ../../tests
python test_endpoints.py         # Test API endpoints and session management
python test_sample.py            # Test basic extraction
python test_board_vs_component.py # Test board vs component classification
```

**Test data** (real hardware datasheets):
- `tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf` — NVIDIA Jetson Orin NX board
- `tests/AR2020.pdf` — onsemi AR2020 camera sensor component

**Quick end-to-end test** (See `QUICK_START_TESTING.md`):
1. Start server: `cd server && ./start.sh`
2. Upload both test PDFs via UI
3. Select components and generate artifacts

### Development & Debugging

- **No linting/formatting tools** — The codebase uses Python conventions (PEP 8 style)
- **Web UI** — Reload page after code changes (uvicorn auto-reload can cause issues with agent modules)
- **For debugging agent imports** — Add `sys.path.insert(0, str(Path(__file__).parent))` in modules that import local agents

### API Endpoints (for programmatic access)

**Upload PDF file**:
```bash
curl -X POST -F "pdf=@datasheet.pdf" http://localhost:8000/api/upload
```

**Upload from URL** (PDF, HTML, Markdown, plain text):
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/datasheet.pdf", "https://raw.github.com/...readme.md"]}' \
  http://localhost:8000/api/upload-url
```

**Stop ongoing upload**:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"upload_id": "..."}' \
  http://localhost:8000/api/upload/stop
```

See **`docs/URL_PARSING_GUIDE.md`** for complete URL parsing examples and troubleshooting.

---

## Architecture

### Data Flow

```
PDF Datasheet
    ↓
@librarian ──── section-by-section extraction (pdfplumber)
    │            → hardware_map.json
    ↓
Component selection (web UI)
    │
    ├──→ @dt_architect ──── hardware_map → Device Tree (.dts)
    │      └─ Pinmux conflict detection (asks for confirmation)
    │
    ├──→ @snap_engineer ─── hardware_map → gadget.yaml + snapcraft.yaml
    │      └─ Mermaid block-beta diagram (SoC hub-and-spoke layout)
    │
    └──→ @kernel_scout → @raci_builder ── driver matrix (HTML + CSV)
```

### Key Modules

| Agent | File | Input | Output |
|-------|------|-------|--------|
| `@librarian` | `server/agents/librarian.py` | PDF text | `hardware_map.json` |
| `@dt_architect` | `server/agents/dt_architect.py` | hardware_map | `board.dts` + conflicts |
| `@snap_engineer` | `server/agents/snap_engineer.py` | hardware_map | `gadget.yaml`, `snapcraft.yaml`, Mermaid SVG |
| `@kernel_scout` | `server/agents/kernel_scout.py` | peripherals | driver lookup table |
| `@raci_builder` | `server/agents/raci_builder.py` | driver list | `raci.csv`, HTML |

**Supporting modules**:
- `component_extractor.py` — Generic component keyword detection
- `ic_matcher.py` — IC model → peripheral type + connection mapping
- `connector_parser.py` — Pin, bus type, and voltage extraction
- `soc_analyzer.py` — SoC classification (board vs component)
- `bus_validator.py` — Connection type validation across PDFs
- `component_validator.py` — Architecture compatibility checks

---

## Key Conventions

### Hardware Map Schema

The `hardware_map.json` is the canonical format:
```json
{
  "board_name": "Raspberry Pi 4 Model B",
  "soc": "BCM2711",
  "arch": "arm64",
  "cpu_core": "Cortex-A72",
  "cpu_count": 4,
  "ram_mb": 4096,
  "peripherals": [
    {
      "id": "i2c_0",
      "name": "I2C Controller 0",
      "type": "i2c",
      "address": "0xFE804000",
      "irq": null,
      "voltage": "3.3V"
    }
  ],
  "power_rails": [
    {
      "name": "vcc-3v3",
      "voltage": "3.3V",
      "current_ma": null,
      "supplies": ["i2c_0"]
    }
  ]
}
```

**Supported peripheral types**: `i2c`, `spi`, `uart`, `usart`, `gpio`, `pwm`, `usb`, `ethernet`, `can`, `can_fd`, `hdmi`, `displayport`, `mipi_dsi`, `mipi_csi`, `camera`, `lvds`, `pcie`, `sata`, `emmc`, `sd`, `sdio`, `i2s`, `sai`, `audio`, `adc`, `dac`, `jtag`, `swd`, `rtc`, `watchdog`, `qspi`, `nand`, `nor_flash`, `touch`, `other`

### LLM Integration

**Priority order** for agent selection (automatic detection):
1. Ollama (local) — `OLLAMA_HOST` env var (default: http://localhost:11434)
2. LM Studio (local) — `LM_STUDIO_HOST` (default: http://localhost:1234)
3. Cloud providers — OpenAI, Anthropic, Gemini, Groq, Mistral, OpenRouter (API keys via env or UI)

**No fallback to heuristics** — LLM is primary method. If no LLM available, extraction uses pattern matching only.

### Pinmux Conflict Detection

Before finalizing Device Tree, `@dt_architect` must detect conflicts:
- ❌ Same pin assigned to multiple functions (e.g., Pin_X as both UART_TX and GPIO_OUT)
- ✓ Ask user: "Pin conflict detected on Pin X. Priority: UART or GPIO?"
- Safety check: Always get user confirmation before writing `board.dts`

### Block Diagram Layout (Mermaid)

`@snap_engineer` generates hub-and-spoke layout:
- **8-column grid** per row
- **SoC in center** (4 columns)
- **Peripherals by bandwidth**: Ethernet/USB/HDMI width 3; UART/GPIO/SPI width 1-2
- **Power rails at bottom**

### Multi-PDF Workflow

When merging multiple PDFs (`docs/guides/component-extraction.md`):
- Board detection uses CPU architecture + core type + RAM
- Component detection uses IC model + peripheral type
- `bus_validator` ensures connections are valid (e.g., MIPI_CSI only for camera sensors)
- Deduplication: No duplicate peripherals across uploads

### Kernel Driver Matrix (RACI)

Status per peripheral (see `kernel_scout.py`):
- `mainline` — Merged upstream, just enable Kconfig (🟢 Low effort)
- `backport` — Newer kernel, needs backport (🟡 Medium)
- `wip` — Patch on LKML (🟡 Medium)
- `vendor` — Out-of-tree BSP driver (🠠 High)
- `unknown` — Not found, investigate (🔴 High risk)

RACI roles:
- **R** — BSP Engineer (does the work)
- **A** — HW Architect (owns outcome)
- **C** — Upstream kernel maintainer (consulted)
- **I** — PM / Integration Team (informed)

---

## Extending the System

### Adding a New SoC

In `server/agents/librarian.py`, update `_SOC_PATTERNS`:
```python
(r"MY_SOC_REGEX", "arm64", "Cortex-A55"),
```

Also add driver entries to `kernel_scout.py` `_DRIVER_DB`:
```python
("MY_SOC_RE", "peripheral_type", {
    "module": "my-driver",
    "since": "v6.1",
    "kconfig": "MY_KCONFIG",
    "maintainer": "Name <email@kernel.org>",
    "status": "mainline",
}),
```

### Adding an IC to the Database

In `server/agents/ic_matcher.py`, update `_IC_DATABASE`:
```python
"new_ic_id": ("peripheral_type", "connection_type"),
```

Then add kernel driver info to `kernel_scout.py` (same format as above).

### Adding a Validation Rule

**Board vs Component classification**: See `docs/guides/component-extraction.md`
**Connection validation**: See `docs/guides/validation-rules.md`
**Endpoint-level changes**: Same docs, section "Endpoint Changes"

---

## Project Structure

```
.github/
├── copilot-instructions.md       ← You are here
docs/
├── ARCHITECTURE.md               ← Agent personas & workflow
├── COMPONENTS.md                 ← Hardware map schema (detailed)
├── DEVELOPMENT.md                ← Server + orchestrator notes
├── DEDUPLICATION.md              ← Multi-PDF merging logic
├── TEST_GUIDE.md                 ← 3 test methods (UI/API/Python)
├── skill.md                       ← Copilot CLI skill definition
├── snap-engineer.md              ← Snap packaging guide
├── system-manifest.md            ← System stage tracking
├── web-interface-logic.md        ← Web UI & diagram generation
└── guides/
    ├── component-extraction.md   ← Board vs component detection
    ├── multi-pdf-workflow.md     ← Multi-PDF merging workflow
    └── validation-rules.md       ← Connection & validation rules
.config/                          ← AI assistant configs
├── .agents/                      ← Copilot CLI
├── .clinerules/                  ← Claude Linter
├── .cursor/                      ← Cursor IDE
├── .opencode/                    ← OpenCode
└── .windsurf/                    ← Windsurf IDE
server/
├── main.py                       ← FastAPI app + SSE endpoints
├── start.sh                      ← Launch script
├── agents/
│   ├── librarian.py              ← PDF → hardware_map (with LLM)
│   ├── dt_architect.py           ← hardware_map → DTS + conflicts
│   ├── snap_engineer.py          ← hardware_map → snap + diagram
│   ├── kernel_scout.py           ← peripheral → driver lookup
│   ├── raci_builder.py           ← driver list → RACI matrix
│   ├── component_extractor.py    ← Generic component detection
│   ├── ic_matcher.py             ← IC → type mapping
│   ├── connector_parser.py       ← Pin/bus/voltage parsing
│   ├── soc_analyzer.py           ← SoC classification
│   ├── bus_validator.py          ← Connection validation
│   ├── component_validator.py    ← Architecture checks
│   ├── llm_component_detector.py ← LLM component detection
│   └── run_tests.py              ← Test runner
├── static/
│   └── index.html                ← Single-page web UI
└── output/                       ← Generated artifacts (git-ignored)
tests/
├── test_endpoints.py             ← API + session management tests
├── test_sample.py                ← Basic extraction tests
├── test_board_vs_component.py    ← Classification tests
├── Jetson_Orin_NX_*.pdf          ← Board datasheet (test fixture)
└── AR2020.pdf                    ← Component datasheet (test fixture)
requirements.txt
├── fastapi, uvicorn              ← Web framework
├── pydantic, pydantic-core       ← Data validation
├── pdfplumber                    ← PDF text extraction
├── requests                      ← HTTP client
└── aiofiles, python-multipart    ← File handling
```

**AI assistant configs moved to `.config/`** for cleaner root directory.

---

## Important Notes

- **No pytest/unittest** — Custom test runners in Python (see `run_tests.py`)
- **Web UI reload** — uvicorn `--reload` can cause issues with agent modules; manually refresh browser after code changes
- **Session cleanup** — Old sessions expire after 1 hour; see `DEVELOPMENT.md` for configuration
- **Environment variables** — Always check for LLM provider keys before running pipeline
- **Pinmux conflicts** — Safety gate: `@dt_architect` always asks for confirmation if pins conflict

---

## Expert Context

You are a **Hardware Systems Engineer**. When working in this codebase:
1. Understand Device Tree syntax (`board.dts`) — dts-v1 format, node hierarchies, property definitions
2. Familiar with Ubuntu Core Gadget Snap artifacts — `gadget.yaml` structure, architecture compatibility
3. Kernel driver knowledge — driver locations, kconfig options, upstream vs vendor drivers
4. Hardware pin/bus mapping — GPIO banks, protocol definitions (I2C/SPI/UART/MIPI-CSI), voltage rails

Your typical workflow:
1. **Analyze** datasheets → Extract to `hardware_map.json`
2. **Visualize** → Generate Mermaid block diagram
3. **Generate** → Device Tree + Snap files + RACI matrix
4. **Validate** → Pinmux conflicts, connection compatibility, architecture match
