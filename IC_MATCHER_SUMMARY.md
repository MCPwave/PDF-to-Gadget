# IC Matcher: Component IC Recognition from PDF Text

## Overview

Created a comprehensive IC matcher module that recognizes known camera, sensor, and display integrated circuits (ICs) from kernel driver databases. The matcher scans PDF text for known component names and extracts metadata including component type, connection interface, and confidence scores.

## Implementation Details

### Location
- **Module**: `server/agents/ic_matcher.py`
- **Tests**: `server/agents/test_ic_matcher.py`

### Supported ICs (31 total from kernel_scout driver DB)

#### Camera Sensors (4)
- **OV5647**: MIPI CSI (also USB)
- **IMX219**: MIPI CSI
- **IMX477**: MIPI CSI
- **AR0521**: MIPI CSI

#### Display Controllers (4)
- **ILI9341**: SPI
- **ST7789**: SPI
- **ST7735**: SPI
- **UC8159**: SPI

#### Touchscreen Controllers (3)
- **FT5406**: I2C
- **EDT-FT5X06**: I2C
- **GOODIX**: I2C

#### Temperature Sensors (2)
- **TMP36**: I2C
- **BMP280**: I2C / SPI

#### Accelerometers / IMUs (2)
- **MPU6050**: I2C / SPI
- **LSM6DSM**: I2C / SPI

#### Proximity & Light Sensors (2)
- **APDS9960**: I2C
- **BH1750**: I2C

#### Power Management (2)
- **AXP209**: I2C
- **TPS65217**: I2C

#### ADCs (4)
- **ADS1015**: I2C
- **ADS1115**: I2C
- **MCP3008**: SPI
- **MCP3208**: SPI

#### GPIO Expanders (3)
- **PCF8574**: I2C
- **MCP23017**: I2C
- **MCP23008**: I2C

#### Real-Time Clocks (2)
- **DS1307**: I2C
- **PCF8563**: I2C

#### LEDs / Lighting (2)
- **APA102**: SPI
- **WS2812**: SPI

## Core Functions

### `match_component_ics(pdf_text: str) -> List[ICMatch]`
Main function that scans PDF text and returns matched ICs with metadata.

**Returns:**
```python
[
    ICMatch(
        ic_name="ov5647",              # Normalized IC name
        component_type="camera_sensor", # Type from driver DB
        connection_type="mipi_csi",    # Inferred from context or defaults
        context="...surrounding 100 chars...",
        confidence=0.9                 # Confidence score (0.5-0.9)
    ),
    ...
]
```

### `match_component_ics_with_positions(pdf_text: str) -> List[Dict]`
Returns matches with text position information for highlighting/mapping.

**Additional fields:**
- `position`: (start_index, end_index) tuple for the IC name in text

## Key Features

### 1. **Case-Insensitive Matching**
- Matches IC names regardless of case: `OV5647`, `ov5647`, `OV5647`
- Handles dashed names: `edt-ft5x06`, `EDT-FT5X06`

### 2. **Connection Type Inference**
Determines how IC connects to main processor:

**Explicit Detection** (looks for keywords in context):
- MIPI/CSI → mipi_csi
- I2C/IIC/TWI → i2c
- SPI/3-wire/4-wire → spi
- USB/UVC → usb
- UART/Serial/RS-232 → uart
- GPIO/Digital → gpio
- HDMI → hdmi
- DSI → dsi

**Fallback to Defaults**: If no keywords found, uses datasheet-known defaults:
- OV5647 → mipi_csi (primary), usb (alternative)
- BMP280 → i2c (primary), spi (secondary)
- etc.

### 3. **Confidence Scoring**
Three-tier confidence system:

| Confidence | Condition | Example |
|------------|-----------|---------|
| **0.9** (High) | IC + connection type both in context | "OV5647 uses MIPI CSI" |
| **0.7** (Medium) | IC found, connection from defaults | "OV5647 and BMP280" (no connection keywords) |
| **0.5** (Low) | IC found, no connection info | Minimal context |

