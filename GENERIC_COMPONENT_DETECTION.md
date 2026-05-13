# Generic Component Detection Strategy

## Problem: Current Limitation

The system currently depends on a **hardcoded IC database**:
- AR2020 works because we added it to `ic_matcher.py`
- New ICs require manual database updates
- System fails on unknown or rare components

## Solution: Generic IC Extraction

New module `generic_ic_extractor.py` enables detection of **ANY** component from **ANY** PDF, without hardcoding.

### How It Works

**1. Extract IC Model Numbers**
- Uses flexible regex patterns: `AR2020`, `OV5647`, `BMP280`, `ST7789`, etc.
- Works with any manufacturer (onsemi, OmniVision, STMicroelectronics, etc.)
- Captures unknown/custom ICs too

```python
patterns = [
    r'\b([A-Z]{2,3}\d{3,5}[A-Z]?)\b',  # AR2020, OV5647
    r'\b(EDT-FT5[X\d]{2,3})\b',        # EDT-FT5X06
]
```

**2. Detect Component Type from Context**

Uses keyword heuristics to infer type from the text around the IC:

```
Context: "AR2020 20MP image sensor MIPI CSI-2 interface"
         → Type: camera_sensor
         → Confidence: 80%

Context: "ST7789 1.3-inch display controller SPI mode"
         → Type: display
         → Confidence: 90%

Context: "BMP280 barometer pressure sensor I2C"
         → Type: sensor_pressure
         → Confidence: 85%
```

**3. Infer Connection Type**

Looks for connection keywords in context + IC name patterns:

```
"MIPI CSI-2 interface" → connection: mipi_csi
"I2C address 0x77"    → connection: i2c
"SPI mode"            → connection: spi
"USB UVC device"      → connection: usb
```

**4. Lookup Driver Status**

If IC is in `kernel_scout.py` database:
- ✓ Show driver status (mainline/vendor/backport)

If IC is unknown:
- ✓ Mark as "unknown" driver
- ✓ System still works, just notes no driver found

### Data Flow

```
PDF Text
  ↓
[Extract IC Models] → AR2020, ST7789, BMP280, XYZ9999
  ↓
[For each IC]:
  ├─ [Detect Type from Context] → camera_sensor, display, sensor_pressure
  ├─ [Infer Connection] → MIPI_CSI, SPI, I2C
  └─ [Lookup Driver] → kernel_scout DB → found/not found
  ↓
[Component List]
  - AR2020: camera_sensor, MIPI_CSI, driver: vendor
  - ST7789: display, SPI, driver: mainline
  - BMP280: sensor_pressure, I2C, driver: mainline
  - XYZ9999: unknown_component, unknown, driver: UNKNOWN
```

### Benefits

✅ **Works with ANY component** (known or unknown)  
✅ **No database updates needed** for new ICs  
✅ **Graceful fallbacks** for unrecognized components  
✅ **Confidence scores** show reliability of each detection  
✅ **Component type inference** from context, not hardcoding  

### Implementation

New file: `server/agents/generic_ic_extractor.py`

Key functions:
```python
detect_component_type(text: str) → (type: str, confidence: float)
extract_ic_models(text: str) → [ic_name, context, confidence]
infer_connection_type(text: str, ic_name: str) → (type: str, confidence: float)
extract_generic_components(pdf_text: str) → [components with all metadata]
```

### Integration Plan

1. **librarian.py**: Call `generic_ic_extractor.extract_generic_components()` instead of just `ic_matcher.match_component_ics()`
2. **kernel_scout.py**: Lookup driver for each extracted IC (may return "unknown")
3. **component_validator.py**: Validate even unknown components (no driver = warning, not error)
4. **UI**: Display driver status as "Unknown" for ICs not in database

### Example: AR2020 Camera

Before (hardcoded):
```python
_KNOWN_COMPONENTS = {
    "ar2020": ("camera_sensor", "mipi_csi"),  # ← Must add manually
}
```

After (generic):
```
PDF: "AR2020 Image Sensor, 20 MP, MIPI CSI-2"
     ↓
IC extracted: AR2020
Type detected: camera_sensor (from "image sensor" keyword)
Connection: mipi_csi (from "MIPI CSI-2" keyword)
Driver lookup: found → vendor driver status
Result: { ic_name: "AR2020", type: "camera_sensor", conn: "mipi_csi", driver: "vendor" }
```

No database update needed. Just upload the PDF.

### Example: Unknown Component

PDF: "XYZ-9999 Custom Device, I2C interface, 3.3V supply"
     ↓
IC extracted: XYZ9999
Type detected: unknown_component (no matching keywords)
Connection: i2c (from "I2C" keyword)
Driver lookup: not found → mark as "unknown"
Result: { ic_name: "XYZ9999", type: "unknown_component", conn: "i2c", driver: "unknown" }

System doesn't fail. Notes it as custom/unknown, continues with validation.

## Next Steps

1. ✅ Create `generic_ic_extractor.py` (done)
2. ⏳ Integrate into `librarian.py` extraction pipeline
3. ⏳ Update component detection to prefer generic extractor
4. ⏳ Test with various PDFs (known ICs, unknown ICs, no ICs)
5. ⏳ Update documentation
