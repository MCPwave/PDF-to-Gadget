---
name: pdf-to-gadget
description: >
  Full multi-PDF pipeline for converting hardware datasheets into Ubuntu Core Gadget Snaps.
  Supports board + component assembly (cameras, sensors, displays, etc. auto-extracted from any PDF).
  Validates bus connections, checks driver availability, suggests alternatives.
  Orchestrates: @librarian (multi-PDF hardware+component extraction), @dt_architect (Device Tree),
  @snap_engineer (snap files + diagram), @kernel_scout (driver lookup), @raci_builder (driver matrix).
  Trigger: user mentions datasheet, PDF, SBC, gadget snap, camera, sensor, display, multi-component,
  hardware validation, driver status, device tree, pinmux, Ubuntu Core, Raspberry Pi.
---

# PDF-to-Gadget Pipeline Skill

## What This Skill Does

Converts **one or multiple hardware datasheets** into production-ready Ubuntu Core Gadget Snap artifacts with **automatic component detection and validation**:

```
Multiple PDFs (board + components)
    │
    ├─→ (each) @librarian ──── section-by-section extraction + component detection
    │           ├─ Board: SoC, arch, CPU, peripherals, power rails
    │           └─ Components: cameras, sensors, displays (auto-extracted from any PDF)
    │
    ├─→ merge_hardware_maps() ──── multi-PDF assembly with deduplication
    │           ├─ Dedup by peripheral ID (board)
    │           ├─ Dedup by IC name (components)
    │           ├─ Track source_pdf for each item
    │           └─ Keep different connection types separate (e.g., camera USB vs MIPI_CSI)
    │
    ├─→ bus_validator ──── pin compatibility + driver availability
    │           ├─ I2C/SPI/UART pin matching
    │           ├─ Power rail voltage consistency
    │           └─ Alternative connection suggestions
    │
    ├─→ component_validator ──── check component-board compatibility
    │           ├─ Interface existence (e.g., MIPI_CSI0 available?)
    │           ├─ Voltage match (component 3.3V vs board 1.8V interface)
    │           ├─ Component IC driver status (e.g., OV5647)
    │           └─ Interface driver status (e.g., MIPI_CSI host)
    │
    └─→ hardware_map.json + components list
        ├─→ @dt_architect ──── DTS with components integrated
        ├─→ @snap_engineer ─── gadget.yaml + snapcraft.yaml
        ├─→ @kernel_scout ──── RACI matrix
        └─→ Web UI ──────────── board + component visualization
```

---

## Multi-PDF Support (NEW)

Upload multiple datasheets at once:
- **Board PDF** (e.g., Raspberry Pi 4 datasheet)
- **Component PDFs** (e.g., OV5647 camera, TMP36 sensor, ILI9341 display)

System automatically:
1. Extracts board peripherals from board PDFs
2. Extracts components (cameras, sensors, displays) from ANY PDF
3. Merges all data with NO DUPLICATES
4. Validates component-to-board connections
5. Suggests alternatives for incompatible connections

---

## Component Auto-Detection (NEW)

@librarian now extracts components from any PDF using **three detection methods**:

### 1. **IC Matching** (31 known ICs)
Recognizes: OV5647, IMX219, ILI9341, TMP36, BMP280, MPU6050, ST7735, etc.
- Returns: IC name, component type, default connection type, confidence

### 2. **Keyword Detection** (20 component types + 8 section markers)
Scans for: `camera`, `sensor`, `display`, `touchscreen`, `audio`, etc.
- Extracts surrounding context from datasheet text

### 3. **Connector Parser** (6 bus types)
Finds Connector/Interface/Pinout sections:
- Detects: MIPI_CSI, I2C, SPI, USB, UART, HDMI
- Extracts pin names and voltages

**Result**: High-confidence component extraction without user annotation.

---

## Deduplication Guarantee (NEW)

System prevents component duplicates via:

1. **Per-PDF dedup** — Same IC mentioned 3 times in single PDF? → 1 component
2. **Multi-PDF dedup** — OV5647 in both RPi datasheet AND camera module datasheet? → 1 component (first occurrence)
3. **Connection-aware** — OV5647 on MIPI_CSI AND USB? → 2 components (different interfaces)
4. **IC name matching** — Dedup by exact IC name (IMX219 vs IMX477 stay separate)