### 4. **Context Extraction**
- Extracts ~100 characters before and after matched IC
- Useful for understanding IC's role in schematic
- Cleaned whitespace for readability

### 5. **Position Tracking**
- Optional position tracking for PDF annotation
- Maps IC names to their location in source text
- Useful for multi-reference PDFs

## Test Coverage

### Test Suite: 17 Tests, 100% Pass Rate

**Known IC Recognition:**
- OV5647, ILI9341, TMP36 single matches
- Unknown IC filtering (no false positives)
- Empty text handling

**Case Insensitivity:**
- Uppercase, lowercase, mixed case
- Multiple ICs with varying cases
- Dashed IC names (edt-ft5x06)

**Connection Type Inference:**
- MIPI CSI keyword detection
- I2C keyword detection
- SPI keyword detection
- Default connection fallback

**Multiple Matches:**
- 2 ICs in same sentence
- 3 ICs in different sections
- Same IC appearing multiple times

**Position Tracking:**
- Accurate start/end positions
- Text order verification

## Usage Examples

### Basic IC Detection
```python
from server.agents.ic_matcher import match_component_ics

pdf_text = """
The Raspberry Pi Camera Module uses OV5647 sensor.
It connects via MIPI CSI-2 interface.
Display is ILI9341 controlled via SPI.
"""

matches = match_component_ics(pdf_text)
for match in matches:
    print(f"{match.ic_name}: {match.component_type}")
    print(f"  Connection: {match.connection_type}")
    print(f"  Confidence: {match.confidence}")
```

### With Position Tracking
```python
results = match_component_ics_with_positions(pdf_text)
for result in results:
    start, end = result["position"]
    print(f"Found {result['ic_name']} at position {start}-{end}")
```

## Integration Points

### With kernel_scout.py
- Uses same `_COMPONENT_DRIVER_DB` structure
- Can cross-reference IC with driver information
- Confidence scores useful for component validation

### With PDF Processing Pipeline
- Accepts text extracted from PDF (PyPDF2, pdfplumber, etc.)
- Returns structured data for downstream processing
- Position tracking enables interactive PDF annotation

### Component Validation Integration
- Can feed IC matches to `component_validator.py`
- Validates connection types against board schema
- Feeds into bus validation pipeline

## Performance Characteristics

- **Regex Compilation**: O(n) where n = number of known ICs (31)
- **Text Scanning**: O(m) where m = text length
- **Per-Match Processing**: O(1) for metadata lookup
- **Overall Complexity**: O(n + m) - efficient for large PDFs

## Future Enhancements

1. **Alias Support**: Map variant names (e.g., "OV5647-YUV" → "OV5647")
2. **Version Detection**: Extract IC revision numbers from text
3. **Pinout Context**: Identify pin configuration patterns in text
4. **Cross-Reference**: Link to kernel driver documentation URLs
5. **Batch Processing**: Handle multiple PDFs efficiently
6. **ML Enhancement**: Use context ML to improve confidence scores

## Files Created

1. **ic_matcher.py** (281 lines)
   - Core IC matching functionality
   - Dataclass for match results
   - Helper functions for context extraction and connection inference
   - Built-in test cases

2. **test_ic_matcher.py** (298 lines)
   - Comprehensive unit test suite
   - 17 test cases covering all major functionality
   - Can be run with pytest or custom runner

## Summary

Successfully created a production-ready IC matcher that:
✅ Recognizes 31 known component ICs from kernel driver DB
✅ Performs case-insensitive matching
✅ Infers connection types from context with fallback to defaults
✅ Provides confidence scoring (0.5-0.9)
✅ Extracts surrounding context for verification
✅ Tracks position information for PDF annotation
✅ 100% test pass rate (17/17 tests)
✅ Documented with examples and integration points

Ready for integration into PDF processing and component validation pipeline.
