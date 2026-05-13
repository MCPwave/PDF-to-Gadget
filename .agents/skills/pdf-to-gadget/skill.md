---
name: pdf-to-gadget
description: >
  Full pipeline for converting hardware datasheets (PDF) into Ubuntu Core Gadget Snaps.
  Orchestrates three AI agents: @librarian (hardware extraction, section-by-section),
  @dt_architect (Linux Device Tree), @snap_engineer (gadget.yaml + snapcraft.yaml + Mermaid diagram).
  Also generates a RACI matrix of upstream Linux kernel driver status via @kernel_scout.
  Trigger: user mentions datasheet, SBC, SOM, gadget snap, device tree, DTS, pinmux,
  Ubuntu Core, Raspberry Pi config, hardware map, RACI matrix, kernel drivers.
---

# PDF-to-Gadget Pipeline Skill

## What This Skill Does

Converts hardware datasheets into production-ready Ubuntu Core Gadget Snap artifacts:

```
PDF Datasheet
    │
    ▼
@librarian ──── section-by-section extraction
    │            ├─ Overview  → board name, SoC, arch, CPU
    │            ├─ Features  → peripheral list
    │            ├─ Peripheral chapters → interfaces + addresses
    │            ├─ Register maps → base addresses
    │            └─ Power sections → voltage rails
    │
    ▼
hardware_map.json
    │
    ├──▶ @kernel_scout ──── upstream driver lookup per peripheral
    │         └─ RACI matrix (driver status, maintainer, effort, Kconfig)
    │
    ├──▶ @dt_architect ──── Linux Device Tree Source (.dts)
    │         └─ pinmux conflict detection
    │
    └──▶ @snap_engineer ─── gadget.yaml + snapcraft.yaml
              └─ Mermaid block-beta diagram (sized by function)
```

---

## Server

**Start:** `cd /home/capo02/work/cop1/server && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

**URL:** `http://localhost:8000`

---

## Agent Files

| Agent | File | Role |
|-------|------|------|
| @librarian | `server/agents/librarian.py` | PDF → hardware_map JSON |
| @dt_architect | `server/agents/dt_architect.py` | hardware_map → DTS |
| @snap_engineer | `server/agents/snap_engineer.py` | hardware_map → gadget.yaml + snapcraft.yaml |
| @kernel_scout | `server/agents/kernel_scout.py` | peripheral → upstream driver + RACI |

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/` | SPA UI |
| `GET`  | `/api/models` | List available LLM models (Ollama, LM Studio, cloud) |
| `POST` | `/api/upload` | Upload PDF → SSE stream of section-by-section extraction |
| `POST` | `/api/generate` | Run DTS + snap pipeline → SSE stream |
| `POST` | `/api/raci` | Generate RACI matrix for detected components |
| `GET`  | `/api/download/{file}` | Download generated artifacts |

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

```json
{
  "board": "Raspberry Pi 4 Model B",
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
      "description": "I2C bus controller 0",
      "voltage": "3.3V",
      "regulator": "vcc-3v3"
    }
  ],
  "power_rails": [
    {
      "name": "vcc-3v3",
      "voltage": "3.3V",
      "current_ma": null,
      "supplies": ["i2c_0", "spi_0"]
    }
  ]
}
```

Peripheral `type` values:
`i2c | spi | uart | usart | gpio | pwm | usb | ethernet | can | can_fd | hdmi | displayport | mipi_dsi | mipi_csi | camera | lvds | pcie | sata | emmc | sd | sdio | i2s | sai | audio | adc | dac | jtag | swd | rtc | watchdog | qspi | nand | nor_flash | hyperflash | touch | other`

---

## RACI Matrix

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
