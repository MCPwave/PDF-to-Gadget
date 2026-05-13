# Component Connection Validator — Implementation Summary

## Overview
The component connection validator checks component connections against board capabilities and verifies driver availability. It validates:
1. **Interface Existence**: Component's required interface exists on the board
2. **Voltage Compatibility**: Component connector voltage matches board interface voltage
3. **IC Driver Availability**: Component IC driver exists in kernel database
4. **Board Interface Driver**: Board interface driver (e.g., MIPI_CSI host) exists

## Files Created

### 1. `component_validator.py` (11.8 KB)
Main validator module with core validation logic.

**Public API:**
```python
def validate_component_connections(
    board_map: dict,
    components_list: List[dict],
) -> dict
```

**Return Structure:**
```python
{
    "valid": True,  # Always true (warn mode, never halts)
    "component_status": [
        {
            "component_id": "camera_ov5647",
            "component_name": "OV5647 Camera",
            "required_interface": "MIPI_CSI0",
            "status": "OK|MISMATCH|NO_DRIVER|NO_INTERFACE",
            "message": "...",
            "drivers": {
                "ic_driver": {
                    "name": "OV5647",
                    "status": "mainline|backport|vendor|unknown"
                },
                "interface_driver": {
                    "name": "bcm2835-unicam",
                    "status": "mainline|backport|vendor|unknown"
                }
            },
            "alternatives": [
                {
                    "connection_type": "usb|mipi_dsi|...",
                    "driver_status": "mainline|backport|vendor|unknown",
                    "effort": "low|medium|high"
                }
            ]
        }
    ],
    "summary": {
        "total_components": 3,
        "ok": 2,
        "warnings": 1,
        "blocking": 0  # Always 0 in warn mode
    }
}
```

### 2. `test_component_validator.py` (17.4 KB)
Comprehensive unittest-based test suite with 39 tests covering:

**Test Categories:**

#### Unit Tests (6 test classes, 30 tests)
- `TestParseVoltage` (7 tests): Voltage string parsing (3.3V, 1.8V, 5V, etc.)
- `TestVoltagesCompatible` (6 tests): Voltage compatibility checking with tolerance
- `TestFindBoardInterface` (4 tests): Interface lookup by bus name or ID
- `TestGetInterfaceType` (6 tests): Interface type extraction (MIPI_CSI0 → mipi_csi)
- `TestValidateComponentConnections` (9 tests): Main validator function
- `TestAlternativeConnections` (4 tests): Alternative connection suggestions

#### Integration Tests (9 tests)
- **OK Status**: RPi4 + OV5647 camera (both drivers mainline)
- **NO_INTERFACE**: Component requiring non-existent board interface
- **MISMATCH**: Voltage incompatibility between component and board
- **NO_DRIVER**: Unknown or missing component driver
- **Multiple Components**: Validation of 3 components with mixed results
- **Empty List**: Graceful handling of empty component list
- **Missing Fields**: Handling of missing connector/IC info
- **Edge Cases**: Missing SoC, peripherals, invalid components

## Validation Logic

### Check 1: Interface Existence
```
if component.connector.required_board_interface not in board.peripherals[].bus:
    status = "NO_INTERFACE"
    suggest alternatives
```

### Check 2: Voltage Matching
```
component_voltage = parse(connector.voltage)      # "1.8V" → 1.8
board_voltage = parse(interface.voltage)          # "1.8V" → 1.8
if |component_voltage - board_voltage| > 0.1V:   # default tolerance
    status = "MISMATCH"
    suggest alternatives
```

### Check 3: Component IC Driver
```
driver_info = kernel_scout._lookup_db(soc, ic_type)
if driver_info is None:
    try_fallback_to_component_type()
if status == "unknown":
    status = "NO_DRIVER"
    suggest alternatives
```

### Check 4: Board Interface Driver
```
interface_type = _get_interface_type("MIPI_CSI0")  # → "mipi_csi"
driver_info = kernel_scout._lookup_db(soc, interface_type)
if status == "unknown":
    status = "NO_DRIVER"
    suggest alternatives
```

## Key Functions

