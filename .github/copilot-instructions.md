# Copilot Instructions for PDF-to-Gadget Pipeline

## Quick Start

```bash
cd server
pip install fastapi uvicorn pdfplumber pydantic httpx
./start.sh          # uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Open http://localhost:8000
```

## Architecture Overview

**Multi-agent AI pipeline** converts hardware datasheets (PDF) → Linux Device Tree + Gadget Snap artifacts.

**Data Flow:**
```
PDF Datasheet
    ↓
@librarian ─→ hardware_map.json (SoC, peripherals, registers, power rails, pinmux)
    ├─→ @dt_architect ─→ board.dts (Device Tree, pin conflict detection)
    ├─→ @snap_engineer ─→ gadget.yaml + snapcraft.yaml + Mermaid diagram
    └─→ @kernel_scout + @raci_builder ─→ raci.csv (driver status matrix)
```

**Key Files:**
- `server/main.py` — FastAPI server, SSE endpoints, session management
- `server/agents/librarian.py` — PDF → hardware_map (pdfplumber + LLM)
- `server/agents/dt_architect.py` — hardware_map → Device Tree Source (DTS)
- `server/agents/snap_engineer.py` — hardware_map → snap files + Mermaid diagram
- `server/agents/kernel_scout.py` — peripheral → upstream driver lookup (100+ SoC combos)
- `server/agents/raci_builder.py` — driver list → RACI HTML/CSV matrix
- `server/static/index.html` — SPA web UI

## Build & Test

- **No dedicated test suite** — validation via web UI upload/generation. Test with real datasheets.
- **No linting/formatting tools** — Python formatting is manual.
- **Dependencies:** All in `server/start.sh` (`pip install` command).

## Key Conventions

### Hardware Map Schema

Agents use `hardware_map.json` as the contract:

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
      "type": "i2c",           // Must be in: i2c, spi, uart, usart, gpio, pwm, usb, ethernet, can, can_fd, hdmi, displayport, mipi_dsi, mipi_csi, camera, lvds, pcie, sata, emmc, sd, sdio, i2s, sai, audio, adc, dac, jtag, swd, rtc, watchdog, qspi, nand, nor_flash, touch, other
      "bus": "I2C0",
      "address": "0xFE804000",  // Hex, from datasheet register map
      "irq": null,
      "voltage": "3.3V",
      "regulator": "vcc-3v3"     // Must match a power_rails.name
    }
  ],
  "power_rails": [
    {
      "name": "vcc-3v3",
      "voltage": "3.3V",
      "current_ma": null,
      "supplies": ["i2c_0"]      // Array of peripheral ids
    }
  ]
}
```

### SoC & Arch Detection

`librarian.py` → `_SOC_PATTERNS` dict: Each entry is `(regex, arch, cpu_core)`.  
To add a new SoC:
```python
(r"MY_SOC_NAME|VARIANT_A|VARIANT_B", "arm64", "Cortex-A72"),
```

### Driver Database (RACI)

`kernel_scout.py` → `_DRIVER_DB` list. Status values: `mainline`, `backport`, `wip`, `vendor`, `unknown`.  
To add driver intel:
```python
("MY_SOC_RE", "peripheral_type", {
    "module":     "my-driver",
    "since":      "v6.1",
    "kconfig":    "CONFIG_MY_DRIVER",
    "path":       "drivers/subsystem/my-driver.c",
    "maintainer": "Name <email@kernel.org>",
    "status":     "mainline",
}),
```

### DTS Generation

`dt_architect.py` generates valid Device Tree Source (.dts) for bootloader.  
**Constraints:**
- Every peripheral node must have `reg = <address>` and `status = "okay"` or `status = "disabled"`
- Pin conflicts trigger warnings but **do not halt**; conflicts are logged in the SSE stream as `conflict` events
- Unused peripherals default to `status = "disabled"` to minimize boot time

### Snap Packaging

`snap_engineer.py` generates `gadget.yaml` + `snapcraft.yaml`.  
**Arch detection:** Verify CPU arch (e.g., Cortex-A72 → arm64) before selecting snap base (`core22` vs `core24`).  
**Block diagram:** Mermaid `block-beta` layout: SoC centred, high-bandwidth interfaces (USB, Ethernet, HDMI) width 3, controllers width 2, single-pin width 1.

### Web API & SSE Streaming

**Endpoints:**
- `POST /api/upload` — File upload → SSE stream with `log`, `error`, `upload_done` events
- `POST /api/generate` — Full pipeline → SSE stream with `log`, `conflict`, `error`, `result` events
- `GET /api/download/{file}` — Download artifact (board.dts, gadget.yaml, etc.)

**Event types in stream:**
- `log` — progress message
- `conflict` — pin/resource conflict (non-fatal)
- `error` — fatal failure
- `done` / `result` — final artifacts payload

**LLM fallback:** If no LLM available, pipeline falls back to regex heuristics for SoC/board/peripheral detection.

### Model Format

Use `provider:model_name` format (e.g., `ollama:llama3.2`, `openai:gpt-4o-mini`).  
Supported providers auto-detect via env vars: `OLLAMA_HOST`, `LM_STUDIO_HOST`, or explicit keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`.

## Communication Style

Respond terse like smart caveman. All technical substance stay. Only fluff die.

- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"
