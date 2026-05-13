# Component Schema Extension for Hardware Map

## Overview

Extended the `hardware_map` schema in `librarian.py` to support external components (cameras, sensors, displays) that connect to the main board. This enables the hardware mapping system to differentiate between board peripherals and external components while preserving connection interface specifications.

## Schema Extension

### New Peripheral Fields

Peripherals can now have the following additional fields:

```python
{
  "id": "camera_ov5647",
  "name": "OV5647 Camera Module",
  "type": "camera",
  
  # NEW: Component identification
  "is_component": True,           # Mark as external component (default: False)
  "connection_type": "mipi_csi",  # How it connects (mipi_csi, i2c, spi, usb, uart, etc.)
  
  # NEW: Connection interface specification
  "connector": {
    "pins": ["CSI_D0", "CSI_D1", "CSI_D2", "CSI_D3", "CSI_CLK", "CSI_HS", "GND", "VDDIO"],
    "voltage": "1.8V",                              # Power requirement
    "required_board_interface": "MIPI_CSI0"         # Must exist on board
  },
  
  # NEW: Component IC information
  "component_ic": {
    "name": "OV5647",
    "vendor": "OmniVision",
    "type": "camera_sensor"
  },
  
  # NEW: Origin tracking
  "source_pdf": "pdf_2"  # Which PDF this came from in merge
}
```

### Valid Connection Types

```
mipi_csi, mipi_dsi, i2c, spi, usb, uart, gpio, hdmi, displayport,
lvds, pcie, sata, eth, can, i2s, audio, usart, qspi, 
touchscreen_i2c, touchscreen_spi
```

### Valid Component IC Types

```
camera_sensor, display, touchscreen, audio_codec, amplifier,
accelerometer, gyroscope, magnetometer, temperature_sensor,
humidity_sensor, pressure_sensor, proximity_sensor, light_sensor,
motion_sensor, compass, gps, modem, nfc, bluetooth, wifi,
microphone, speaker, regulator, pmic
```

## Implementation Details

### 1. New Validation Functions

#### `_validate_component(peripheral: dict, board_buses: set) -> tuple[bool, list[str]]`

Validates component-specific requirements:
- `is_component=True` peripherals must have `connection_type`
- Connection type must be in `_VALID_CONNECTION_TYPES`
- Must have `connector.voltage` (power requirement)
- `connector.required_board_interface` must exist on board
- Should have `component_ic` info with valid type

Returns `(is_valid, errors)` tuple. Non-component peripherals skip validation.

#### `_separate_components(peripherals: list[dict]) -> tuple[list[dict], list[dict]]`

Separates board peripherals from components by checking `is_component` flag.
Returns `(board_peripherals, components)`.

### 2. Updated `merge_hardware_maps()` Function

Enhanced to handle components during merge:

1. **Separation Phase**: Board peripherals and components are separated before deduplication
   - Components handled independently with different deduplication logic
   
2. **Deduplication Logic**:
   - Board peripherals: deduplicate by `(bus_name, type)` pair
   - Components: deduplicate by `id` (first occurrence wins)
   
3. **Source Tracking**: `source_pdf` field marks which PDF contributed each peripheral
   - Format: `pdf_1`, `pdf_2`, etc.
   - Preserves original `source_pdf` if already set
   
4. **Connector Preservation**: 
   - All connector interface info preserved during merge
   - Component IC information maintained
   
5. **Warning System**:
   - Logs duplicate components (keeps first occurrence)
   - Logs missing board interfaces for components
   - Logs unknown regulators

### 3. Updated `_normalise_hw_map()` Function

Added default values for new component fields:

```python
p_defaults = {
    "id": "", "name": "", "type": "other", "bus": "", "address": "",
    "irq": None, "description": "", "voltage": "3.3V", "regulator": "vcc-3v3",
    "is_component": False,              # NEW
    "connection_type": "",              # NEW
    "source_pdf": ""                    # NEW
}
```

## Usage Examples

### Example 1: Merging Board with Camera Component

