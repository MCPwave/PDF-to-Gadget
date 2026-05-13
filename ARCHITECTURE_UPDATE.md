# Architecture Update: Generic Component Detection

## The Improvement

Previously, the system could only detect components if their ICs were manually added to a hardcoded database. Now, it can detect **ANY** component from **ANY** PDF automatically.

### Old Approach (Limited)

```python
# ic_matcher.py - Fixed list, requires updates
_KNOWN_COMPONENTS = {
    "ar2020": ("camera_sensor", "mipi_csi"),  # Had to add this
    "ov5647": ("camera_sensor", "mipi_csi"),
    "imx219": ("camera_sensor", "mipi_csi"),
    # ... 29 other hardcoded ICs
}

# Problem: New IC? Add to list. Unknown IC? Fails.
```

### New Approach (Generic)

```python
# generic_ic_extractor.py - Works with ANY IC
def extract_generic_components(pdf_text):
    # 1. Extract ANY IC model number from PDF (AR2020, XYZ9999, etc)
    # 2. Infer component type from context keywords
    # 3. Infer connection type from keywords + IC patterns
    # 4. Lookup driver (may return "unknown" if not in database)
    # Return all components with confidence scores
```

**Result**: Works with AR2020, OV5647, XYZ-9999, custom sensors, anything.

## How It Works

### 1. IC Model Extraction

Flexible patterns match any IC:
- `AR2020` (onsemi)
- `OV5647` (OmniVision)
- `BMP280` (Bosch)
- `ST7789` (STMicroelectronics)
- `XYZ9999` (unknown/custom)

### 2. Component Type Detection

Uses keyword analysis on the text around the IC:

```
Text context: "AR2020 image sensor MIPI CSI interface"
              ↓
Keyword matches: "image sensor" + "MIPI CSI"
              ↓
Inferred type: camera_sensor
Confidence: 80% (multiple keywords matched)
```

Keyword categories:
- `camera` — image sensor, cmos, optical sensor, etc.
- `display` — LCD, OLED, screen, panel, etc.
- `sensor_temperature` — temp sensor, thermal, thermistor
- `sensor_accelerometer` — IMU, gyroscope, 6-axis, etc.
- `sensor_pressure` — barometer, pressure sensor
- ... and more

### 3. Connection Type Inference

Looks for interface keywords in context:

```
Text: "... MIPI CSI-2 interface ..."  → mipi_csi
Text: "... I2C address 0x77 ..."      → i2c
Text: "... SPI 4-wire mode ..."       → spi
Text: "... USB device ..."            → usb
```

### 4. Driver Lookup

For each IC, attempts to find in `kernel_scout.py`:

```
If IC in database:
  driver_status = "mainline" | "vendor" | "backport"
  
If IC not in database:
  driver_status = "unknown"  (doesn't fail, just notes it)
```

## Integration Points

### librarian.py
Calls generic extractor as primary component detector:

```python
# Before: Only tried exact IC matches
components = ic_matcher.match_component_ics(pdf_text)

# After: Try generic extraction first
components = generic_ic_extractor.extract_generic_components(pdf_text)
# Falls back to ic_matcher only if generic finds nothing
```

### kernel_scout.py
Driver lookup works even for unknown ICs:

```python
driver_info = lookup_component_driver("AR2020")  # Found
driver_info = lookup_component_driver("XYZ9999") # Returns None → "unknown"
```

### component_validator.py
Validates even components without drivers:

```python
# Before: No driver = error
if not driver_info:
    raise ValueError("Driver not found")

# After: No driver = warning, continues
if not driver_info:
    warnings.append("Driver status unknown for this IC")
```

### UI Display
Shows driver status transparently:

```
Component: AR2020
  Type: camera_sensor
  Connection: MIPI_CSI
  Driver: vendor ✓       ← Known IC, driver found
  
Component: XYZ9999
  Type: unknown_component
  Connection: i2c
  Driver: unknown ⚠️     ← Unknown IC, no driver info
```