**Test coverage**: 14 test scenarios + 6 real-world multi-PDF merges, 100% PASS rate.

---

## Server

**Start:** `cd /home/capo02/work/cop1/server && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

**URL:** `http://localhost:8000`

---

## Agent Files

| Agent | File | Role |
|-------|------|------|
| @librarian | `server/agents/librarian.py` | Multi-PDF extraction: board peripherals + auto-detected components |
| @dt_architect | `server/agents/dt_architect.py` | hardware_map → DTS with components |
| @snap_engineer | `server/agents/snap_engineer.py` | hardware_map → gadget.yaml + snapcraft.yaml |
| @kernel_scout | `server/agents/kernel_scout.py` | peripheral → driver status + RACI (board + component ICs) |
| @raci_builder | `server/agents/raci_builder.py` | driver list → RACI HTML/CSV |

**Component Extraction Modules:**
| Module | File | Role |
|--------|------|------|
| Component Extractor | `server/agents/component_extractor.py` | Keyword + section detection |
| IC Matcher | `server/agents/ic_matcher.py` | 31 known component ICs |
| Connector Parser | `server/agents/connector_parser.py` | Bus type + pin extraction |
| Bus Validator | `server/agents/bus_validator.py` | Pin/voltage/driver compatibility |
| Component Validator | `server/agents/component_validator.py` | Component-to-board validation |
| Alternative Connections | `server/agents/alternative_connections.py` | Connection type mappings |

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/` | SPA UI |
| `GET`  | `/api/models` | List available LLM models |
| `POST` | `/api/upload` | Upload **1+ PDFs** → SSE stream of per-file extraction + component discovery |
| `POST` | `/api/validate` | Validate merged hardware_map (component connections, driver status) |
| `POST` | `/api/generate` | Run DTS + snap pipeline with component validation → SSE stream |
| `POST` | `/api/raci` | Generate RACI matrix (board peripherals + component ICs) |
| `GET`  | `/api/download/{file}` | Download generated artifacts |

**SSE Event Types:**
- `log` — progress messages (extraction, merging, validation)
- `component_found` — component discovered (id, name, type, ic_name, connection_type, source_pdf)
- `conflict` — validation warning (pin mismatch, driver unavailable, voltage conflict)
- `error` — fatal error
- `result` — final artifacts + validation report

---

## LLM Model Selection

Format: `provider:model` — e.g. `ollama:llama3.2`, `openai:gpt-4o-mini`

| Provider | Auto-detect | Key env var |
|----------|-------------|-------------|
| Ollama   | ✅ (local)  | `OLLAMA_HOST` |
| LM Studio| ✅ (local)  | `LM_STUDIO_HOST` |
| OpenAI   | env or UI   | `OPENAI_API_KEY` |
| Anthropic| env or UI   | `ANTHROPIC_API_KEY` |
| Gemini   | env or UI   | `GOOGLE_API_KEY` |
| Groq     | env or UI   | `GROQ_API_KEY` |
| Mistral  | env or UI   | `MISTRAL_API_KEY` |
| OpenRouter| env or UI  | `OPENROUTER_API_KEY` |

---

## Section-by-Section PDF Extraction

`main.py::_extract_pdf_sections()` splits the PDF page-by-page using heading detection:

```python
# Heading patterns detected (triggers new section):
Overview | Introduction | Features | Block Diagram |
Peripheral | Interface | Pin Description | Memory Map |
Register | Power | Electrical | I2C | SPI | UART | USB | CAN |
HDMI | GPIO | PWM | ADC | DAC | PCIe | SATA | eMMC | Camera | Display
```

Each section is classified → focused LLM prompt sent:

| Section type | Prompt focus | Fields extracted |
|---|---|---|
| `overview` | Board + SoC identity | board, soc, arch, cpu_core, cpu_count, cpu_freq_mhz, ram_mb, peripherals |
| `peripheral` | Interface list | peripherals[] with bus, address, type |
| `register` | Base addresses | peripheral addresses only |
| `power` | Power rails | power_rails[] with voltage, current_ma |
| `pinmux` | GPIO banks | gpio peripheral groups |
| `general` | Peripheral fallback | peripherals |

Results merged via `_merge_hw_maps()` — deduplicates by peripheral ID, enriches addresses.

---

## hardware_map Schema

**Board Peripherals:**
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
      "is_component": false,
      "bus": "I2C0",
      "address": "0xFE804000",
      "voltage": "3.3V",
      "regulator": "vcc-3v3",
      "source_pdf": "rpi4_datasheet.pdf"
    }
  ],
  "power_rails": [...]
}
```

