# Component Schema Extension - Implementation Summary

## Task Completion

✅ **Define component representation in hardware_map schema**

### What Was Delivered

Extended the hardware_map schema in `librarian.py` to support external components (cameras, sensors, displays) that connect to the main board. This enables the system to differentiate between board peripherals and external components while preserving connection interface specifications.

### Key Changes

#### 1. Schema Extension (librarian.py)

**New Constants:**
- `_VALID_CONNECTION_TYPES`: 19 connection types (mipi_csi, mipi_dsi, i2c, spi, usb, uart, gpio, hdmi, etc.)
- `_COMPONENT_IC_TYPES`: 23 IC types (camera_sensor, display, temperature_sensor, accelerometer, etc.)

**New Peripheral Fields:**
```python
{
  "is_component": True,           # Mark as external component
  "connection_type": "mipi_csi",  # How it connects
  "connector": {                  # Connection interface
    "pins": [...],
    "voltage": "1.8V",            # Power requirement
    "required_board_interface": "MIPI_CSI0"  # Board interface needed
  },
  "component_ic": {               # Component IC information
    "name": "OV5647",
    "vendor": "OmniVision",
    "type": "camera_sensor"
  },
  "source_pdf": "pdf_2"           # Origin tracking during merge
}
```

#### 2. New Validation Functions

**`_validate_component(peripheral: dict, board_buses: set) -> tuple[bool, list[str]]`**
- Validates component-specific requirements
- Checks connection_type validity
- Ensures connector.voltage exists
- Validates required_board_interface exists on board
- Validates component_ic.type

**`_separate_components(peripherals: list[dict]) -> tuple[list[dict], list[dict]]`**
- Separates board peripherals from components by `is_component` flag
- Returns (board_peripherals, components) tuple

#### 3. Updated merge_hardware_maps()

Enhanced to handle components properly:
- **Separation Phase**: Board peripherals and components separated before deduplication
- **Deduplication**: 
  - Board: by (bus_name, type) pair
  - Components: by id (first occurrence wins)
- **Source Tracking**: `source_pdf` field marks PDF origin
- **Connector Preservation**: All connector interface info preserved
- **Warnings**: For duplicates and missing interfaces

#### 4. Updated _normalise_hw_map()

Added defaults for new component fields:
```python
p_defaults = {
    ...existing fields...,
    "is_component": False,
    "connection_type": "",
    "source_pdf": ""
}
```

### Test Coverage

**Created: test_librarian_components.py** with 22 comprehensive tests

**Validation Tests (9 tests)**
- ✓ Valid component validation
- ✓ Missing connection_type detection
- ✓ Invalid connection_type detection
- ✓ Missing connector info detection
- ✓ Missing connector voltage detection
- ✓ Board interface not found detection
- ✓ Missing IC info detection
- ✓ Invalid IC type detection
- ✓ Non-components skip validation

**Separation Tests (4 tests)**
- ✓ Both board and components
- ✓ Only board peripherals
- ✓ Only components
- ✓ Default is_component=False

**Merge Tests (5 tests)**
- ✓ Board and components merge correctly
- ✓ Components marked with source_pdf
- ✓ Connector info preserved during merge
- ✓ Duplicate components warning
- ✓ New fields normalized after merge

**Normalization Tests (2 tests)**
- ✓ Component defaults added
- ✓ Component info preserved

**Integration Tests (2 tests)**
- ✓ Full workflow: merge board + 2 components
- ✓ Multiple boards with components

### Test Results
```
✓ 22/22 tests passed
✓ All validation tests passed
✓ All merge operations passed
✓ All integration workflows passed
✓ Existing tests unaffected (bus_validator still passes)
```

### Backward Compatibility

✅ **Fully backward compatible:**
- Existing peripherals: `is_component` defaults to False
- Existing merge logic: Board deduplication unchanged
- New fields optional: _normalise_hw_map() adds defaults
- Existing tests pass: Bus validator tests unchanged

### Example Usage

**Merging Raspberry Pi 4 board with camera and temperature sensor:**

```python
board = {
    "board": "Raspberry Pi 4",
    "soc": "BCM2711",
    "peripherals": [
        {"id": "mipi_csi0", "bus": "MIPI_CSI0", ...},
        {"id": "i2c1", "bus": "I2C1", ...}
    ]
}

camera = {
    "peripherals": [{
        "id": "camera_ov5647",
        "is_component": True,
        "connection_type": "mipi_csi",
        "connector": {
            "pins": [...],
            "voltage": "1.8V",
            "required_board_interface": "MIPI_CSI0"
        },
        "component_ic": {
            "name": "OV5647",
            "vendor": "OmniVision",
            "type": "camera_sensor"
        }
    }]
}

sensor = {
    "peripherals": [{
        "id": "sensor_tmp36",
        "is_component": True,
        "connection_type": "i2c",
        "connector": {
            "voltage": "3.3V",
            "required_board_interface": "I2C1"
        },
        "component_ic": {
            "name": "TMP36",
            "type": "temperature_sensor"
        }
    }]
}

merged = merge_hardware_maps([board, camera, sensor])
normalized = _normalise_hw_map(merged)

# Result: 4 peripherals (2 board + 2 components), properly separated and tagged
```

### Files Changed

1. **librarian.py** (+140 lines)
   - New constants: _VALID_CONNECTION_TYPES, _COMPONENT_IC_TYPES
   - New functions: _validate_component(), _separate_components()
   - Updated: merge_hardware_maps(), _normalise_hw_map()
   - Fixed: regulator validation to handle None values

2. **test_librarian_components.py** (+400 lines, NEW)
   - 22 comprehensive tests
   - Test fixtures for board, camera, sensor
   - Full coverage of validation, separation, merge, normalization

3. **COMPONENT_SCHEMA.md** (NEW)
   - Detailed documentation
   - Schema specification
   - Usage examples
   - Future enhancements

### Validation Rules Implemented

✅ Components have `is_component=True` and `connection_type` defined
✅ Board peripherals have `is_component=False` or omitted
✅ All components have `connector.voltage` (power requirement)
✅ `required_board_interface` references valid bus on board
✅ `component_ic.type` is in valid IC types list
✅ `connection_type` is in valid connection types list

### Merge Logic Enhancements

✅ Separate board peripherals from components during merge
✅ Mark component origin with source_pdf
✅ Preserve connector interface information
✅ Deduplicate components by id (first occurrence wins)
✅ Warn on duplicate components
✅ Warn on missing board interfaces
✅ Maintain all existing merge behavior for board peripherals

## Next Steps

1. Integrate component validation into upload/merge workflow
2. Add component compatibility checking against board interfaces
3. Link components to kernel driver requirements
4. Add power supply tracing through board rails
5. Create component library for common modules