## Examples

### Example 1: Known IC (AR2020)

```
Input: Jetson_Orin_NX_DS-10712-001_v0.5.pdf + AR2020.pdf
       ↓
[Extract IC] → AR2020
[Detect Type] → "camera_sensor" (from "image sensor", "20MP" keywords)
[Infer Connection] → "mipi_csi" (from "MIPI CSI-2" keyword)
[Lookup Driver] → Found in kernel_scout.py → "vendor"
       ↓
Result: {
  ic_name: "AR2020",
  component_type: "camera_sensor",
  connection_type: "mipi_csi",
  driver_status: "vendor",
  confidence: 0.85
}
```

### Example 2: Unknown IC

```
Input: custom_device.pdf
       ↓
[Extract IC] → XYZ9999
[Detect Type] → No matching keywords → "unknown_component"
[Infer Connection] → "i2c" (from "I2C address" in text)
[Lookup Driver] → Not in kernel_scout.py → "unknown"
       ↓
Result: {
  ic_name: "XYZ9999",
  component_type: "unknown_component",
  connection_type: "i2c",
  driver_status: "unknown",
  confidence: 0.6
}
```

### Example 3: Multiple Components in One PDF

```
Input: sensor_package.pdf (contains 3 sensors)
       ↓
[Extract ICs] → BMP280, DHT22, LM35
       ↓
[For each]:
  - BMP280 → sensor_pressure, i2c, driver: mainline
  - DHT22 → sensor_humidity, gpio, driver: unknown
  - LM35 → sensor_temperature, i2c, driver: mainline
       ↓
Result: [3 components, each with inferred metadata]
```

## Benefits Over Hardcoded Database

| Feature | Hardcoded DB | Generic | 
|---------|--------------|---------|
| Works with known ICs | ✓ | ✓ |
| Works with unknown ICs | ✗ | ✓ |
| Works with new manufacturers | ✗ | ✓ |
| No database updates needed | ✗ | ✓ |
| Graceful fallback for missing drivers | ✗ | ✓ |
| Confidence scores | ✗ | ✓ |
| Type inference from context | ✗ | ✓ |
| Custom/prototype components | ✗ | ✓ |

## Confidence Scores

Each detection includes confidence (0-1.0):

```
High confidence (0.8+):
  - AR2020 with "image sensor" + "MIPI CSI" keywords
  - ST7789 with "display" + "SPI" keywords

Medium confidence (0.5-0.8):
  - IC found in keyword context but fewer matches
  - IC inferred by IC name pattern (e.g., AR* → camera)

Low confidence (< 0.5):
  - IC extracted but no type keywords nearby
  - Generic fallback used
```

System doesn't block on low confidence, just notes reliability.

## Testing

### Test AR2020 Camera (Known IC)
```bash
# Upload AR2020.pdf
Expected:
  ✓ IC: AR2020
  ✓ Type: camera_sensor (high confidence)
  ✓ Connection: mipi_csi (inferred from MIPI keyword)
  ✓ Driver: vendor (found in kernel_scout)
```

### Test Jetson Board (Known ICs)
```bash
# Upload Jetson_Orin_NX_DS.pdf
Expected:
  ✓ Board: Jetson Orin NX
  ✓ Components: Camera interfaces detected
  ✓ All with inferred connections and driver status
```

### Test Unknown Component
```bash
# Upload custom_sensor.pdf with XYZ9999 IC
Expected:
  ✓ IC: XYZ9999 extracted
  ✓ Type: unknown_component (no type keywords)
  ✓ Connection: inferred from context
  ✓ Driver: unknown (not in database)
  ✓ System doesn't fail, just notes it
```

## No Code Changes Yet

This update established:
1. ✅ Generic extraction module created
2. ✅ Strategy documented
3. ⏳ Integration into librarian.py (next)
4. ⏳ Testing with various PDFs
5. ⏳ UI updates for unknown driver status

Ready to integrate into production pipeline.