**Components (NEW):**
```json
{
  "id": "camera_ov5647_0",
  "name": "OV5647 Camera Module",
  "type": "camera",
  "is_component": true,
  "component_ic": {
    "name": "OV5647",
    "vendor": "OmniVision",
    "type": "camera_sensor"
  },
  "connection_type": "mipi_csi",
  "connector": {
    "pins": ["CSI_D0", "CSI_D1", "CSI_D2", "CSI_D3", "CSI_CLK", "CSI_HS", "GND", "VDDIO"],
    "voltage": "1.8V",
    "required_board_interface": "MIPI_CSI0"
  },
  "source_pdf": "camera_module.pdf",
  "confidence": 0.9
}
```

Peripheral `type` values:
`i2c | spi | uart | usart | gpio | pwm | usb | ethernet | can | can_fd | hdmi | displayport | mipi_dsi | mipi_csi | camera | lvds | pcie | sata | emmc | sd | sdio | i2s | sai | audio | adc | dac | jtag | swd | rtc | watchdog | qspi | nand | nor_flash | hyperflash | touch | other`

Component IC types (31 supported):
- **Cameras**: OV5647, IMX219, IMX477, AR0521
- **Displays**: ILI9341, ST7789, ST7735, UC8159
- **Sensors**: TMP36, BMP280, MPU6050, LSM6DSM, BH1750, APDS9960
- **Touchscreens**: FT5406, EDT-FT5x06, Goodix
- **ADCs**: ADS1015, ADS1115, MCP3008, MCP3208
- **GPIO expanders**: PCF8574, MCP23017, MCP23008
- **Power**: AXP209, TPS65217
- **RTC**: DS1307, PCF8563
- **LEDs**: APA102, WS2812

---

## Component Validation (NEW)

When components are detected, the system validates:

1. **Interface Existence** — Does the board have the required interface?
   - Component: OV5647 on MIPI_CSI0
   - Board: has MIPI_CSI0? ✅ OK / ❌ NO_INTERFACE

2. **Voltage Compatibility** — Do voltages match?
   - Component: 1.8V, Board interface: 1.8V ✅ OK / 3.3V ❌ MISMATCH

3. **Driver Availability** — Do drivers exist in Linux kernel?
   - Component IC driver (e.g., ov5647) status: mainline/backport/vendor/unknown
   - Interface driver (e.g., bcm2835-unicam) status: mainline/backport/vendor/unknown

4. **Alternative Suggestions** — If validation fails:
   - "OV5647 camera not available on MIPI_CSI? Try USB: USB camera drivers are mainline"
   - "I2C0 occupied? Try SPI: TMP36 can work on both I2C and SPI"

---

## Common Workflows

### Single-PDF Board Only
1. Upload `rpi4_datasheet.pdf`
2. System extracts: SoC (BCM2711), peripherals (I2C0, SPI0, GPIO, etc.)
3. Generate DTS + snap

### Multi-PDF: Board + Components
1. Upload `rpi4_datasheet.pdf` + `ov5647_camera.pdf` + `tmp36_sensor.pdf`
2. System extracts:
   - Board: Raspberry Pi 4 (BCM2711, I2C0, SPI0, MIPI_CSI0, etc.)
   - Components: OV5647 camera (MIPI_CSI), TMP36 sensor (I2C0)
3. Validates: Camera needs MIPI_CSI0 ✅, Sensor needs I2C0 ✅
4. Generates unified DTS + snap with all components integrated

### Component with Multiple Connection Options
1. Upload `ov5647_datasheet.pdf` (mentions both MIPI_CSI and USB)
2. System detects: OV5647 can work on MIPI_CSI or USB
3. UI shows both options + driver status for each
4. User selects preferred connection type
5. DTS generated for chosen interface

### Conflict Resolution
1. Upload board + two cameras both needing MIPI_CSI0
2. System warns: "Two cameras on same MIPI_CSI0 interface"
3. Suggests alternative: "Camera 2 can use USB (driver: mainline, effort: low)"
4. User selects USB alternative via UI
5. DTS generated with both cameras: Camera1 on MIPI_CSI0, Camera2 on USB

