# Connector Pin Parser

A comprehensive Python module for extracting bus types, pin names, connector types, and voltage information from PDF connector/interface sections.

## Quick Start

```python
from connector_parser import parse_connector_pins

text = """
I2C Interface Header
Type: 4-pin header
Voltage: 3.3V

Pin 1: VCC
Pin 2: GND
Pin 3: SDA
Pin 4: SCL
"""

result = parse_connector_pins(text)
# Output: {
#     'bus_type': 'I2C',
#     'pins': ['VCC', 'GND', 'SDA', 'SCL'],
#     'connector_type': '4-pin header',
#     'voltage': '3.3V',
#     'confidence': 0.95
# }
```

## Installation

No external dependencies required. Uses only Python standard library (re).

```bash
# Copy connector_parser.py to your project
cp connector_parser.py /path/to/project/
```

## API Reference

### Main Function

#### `parse_connector_pins(section_text: str) -> dict`

Parses connector/interface section text and extracts structured information.

**Parameters:**
- `section_text` (str): Text block from a Connector/Interface/Pinout section

**Returns:**
```python
{
    'bus_type': str,         # MIPI_CSI, I2C, SPI, USB, UART, HDMI, or 'unknown'
    'pins': List[str],       # List of pin names
    'connector_type': str,   # e.g., "30-pin FPC", "USB Type-C"
    'voltage': Optional[str],# e.g., "3.3V", "5V"
    'confidence': float      # 0.0 to 1.0 confidence score
}
```

### Bus Types Supported

| Bus Type | Example Pins | Keywords |
|----------|-------------|----------|
| MIPI_CSI | CSI_D0, CSI_CLK, CSI_HS | mipi, csi, camera serial interface |
| I2C | SDA, SCL | i2c, i²c, iic, two-wire |
| SPI | MOSI, MISO, CLK, CS | spi, serial peripheral interface |
| USB | DP, DM, VBUS | usb, universal serial bus |
| UART | TX, RX, RTS, CTS | uart, serial, rs-232 |
| HDMI | D0_P, D0_N, CLK_P | hdmi, high-definition multimedia |

## Features

### Pin Extraction
Supports multiple text formats:
- **Tables**: "Pin 1: VCC | Power Supply"
- **CSV Lists**: "SDA, SCL, INT"
- **GPIO Style**: "1: GPIO2, 2: GPIO3"
- **Inline**: "CSI_D0: camera data line"
- **Diagrams**: "Pin/Signal name: description"

### Bus Type Inference
- Keyword matching (MIPI, I2C, SPI, USB, UART, HDMI)
- Pin pattern matching (SDA/SCL for I2C, CSI_* for MIPI, etc.)
- Optional pin presence detection
- Weighted scoring for disambiguation

### Connector Recognition
- Pin counts: "50-pin FPC", "40-pin header"
- Named types: "USB Type-C", "Micro USB", "HDMI"
- Pitch specs: "2.54mm header", "0.1 inch header"
- Generic types: "standard header", "ribbon connector"

### Voltage Detection
- Standard format: "3.3V", "5V", "1.8V"
- Alternative format: "3V3", "1V8"
- Context-aware: "3.3V IO", "5V Power"

## Examples

### Camera Module (MIPI CSI)
```python
text = """
30-pin FPC MIPI CSI Connector
Operating voltage: 1.8V

Pins:
CSI_D0: data lane 0
CSI_D1: data lane 1
CSI_CLK: clock signal
CSI_HS: horizontal sync
CSI_VS: vertical sync
"""

result = parse_connector_pins(text)
assert result['bus_type'] == 'MIPI_CSI'
assert 'CSI_D0' in result['pins']
```

### I2C Sensor (Temperature, Humidity, etc.)
```python
text = """
I2C Sensor Header
4-pin 0.1" header, 3.3V

Pin 1: VCC
Pin 2: GND
Pin 3: SDA
Pin 4: SCL
"""

result = parse_connector_pins(text)
assert result['bus_type'] == 'I2C'
assert result['voltage'] == '3.3V'
```

### USB Type-C with Power Delivery
```python
text = """
USB Type-C Connector
USB 3.1 Gen 1, Power Delivery
5V/3A standard, 20V/5A with PD

Pins: GND, TX1_P, TX1_N, VBUS, RX2_N, RX2_P, D+, D-
"""

result = parse_connector_pins(text)
assert result['bus_type'] == 'USB'
assert 'Type-C' in result['connector_type']
```

## Testing

Run the test suite:
```bash
python3 run_tests.py
```

Output:
```
======================================================================
Results: 40 passed, 0 failed
======================================================================
```

Test categories:
- Pin extraction (6 tests)
- Bus type inference (9 tests)
- Connector type detection (5 tests)
- Voltage extraction (5 tests)
- Full parsing (8 tests)
- Real-world examples (3 tests)
- Edge cases (4 tests)

## Integration with component_extractor

```python
from component_extractor import extract_section_text
from connector_parser import parse_connector_pins

# Extract connector section from PDF
section_text = extract_section_text(pdf_text, "Pin Map", context_lines=20)

# Parse the section
result = parse_connector_pins(section_text)

# Use the result
print(f"Bus Type: {result['bus_type']}")
print(f"Pins: {', '.join(result['pins'])}")
print(f"Voltage: {result['voltage']}")
```

## Performance

- **Speed**: ~40ms per parse (typical case)
- **Memory**: Minimal - processes text in single pass
- **Scalability**: Handles sections up to 200+ lines
- **Dependencies**: None (standard library only)

## Confidence Scoring

Confidence (0.0-1.0) calculated from:
- Bus type keyword matches: +0.4 per keyword
- Pin pattern matches: +0.5 maximum
- Optional pin presence: +0.1 per pin
- Connector type detection: +0.1
- Voltage specification: +0.05
- Pin count: +0.1 (up to 5+ pins)

## Limitations

1. **Complex layouts**: Table-based multi-column layouts may not extract perfectly
2. **Ambiguous pins**: Conflicting pin patterns (e.g., GPIO names matching HDMI patterns)
3. **Multiple bus types**: Single parser call detects primary bus type only
4. **OCR artifacts**: PDF extraction errors may reduce accuracy

## Future Improvements

- Machine learning for bus type disambiguation
- OCR support for pin diagrams
- Multi-line table parsing
- Custom bus type definitions
- Database lookups for known connectors

## License

Part of the PDFConnectorParser project.

## Contributing

Submit issues and pull requests for:
- New bus type support
- Improved pin extraction patterns
- Better connector recognition
- Test cases for edge scenarios
