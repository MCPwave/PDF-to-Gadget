# PDF-to-Gadget Pipeline

Convert hardware datasheets (PDF) into Ubuntu Core Gadget Snap artifacts — Device Tree, `gadget.yaml`, `snapcraft.yaml`, and a RACI kernel driver matrix — via a multi-agent AI pipeline.

---

## Overview

```
PDF Datasheet
    │
    ▼
@librarian ──── section-by-section extraction (pdfplumber)
    │            Overview → SoC/board identity
    │            Features → peripheral list
    │            Registers → base addresses
    │            Power → voltage rails
    │            Pinmux → GPIO banks
    ▼
hardware_map.json
    │
    ├──▶ @kernel_scout ──── upstream Linux driver lookup
    │         └─ @raci_builder → RACI matrix (HTML + CSV)
    │
    ├──▶ @dt_architect ──── Linux Device Tree Source (.dts)
    │         └─ pinmux conflict detection
    │
    └──▶ @snap_engineer ─── gadget.yaml + snapcraft.yaml
              └─ Mermaid block-beta diagram (SoC centred)
```

---

## Quick Start

```bash
cd server
pip install fastapi uvicorn pdfplumber pydantic httpx
./start.sh          # or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**

---

## Web UI

1. **Upload** — drag-and-drop datasheet PDF
2. **Watch** — section-by-section extraction streams live in the terminal tab
3. **Select** — tick the components you want included
4. **Generate** — runs DTS + snap + RACI pipeline
5. **Download** — `board.dts`, `gadget.yaml`, `snapcraft.yaml`, `raci.csv`, `hardware_map.json`

---

## Agents

| Agent | File | Role | Output |
|-------|------|------|--------|
| `@librarian` | `server/agents/librarian.py` | PDF → hardware map | `hardware_map.json` |
| `@dt_architect` | `server/agents/dt_architect.py` | hardware map → DTS | `board.dts` |
| `@snap_engineer` | `server/agents/snap_engineer.py` | hardware map → snap files + diagram | `gadget.yaml`, `snapcraft.yaml`, Mermaid SVG |
| `@kernel_scout` | `server/agents/kernel_scout.py` | peripheral → upstream driver lookup | driver list |
| `@raci_builder` | `server/agents/raci_builder.py` | driver list → RACI matrix | `raci.csv`, HTML table |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | SPA web UI |
| `GET`  | `/api/models` | List available LLM models |
| `POST` | `/api/upload` | Upload PDF → SSE stream of section extraction |
| `POST` | `/api/generate` | Run full pipeline → SSE stream |
| `POST` | `/api/raci` | Return RACI matrix for a session |
| `GET`  | `/api/download/{file}` | Download generated artifact |

### SSE event types

**`/api/upload`** streams:
- `log` — section-by-section progress
- `error` — extraction failure
- `upload_done` — final `hardware_map` payload

**`/api/generate`** streams:
- `log` / `conflict` / `error` / `done` — pipeline progress
- `result` — final payload with all artifacts + `raci_html` + `raci_json`

---

## LLM Support

Model format: `provider:model_name` — e.g. `ollama:llama3.2`, `openai:gpt-4o-mini`

| Provider | Detection | Key |
|----------|-----------|-----|
| Ollama | auto (local) | `OLLAMA_HOST` |
| LM Studio | auto (local) | `LM_STUDIO_HOST` |
| OpenAI | env / UI | `OPENAI_API_KEY` |
| Anthropic | env / UI | `ANTHROPIC_API_KEY` |
| Gemini | env / UI | `GOOGLE_API_KEY` |
| Groq | env / UI | `GROQ_API_KEY` |
| Mistral | env / UI | `MISTRAL_API_KEY` |
| OpenRouter | env / UI | `OPENROUTER_API_KEY` |

Without LLM, pipeline falls back to regex heuristics (SoC patterns, bus patterns, board name detection).

---

## hardware_map Schema

```json
{
  "board_name": "Raspberry Pi 4 Model B",
  "soc": "BCM2711",
  "arch": "arm64",
  "cpu_core": "Cortex-A72",
  "cpu_count": 4,
  "cpu_freq_mhz": 1800,
  "ram_mb": 4096,
  "peripherals": [
    {
      "id": "i2c_0",
      "name": "I2C Controller 0",
      "type": "i2c",
      "bus": "I2C0",
      "address": "0xFE804000",
      "irq": null,
      "voltage": "3.3V",
      "regulator": "vcc-3v3"
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

Supported peripheral types: `i2c`, `spi`, `uart`, `usart`, `gpio`, `pwm`, `usb`, `ethernet`, `can`, `can_fd`, `hdmi`, `displayport`, `mipi_dsi`, `mipi_csi`, `camera`, `lvds`, `pcie`, `sata`, `emmc`, `sd`, `sdio`, `i2s`, `sai`, `audio`, `adc`, `dac`, `jtag`, `swd`, `rtc`, `watchdog`, `qspi`, `nand`, `nor_flash`, `touch`, `other`

---

## Block Diagram Layout

`@snap_engineer` generates Mermaid `block-beta` diagrams with a hub-and-spoke layout:

```
┌──────────────── Board (8 cols) ─────────────────┐
│  [ethernet:3]  [usb:3]  [hdmi:3]  [space…]      │  ← big (w≥3)
│  [gpio:1][pwm:1]  [ SoC : 4 cols ]  [i2c:2]    │  ← SoC centred
│  [spi:2]  [uart:2]  [can:2]  [space…]           │  ← medium/small
│  (vcc-3v3)  (vcc-1v8)  …                        │  ← power rails
└─────────────────────────────────────────────────┘
```

Block widths reflect hardware complexity: high-bandwidth interfaces (Ethernet, USB, HDMI, PCIe, MIPI) are width 3; protocol controllers width 2; single-signal pins width 1.

---

## RACI Matrix

Kernel driver status per peripheral:

| Status | Meaning | Effort |
|--------|---------|--------|
| `mainline` | Merged upstream — just enable Kconfig | 🟢 Low |
| `backport` | Newer kernel; needs backport | 🟡 Medium |
| `wip` | Patch on LKML | 🟡 Medium |
| `vendor` | Out-of-tree BSP driver | 🟠 High |
| `unknown` | Not found | 🔴 Investigate |

RACI roles:
- **R** — BSP Engineer (does the work)
- **A** — HW Architect (owns outcome)
- **C** — Upstream kernel maintainer (consulted)
- **I** — PM / Integration Team (informed)

`@kernel_scout` covers 100+ `(SoC, peripheral_type)` combinations for BCM2711, RK3xxx, i.MX 8M/9, AM62x, MT8xxx, STM32MP, Allwinner, Amlogic, Qualcomm, Exynos and more.

---

## Extending

### Add a new SoC

`server/agents/librarian.py` → `_SOC_PATTERNS`:
```python
(r"MY_SOC_REGEX", "arm64", "Cortex-A55"),
```

### Add a driver to the RACI DB

`server/agents/kernel_scout.py` → `_DRIVER_DB`:
```python
("MY_SOC_RE", "peripheral_type", {
    "module":     "my-driver",
    "since":      "v6.1",
    "kconfig":    "MY_KCONFIG",
    "path":       "drivers/subsystem/my-driver.c",
    "maintainer": "Name <email@kernel.org>",
    "status":     "mainline",
}),
```

---

## Project Structure

```
cop1/
├── README.md                          # Main readme
├── .github/
│   └── copilot-instructions.md       # AI assistant instructions
├── .gitignore                         # Ignore unnecessary files
├── docs/                              # All documentation
│   ├── ARCHITECTURE.md               # Agent persona definitions
│   ├── COMPONENTS.md                 # Hardware map & component schema
│   ├── DEVELOPMENT.md                # Server architecture & orchestrator
│   ├── DEDUPLICATION.md              # Multi-PDF merging & validation
│   ├── skill.md                      # Copilot CLI skill definition
│   ├── snap-engineer.md              # Snap packaging guide
│   ├── system-manifest.md            # System stage tracking
│   ├── web-interface-logic.md        # Web UI & diagram generation
│   ├── superpowers.md                # (reserved)
│   └── guides/
│       ├── multi-pdf-workflow.md     # Multi-PDF merging workflow
│       ├── component-extraction.md   # Board vs component detection
│       └── validation-rules.md       # Endpoint changes & validation
├── .config/                          # AI assistant & IDE configs
│   ├── .agents/                      # GitHub Copilot CLI config
│   ├── .clinerules/                  # Claude Linter rules
│   ├── .cursor/                      # Cursor IDE config
│   ├── .opencode/                    # OpenCode config (with node_modules)
│   └── .windsurf/                    # Windsurf IDE config
├── server/
│   ├── main.py                       # FastAPI app, SSE endpoints
│   ├── start.sh                      # Launch script
│   ├── agents/                       # AI agent modules
│   │   ├── librarian.py              # PDF → hardware_map
│   │   ├── dt_architect.py           # hardware_map → DTS
│   │   ├── snap_engineer.py          # hardware_map → snap + diagram
│   │   ├── kernel_scout.py           # peripheral → driver lookup
│   │   └── raci_builder.py           # driver list → RACI matrix
│   ├── static/
│   │   └── index.html                # Single-page web UI
│   └── output/                       # Generated artifacts (git-ignored)
├── tests/                            # Test files (if any)
└── .gitignore                        # Git ignore rules
```

**Config moved to `.config/`** for cleaner root directory. All AI assistant configs (Copilot CLI, Cursor, Windsurf, etc.) are now organized in one place.

---

## Requirements

- Python 3.10+
- `fastapi`, `uvicorn`, `pdfplumber`, `pydantic`, `httpx`
- At least one LLM: Ollama (local) **or** any cloud provider key
- Mermaid 10.3+ (loaded from CDN in browser)