---

## Driver Status Reference

| Status | Meaning | Linux Version | Integration Effort |
|--------|---------|---------------|--------------------|
| `mainline` | In upstream Linux kernel | v5.x+ | Low (just enable Kconfig) |
| `backport` | Available in newer kernel, needs backport | v6.x→v5.x | Medium (backport module) |
| `wip` | Patch series on LKML | development | Medium (testing + review) |
| `vendor` | Out-of-tree BSP driver only | BSP-specific | High (kernel integration needed) |
| `unknown` | Not found in database | TBD | Investigate |

@kernel_scout DB covers 100+ (SoC, peripheral_type) combinations across 15+ SoC families.

Generated by `@kernel_scout` + `raci_builder`:

| Column | Meaning in this context |
|--------|------------------------|
| **R** — Responsible | BSP Engineer who enables/ports the driver |
| **A** — Accountable | Hardware Architect who owns integration |
| **C** — Consulted | Upstream kernel maintainer for this subsystem |
| **I** — Informed | PM / Integration Team |

Driver status → effort level:

| Status | Meaning | Effort |
|--------|---------|--------|
| `mainline` | Merged in upstream Linux — just `Kconfig` | 🟢 Low |
| `backport` | In newer kernel; older kernels need backport | 🟡 Medium |
| `vendor` | Out-of-tree BSP driver only | 🟠 High |
| `wip` | Patch series posted to LKML | 🟡 Medium |
| `unknown` | Not found — needs investigation | 🔴 Investigate |

`@kernel_scout` covers 100+ (SoC, peripheral_type) combinations in its built-in DB:
BCM2711, RK3588, i.MX 8M/9, AM62x, MT8xxx, STM32MP, Allwinner, Amlogic, Qualcomm, Exynos…

---

## Mermaid Diagram

Generated by `@snap_engineer` using `block-beta` syntax (Mermaid ≥10.3).

Block widths reflect hardware complexity:

| Type | Width (of 6 cols) |
|------|------------------|
| ethernet, usb, hdmi, camera | 3 |
| spi, can, i2c, uart, pcie, sata | 2 |
| gpio, pwm, adc, rtc, other | 1 |

Layout: Board block (navy) → SoC block (orange) → peripheral blocks (color by type) → power rails (grey).

---

## Heuristic Fallback

When no LLM is available, `_heuristic_extract()` uses regex patterns:

- **SoC detection**: 25+ families (BCM, RK3xxx, i.MX, AM6x, MT, STM32MP, Exynos, Tegra, RZ…)
- **Bus detection**: 18 peripheral types via regex on text
- **Board detection**: 14 named board patterns (RPi, Jetson, BeagleBone, Rock Pi, Orange Pi, NanoPi, Odroid…)
- **Power rails**: `vcc-*`, `vdd-*` pattern matching

---

## Common Tasks

### Start fresh from a new datasheet
1. Open `http://localhost:8000`
2. Drag-and-drop PDF
3. Watch section-by-section extraction in terminal tab
4. Select components → Generate
5. Download DTS, gadget.yaml, snapcraft.yaml, RACI CSV

### Add a new SoC to the knowledge base
Edit `server/agents/librarian.py` → `_SOC_PATTERNS` list:
```python
(r"MY_SOC_REGEX", "arm64", "Cortex-A55"),
```

### Add a new driver to the RACI DB
Edit `server/agents/kernel_scout.py` → `_DRIVER_DB` list:
```python
("MY_SOC_RE", "peripheral_type", {
    "module": "my-driver",
    "since": "v6.1",
    "kconfig": "MY_KCONFIG",
    "path": "drivers/subsystem/my-driver.c",
    "maintainer": "Name <email@domain.com>",
    "status": "mainline",
}),
```

### Use a cloud LLM
In the UI header, select e.g. `OpenAI → gpt-4o-mini`, paste your `sk-...` key in the key field that appears.

### Debug section detection
Check the terminal tab after upload — each section is logged:
```
📑 Found 8 sections: "Overview", "Features", "GPIO Interface", ...
📄 [p1-2] "Overview" → overview
     ↳ LLM ✓ 3 peripherals, 0 rails
📄 [p5-7] "GPIO Interface" → peripheral
     ↳ LLM ✓ 12 peripherals, 2 rails
```
