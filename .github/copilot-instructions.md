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

## Multi-PDF Hardware Assembly

### Use Case
Combine separate component datasheets (e.g., SoC reference design + camera module + display controller) into unified hardware map. Avoids manual datasheet merging; validates cross-component connectivity; suggests alternatives when drivers unavailable.

**Example:** Raspberry Pi 4 base board (SoC + GPIO) + OmniVision OV5647 camera module (sensor + CSI interface) → single hardware map with merged buses and validated connections.

### Sequential Workflow

1. **Upload all PDFs** → `POST /api/upload-batch` streams per-file extraction progress
2. **Merge hardware maps** → `librarian.merge_hardware_maps()` deduplicates buses, merges power rails, tracks component origin
3. **Validate connections** → `bus_validator.validate_connections()` checks I2C/SPI/UART pin compatibility, validates driver availability, returns warnings + alternatives
4. **Generate artifacts** → `dt_architect` + `snap_engineer` produce merged Device Tree + snap files

---

## Hardware Map Merging (`librarian.merge_hardware_maps`)

### Function Signature
```python
def merge_hardware_maps(maps: List[dict]) -> dict:
    """
    Merges multiple hardware maps into a single map.
    
    Args:
        maps: List of hardware_map.json objects
    
    Returns:
        Merged hardware_map with source_pdf tracking
    """
```

### Deduplication Strategy

**Bus deduplication by (name, type):**
- If two PDFs define `I2C0` (type: `i2c`), keep first occurrence, log in SSE as `merge_info` event
- If bus names differ but types overlap (e.g., `SPI_0` + `SPI` both type `spi`), rename second to `SPI_1` and track in conflict report

**Power rails merging:**
- Merge by voltage + name (e.g., `vcc-3v3` across multiple PDFs)
- Combine `supplies` arrays (deduped by peripheral id)
- If current_ma differs between sources, use maximum

**Peripheral merging:**
- Append all peripherals, preserve original `id` from source PDF
- Add `source_pdf` field to each peripheral: `"source_pdf": "camera-module-v2.pdf"`

### Example: Merging Raspberry Pi 4 + OV5647 Camera

**Input:** Two PDFs
```
rpi4-base.pdf  → {
  "board_name": "Raspberry Pi 4 Model B",
  "soc": "BCM2711",
  "peripherals": [{"id": "i2c_0", "bus": "I2C0", ...}, ...],
  "power_rails": [{"name": "vcc-3v3", "voltage": "3.3V", ...}]
}

ov5647.pdf → {
  "board_name": "OV5647 Camera Module",
  "peripherals": [
    {"id": "csi_rx", "bus": "MIPI_CSI0", "type": "mipi_csi", ...},
    {"id": "i2c_cam", "bus": "I2C0", "address": "0x36", ...}
  ]
}
```

**Output:** Merged map
```json
{
  "board_name": "Raspberry Pi 4 + OV5647",
  "soc": "BCM2711",
  "peripherals": [
    {"id": "i2c_0", "bus": "I2C0", "source_pdf": "rpi4-base.pdf", ...},
    {"id": "csi_rx", "bus": "MIPI_CSI0", "source_pdf": "ov5647.pdf", ...},
    {"id": "i2c_cam", "bus": "I2C0", "address": "0x36", "source_pdf": "ov5647.pdf", ...}
  ],
  "power_rails": [
    {"name": "vcc-3v3", "voltage": "3.3V", "supplies": ["i2c_0", "i2c_cam", ...], ...}
  ]
}
```

---

## Connection Validation (`bus_validator.validate_connections`)

### Function Signature
```python
def validate_connections(hardware_map: dict, driver_db: dict) -> dict:
    """
    Validates I2C/SPI/UART pin compatibility across merged components.
    Checks driver availability via kernel_scout's DRIVER_DB.
    
    Args:
        hardware_map: Merged hardware_map.json
        driver_db: kernel_scout's _DRIVER_DB
    
    Returns:
        {
            "valid": bool,
            "warnings": [...],
            "alternatives": {...}
        }
    """
```

### Validation Checks

1. **I2C/SPI Address Conflicts**
   - Detect collisions on same bus (e.g., two devices at address 0x50 on I2C0)
   - Non-fatal warning: log source_pdf fields, suggest pin reassignment

2. **Driver Availability**
   - Query driver_db for (SoC, peripheral_type) → status in [mainline, backport, wip, vendor, unknown]
   - If status = unknown or vendor, check `alternative_connections` for fallback options

3. **UART Pin Compatibility**
   - Validate TX/RX pin assignment doesn't conflict across components
   - Check voltage levels (3.3V vs 5V) for multi-component systems

4. **Power Rail Consistency**
   - Verify all peripherals on a rail have compatible voltage requirements
   - Non-fatal warning if mismatch detected

### Example: Camera Connection Validation

```json
{
  "valid": true,
  "warnings": [
    {
      "type": "driver_unavailable",
      "severity": "warning",
      "component": "csi_rx",
      "message": "MIPI CSI receiver not in mainline (status: vendor). Alternatives available.",
      "source_pdf": "ov5647.pdf"
    }
  ],
  "alternatives": {
    "csi_rx": [
      {"connection": "mipi_csi", "driver_status": "vendor", "effort": "high"},
      {"connection": "usb", "driver_status": "mainline", "effort": "low"}
    ]
  }
}
```