### Voltage Utilities
- `_parse_voltage(voltage_str: str) -> Optional[float]`
  - Parse "3.3V", "1.8V", "5 V" → 3.3, 1.8, 5.0
  - Returns None for invalid input

- `_voltages_compatible(comp_v: str, board_v: str, tolerance=0.1) -> bool`
  - Check voltage compatibility with 0.1V tolerance (default)
  - Supports custom tolerance values

### Interface Utilities
- `_find_board_interface(board_map: dict, required_interface: str) -> Optional[dict]`
  - Find board peripheral by bus name or ID
  - Supports case-insensitive lookup

- `_get_interface_type(interface_name: str) -> str`
  - Extract type from name: "MIPI_CSI0" → "mipi_csi"
  - Handles numbered interfaces and underscores

### Driver Utilities
- `_get_connection_alternatives(peripheral_type: str, soc: str) -> List[Dict]`
  - Get alternative connection types from alternative_connections.py
  - Look up driver status for each alternative
  - Estimate effort level (low/medium/high)

## Test Results

```
Ran 39 tests in 0.002s
OK

Coverage:
✓ Unit tests for voltage parsing and compatibility
✓ Unit tests for interface lookup and type extraction
✓ Integration tests for all validation statuses
✓ Edge case handling (missing fields, invalid data)
✓ Multiple component validation
✓ Alternative connection suggestions
```

## Example Usage

```python
from component_validator import validate_component_connections

board_map = {
    "soc": "BCM2711",
    "peripherals": [
        {
            "bus": "MIPI_CSI0",
            "voltage": "1.8V",
            "type": "mipi_csi"
        }
    ]
}

components = [
    {
        "id": "camera_ov5647",
        "name": "OV5647 Camera",
        "type": "camera",
        "connector": {
            "voltage": "1.8V",
            "required_board_interface": "MIPI_CSI0"
        },
        "component_ic": {
            "name": "OV5647",
            "type": "camera_sensor"
        }
    }
]

result = validate_component_connections(board_map, components)

# Result:
# {
#     "valid": True,
#     "component_status": [{
#         "component_id": "camera_ov5647",
#         "status": "OK",
#         "drivers": {
#             "ic_driver": {"name": "OV5647", "status": "mainline"},
#             "interface_driver": {"name": "bcm2835-unicam", "status": "mainline"}
#         }
#     }],
#     "summary": {"total_components": 1, "ok": 1, "warnings": 0}
# }
```

## Validation Statuses

| Status | Meaning | When | Action |
|--------|---------|------|--------|
| **OK** | All checks passed | IC & interface drivers available, voltage matches, interface exists | Proceed |
| **NO_INTERFACE** | Required board interface missing | Interface not in board peripherals | Suggest alternatives |
| **MISMATCH** | Voltage or interface incompatible | Voltage differs >0.1V or other conflict | Suggest alternatives |
| **NO_DRIVER** | Driver not found for IC or interface | _lookup_db returns None | Suggest alternatives |

## Integration Points

### Dependencies
- `kernel_scout._lookup_db(soc, ptype)` — Look up kernel drivers
- `alternative_connections.get_alternatives(ptype)` — Get alternative connection types

### Used By
- Board validation pipelines
- Component-board compatibility checking
- Driver availability assessment
- Alternative connection recommendation

## Design Decisions

1. **Warn Mode Only**: Validator always returns `valid: True` and never halts processing. Issues are reported as warnings.

2. **Voltage Tolerance**: Uses 0.1V (100mV) tolerance to account for component variations while maintaining compatibility.

3. **Fallback Driver Lookup**: If IC-specific driver lookup fails, falls back to component type lookup.

4. **Alternative Suggestions**: Always provides alternative connection types and their driver statuses to guide remediation.

5. **Graceful Degradation**: Handles missing fields, invalid data types, and empty lists without crashing.

## Testing Strategy

- **Unit Tests**: Isolated function testing for voltage, interface, type extraction
- **Integration Tests**: Full validation scenarios with realistic board/component data
- **Edge Cases**: Missing fields, invalid inputs, empty lists
- **Fixtures**: Reusable board (RPi4) and component (OV5647, HDMI, etc.) definitions

All tests use Python's built-in `unittest` module for maximum compatibility.
