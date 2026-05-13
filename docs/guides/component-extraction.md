# Board vs Component PDF Auto-Detection

## Overview

Enhanced `server/agents/librarian.py` with automatic detection and classification of hardware datasheets:
- **Board PDFs**: Contain a System-on-Chip (SoC) with internal peripherals, registers, and power management
- **Component PDFs**: External modules with only connector pinout (cameras, sensors, breakout boards)

## Implementation

### 1. Classification Function

**`classify_pdf_type(hardware_map: dict) -> str`**

Determines if extracted hardware map is from a board or component based on SoC detection.

```python
# Returns "board" if SoC found, "component" otherwise
pdf_type = classify_pdf_type(hardware_map)
```

Logic:
- Checks `hardware_map["soc"]` field
- Returns `"board"` if SoC is present and not "unknown" or empty
- Returns `"component"` otherwise

### 2. Pin Pattern Detection

**`_PIN_PATTERNS` - Connection type regex patterns:**

```python
{
    "mipi_csi": r"CSI[-_]?D[0-3]|CSI[-_]?(?:CLK|HS[PC]|VS)",
    "i2c":      r"\b(?:SDA|SCL|INT|ALERT)\b",
    "spi":      r"\b(?:MOSI|MISO|CLK|CS|SCLK|SDI|SDO)\b",
    "usb":      r"\b(?:DP|DM|VBUS|D[\+\-])\b",
    "uart":     r"\b(?:TX|RX|TXD|RXD|RTS|CTS)\b",
}
```

Detects:
- **MIPI CSI**: Camera interface pins (CSI_D0-3, CSI_CLK, CSI_HS*, CSI_VS)
- **I2C**: Two-wire interface (SDA, SCL, optionally INT, ALERT)
- **SPI**: Serial peripheral interface (MOSI, MISO, CLK, CS)
- **USB**: Universal serial bus (DP, DM, VBUS)
- **UART**: Serial communication (TX, RX, optionally RTS, CTS)

### 3. Connector Information Extraction

**`_extract_connector_pins(peripheral: dict) -> List[str]`**

Extracts pin signal names from peripheral description.

Algorithm:
1. Search peripheral description for pin patterns (e.g., "CSI_D0", "SDA", "MOSI")
2. If found, return unique pin names
3. Fallback: Use bus label (e.g., "CSI0" → ["CSI0_PIN"])

### 4. Component Enrichment

**`enrich_component_peripheral(peripheral: dict) -> dict`**

Adds component-specific fields to peripheral dict:

```python
{
    # Original fields preserved
    "id": "csi_0",
    "name": "MIPI CSI Camera",
    "type": "mipi_csi",
    "bus": "CSI0",
    "voltage": "3.3V",
    
    # Component-specific additions
    "is_component": True,
    "connection_type": "mipi_csi",
    "connector_pins": ["CSI_D0", "CSI_D1", "CSI_CLK", "CSI_HS", "CSI_VS", "GND"],
    
    # Board-specific fields removed
    # (address, irq not included)
}
```

**Enrichment logic:**
- Detects connection type from pin names
- Sets `is_component = True`
- Extracts `connector_pins` list
- Removes internal fields (address, irq)
- Simplifies description to connector format

### 5. Hardware Map Enrichment

**`enrich_hardware_map_for_type(hardware_map: dict, pdf_type: str = None) -> dict`**

Enriches entire hardware map based on PDF type.

Features:
- Auto-detects PDF type if not specified
- Adds `pdf_type` field to map
- For components: enriches all peripherals with connection info
- For boards: preserves original structure

```python
# Auto-detect
enriched = enrich_hardware_map_for_type(hardware_map)
# pdf_type will be set to "board" or "component"

# Or specify type
enriched = enrich_hardware_map_for_type(hardware_map, pdf_type="component")
```

## Example Outputs

### Board Example

Input: Raspberry Pi 4 datasheet

```json
{
  "board": "Raspberry Pi 4 Model B",
  "soc": "BCM2711",
  "pdf_type": "board",
  "peripherals": [
    {
      "id": "uart_0",
      "name": "UART0",
      "type": "uart",
      "address": "0x7e201000",
      "regulator": "vcc-3v3"
    }
  ]
}
```

### Component Example

Input: MIPI CSI camera module datasheet