---

## Alternative Connections

### Concept

Some peripherals (camera, display) support multiple connection types. If primary driver unavailable, suggest alternatives ranked by effort.

### Peripheral → Connection Mappings

```python
ALTERNATIVE_CONNECTIONS = {
    "camera": ["usb", "mipi_csi", "mipi_dsi", "parallel_rgb"],
    "display": ["hdmi", "displayport", "mipi_dsi", "lvds", "parallel_rgb"],
    "storage": ["sd", "emmc", "usb", "pcie", "sata", "nand"],
    "ethernet": ["ethernet", "usb"],
    "wifi": ["pcie", "usb", "sdio"],
}
```

### Effort Levels

- **Low (mainline):** Driver in Linux kernel mainline since 2+ releases. Integration ~1-2 hours.
- **Medium (backport/wip):** Driver in backports or work-in-progress. Integration ~4-8 hours. May need patch application.
- **High (vendor):** Vendor-supplied driver. Integration ~1-2 days. Requires vendor kernel/source.

### Workflow: Camera Driver Unavailable

1. Validator detects `csi_rx` driver not in mainline (BCM2711 + MIPI CSI = vendor status)
2. Query alternatives: `["usb", "mipi_csi", "parallel_rgb"]`
3. Check driver_db for each:
   - `usb` → mainline (effort: low) ✓
   - `mipi_csi` → vendor (effort: high) ✗
   - `parallel_rgb` → backport (effort: medium) ◐
4. Return alternatives ranked by effort to web UI
5. User selects `usb`, validator updates hardware_map: `csi_rx.type = "usb"`

---

## Web UI Workflow (Multi-PDF)

### Step 1: Upload Multiple PDFs
- Drag-drop interface accepts 2+ files
- `POST /api/upload-batch` with file list
- SSE stream per-file: `upload_progress` events with filename + extraction % (0-100)
- After all uploads: `upload_done` event with map list

### Step 2: Review Extraction Progress
- Progress bar per file
- Expandable detail: extracted board_name, SoC, peripheral count
- Cancel per-file during extraction

### Step 3: Merge & Validate
- Auto-trigger `librarian.merge_hardware_maps()` + `bus_validator.validate_connections()` after all uploads
- SSE `merge_info` events log deduplication (e.g., "I2C0 already exists, skipping")
- SSE `conflict` events for validation warnings

### Step 4: Review Conflicts & Alternatives
- Table: conflict type, severity, source_pdf, message
- For each conflict, show `alternatives` dropdown (if available)
- Example row:
  ```
  Type             Severity  Source PDF     Message                                    Alternatives
  driver_unavail   warning   ov5647.pdf     MIPI CSI not mainline                      [USB (low), ParallelRGB (medium), ...]
  ```

### Step 5: Select Alternatives (Optional)
- User clicks dropdown, selects connection type
- UI updates hardware_map in-memory
- Auto-revalidate affected connections
- Display updated conflict list

### Step 6: Generate Artifacts
- Button: "Generate Device Tree + Snap"
- `POST /api/generate` with merged + validated hardware_map
- SSE stream: `log` (dt_architect progress), `error`, `result` (artifacts list)
- Download links for: `board.dts`, `gadget.yaml`, `snapcraft.yaml`, `raci.csv`, conflict report (JSON)

---

## SSE Event Types (Updated)

### New Event: `conflict`

Sent during validation phase in `/api/generate` or `/api/upload-batch`.

```json
{
  "event": "conflict",
  "type": "driver_unavailable|pin_conflict|bus_duplicate|power_mismatch",
  "severity": "warning|error",
  "component": "csi_rx",
  "source_pdf": "ov5647.pdf",
  "message": "MIPI CSI receiver not in mainline for BCM2711. Alternatives available.",
  "alternatives": [
    {"connection": "usb", "driver_status": "mainline", "effort": "low"},
    {"connection": "parallel_rgb", "driver_status": "backport", "effort": "medium"}
  ]
}
```

### Existing Events (Unchanged)

- `log` — progress message (string)
- `error` — fatal failure (string)
- `done` / `result` — final artifacts (JSON payload)

---

## Troubleshooting

### "Camera shows driver_unavailable"
1. Check conflict report: verify driver status from `kernel_scout._DRIVER_DB`
2. Review alternatives: click dropdown in conflict table
3. Select lower-effort option (e.g., USB over MIPI CSI)
4. Re-generate artifacts

### "Power rail mismatch warning"
1. Inspect source_pdf fields in warning details
2. Check voltage: does peripheral match rail voltage?
3. Edit hardware_map JSON directly (advanced): change peripheral's `regulator` or `voltage` field
4. Re-upload to re-validate

### "Bus pin conflict"
1. Identify conflicting components from warning (source_pdf field)
2. Check address collisions in conflict table
3. Manual reassignment required: edit hardware_map, change peripheral address
4. Example: if I2C0 has two devices at 0x50, change one to 0x51 (if sensor supports it)
5. Re-validate

### "Merge skipped my I2C peripheral"
1. Check merge_info SSE events for deduplication log
2. Verify bus names across PDFs: librarian may have inferred different names (I2C0 vs I2C_0)
3. Edit source PDF extraction or manually merge in hardware_map JSON

---

## Communication Style

Respond terse like smart caveman. All technical substance stay. Only fluff die.

- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"