```python
# Board definition
board = {
    "board": "Raspberry Pi 4",
    "soc": "BCM2711",
    "peripherals": [
        {
            "id": "mipi_csi0",
            "name": "MIPI CSI-2 Interface 0",
            "type": "mipi_csi",
            "bus": "MIPI_CSI0",
            "voltage": "1.8V"
        }
    ],
    "power_rails": [...]
}

# Camera component
camera = {
    "board": None,
    "soc": None,
    "peripherals": [
        {
            "id": "camera_ov5647",
            "name": "OV5647 Camera Module",
            "type": "camera",
            "is_component": True,
            "connection_type": "mipi_csi",
            "connector": {
                "pins": ["CSI_D0", "CSI_D1", "CSI_D2", "CSI_D3", "CSI_CLK", "CSI_HS"],
                "voltage": "1.8V",
                "required_board_interface": "MIPI_CSI0"
            },
            "component_ic": {
                "name": "OV5647",
                "vendor": "OmniVision",
                "type": "camera_sensor"
            }
        }
    ]
}

# Merge
merged = merge_hardware_maps([board, camera])
```

### Example 2: Validating Component Before Merge

```python
from librarian import _validate_component

component = {...}  # Component peripheral
board_buses = {"MIPI_CSI0", "I2C1"}

is_valid, errors = _validate_component(component, board_buses)
if not is_valid:
    for error in errors:
        print(f"Validation error: {error}")
```

## Testing

Created comprehensive test suite: `test_librarian_components.py`

### Test Coverage

**Component Validation Tests (9 tests)**
- Valid component validation
- Missing connection_type
- Invalid connection_type
- Missing connector info
- Missing connector voltage
- Board interface not found
- Missing IC info
- Invalid IC type
- Non-components skip validation

**Component Separation Tests (4 tests)**
- Both board and components
- Only board peripherals
- Only components
- Default is_component=False

**Merge with Components Tests (5 tests)**
- Board and components merge correctly
- Components marked with source_pdf
- Connector info preserved
- Duplicate components warning
- New fields normalized

**Normalization Tests (2 tests)**
- Component defaults added
- Component info preserved

**Integration Tests (2 tests)**
- Full workflow: merge and normalize
- Multiple boards with components

### Test Results

```
22 tests passed, 0 failed
✓ All validation, separation, merge, normalization, and integration tests pass
```

## Backward Compatibility

Changes are fully backward compatible:

1. **Existing peripherals unchanged**: `is_component` defaults to `False`
2. **Existing merge logic preserved**: Board deduplication unchanged
3. **New fields optional**: `_normalise_hw_map()` adds defaults
4. **Existing tests pass**: Bus validator and alternative connections tests unchanged

## Example Component Definitions

### Camera Module (MIPI CSI)

```json
{
  "id": "camera_ov5647",
  "name": "OV5647 Camera Module",
  "type": "camera",
  "is_component": true,
  "connection_type": "mipi_csi",
  "connector": {
    "pins": ["CSI_D0", "CSI_D1", "CSI_D2", "CSI_D3", "CSI_CLK", "CSI_HS", "GND", "VDDIO"],
    "voltage": "1.8V",
    "required_board_interface": "MIPI_CSI0"
  },
  "component_ic": {
    "name": "OV5647",
    "vendor": "OmniVision",
    "type": "camera_sensor"
  }
}
```

### Temperature Sensor (I2C)

```json
{
  "id": "sensor_tmp36",
  "name": "TMP36 Temperature Sensor",
  "type": "sensor",
  "is_component": true,
  "connection_type": "i2c",
  "address": "0x48",
  "connector": {
    "pins": ["SDA", "SCL", "GND", "VDDIO"],
    "voltage": "3.3V",
    "required_board_interface": "I2C1"
  },
  "component_ic": {
    "name": "TMP36",
    "vendor": "Analog Devices",
    "type": "temperature_sensor"
  }
}
```

### Display (HDMI)

```json
{
  "id": "display_hdmi",
  "name": "HDMI Display",
  "type": "display",
  "is_component": true,
  "connection_type": "hdmi",
  "connector": {
    "pins": ["HDMI_D0+", "HDMI_D0-", "HDMI_D1+", "HDMI_D1-", "HDMI_CLK+", "HDMI_CLK-"],
    "voltage": "5.0V",
    "required_board_interface": "HDMI0"
  },
  "component_ic": {
    "name": "Display Module",
    "vendor": "Various",
    "type": "display"
  }
}
```

## Future Enhancements

1. **Power supply tracking**: Link components to board power rails
2. **Pin mapping**: Validate actual pin assignments
3. **Compatibility matrix**: Cross-check component compatibility
4. **Driver integration**: Link components to kernel drivers
5. **Cost/sourcing**: Add component sourcing information
6. **Thermal info**: Track power dissipation and thermal requirements