```json
{
  "board": null,
  "soc": "Unknown SoC",
  "pdf_type": "component",
  "peripherals": [
    {
      "id": "csi_0",
      "name": "MIPI CSI Camera",
      "type": "mipi_csi",
      "bus": "CSI0",
      "is_component": true,
      "connection_type": "mipi_csi",
      "connector_pins": ["CSI_D0", "CSI_D1", "CSI_CLK", "CSI_HS", "CSI_VS", "GND"],
      "voltage": "3.3V",
      "description": "MIPI CSI connector: CSI_D0, CSI_D1, CSI_CLK, CSI_HS"
    }
  ]
}
```

## Test Results

All 21 tests pass ✓

### Classification Tests (4/4)
- ✓ Board with SoC → classified as "board"
- ✓ Component with "Unknown SoC" → classified as "component"
- ✓ Component with empty SoC → classified as "component"
- ✓ Missing SoC field → classified as "component"

### Connection Type Detection (6/6)
- ✓ MIPI CSI: CSI_D0, CSI_D1, CSI_CLK → "mipi_csi"
- ✓ I2C: SDA, SCL, INT → "i2c"
- ✓ SPI: MOSI, MISO, CLK, CS → "spi"
- ✓ USB: DP, DM, VBUS → "usb"
- ✓ UART: TX, RX → "uart"
- ✓ Generic: PIN1, PIN2 → "generic"

### Pin Extraction (2/2)
- ✓ Extract from description: "CSI_D0, CSI_D1, CSI_CLK" parsed correctly
- ✓ Fallback to bus: "I2C_EXT" → ["I2C_EXT_PIN"]

### Component Enrichment (4/4)
- ✓ Peripheral enrichment adds is_component, connection_type, connector_pins
- ✓ Removes board-specific fields (address, irq)
- ✓ Hardware map enrichment (component)
- ✓ Hardware map enrichment (board) - no modification

### Integration (3/3)
- ✓ Full board workflow
- ✓ Full component workflow
- ✓ JSON serialization compatibility

## File Changes

### Modified
- `server/agents/librarian.py` (+145 lines)
  - Added `_PIN_PATTERNS` dict for connection detection
  - Added `classify_pdf_type()` function
  - Added `_detect_connection_type_from_pins()` function
  - Added `_extract_connector_pins()` function
  - Added `enrich_component_peripheral()` function
  - Added `enrich_hardware_map_for_type()` function

### Created
- `test_board_vs_component.py` (12.7 KB)
  - 21 comprehensive tests covering all functions
  - Board and component fixtures
  - Classification, detection, extraction, enrichment tests
  - Integration tests

## Usage in Main Extraction Flow

To integrate into the main librarian extraction:

```python
from server.agents.librarian import (
    run_sections,
    classify_pdf_type,
    enrich_hardware_map_for_type,
)

# Extract hardware map
hardware_map, mode, logs = run_sections(sections)

# Classify and enrich
pdf_type = classify_pdf_type(hardware_map)
enriched_map = enrich_hardware_map_for_type(hardware_map, pdf_type=pdf_type)

# enriched_map now includes pdf_type and component-specific fields
print(enriched_map["pdf_type"])  # "board" or "component"
```

## Design Decisions

### 1. SoC as Primary Indicator
The presence of a System-on-Chip is the most reliable indicator of a board PDF vs component.
- Boards always have a main SoC (BCM2711, RK3588, i.MX8, etc.)
- Components may have processors but are not the main system

### 2. Pin Pattern Matching
Connection types are inferred from signal names rather than peripheral count, because:
- Components often have minimal peripheral info
- Pin names are consistently formatted across manufacturers
- Pattern matching is fast and requires no LLM

### 3. Component-Specific Fields
Additional fields (`is_component`, `connection_type`, `connector_pins`) help:
- Distinguish components in post-processing
- Enable component-specific routing in device tree generation
- Provide connector information for pinout documentation

### 4. Field Removal for Components
Board-specific fields (address, irq) are removed from component peripherals because:
- Components don't have register-mapped interfaces
- These fields are meaningless for external modules
- Cleaner data model for further processing

## Future Enhancements

Potential improvements:
1. Multi-pin detection (extract individual pins instead of groups)
2. Voltage rail detection from connector specs (3.3V, 5V detection)
3. Power consumption extraction for components
4. Component category classification (camera, sensor, breakout, etc.)
5. Integration with main extraction flow in `run_sections()`
6. Device tree generation for component connectors
