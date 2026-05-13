# PDF-to-Gadget Extraction Test Report

**Test Date**: 2026-05-13  
**Test Files**:
- `tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf` (40 pages, Board datasheet)
- `tests/AR2020.pdf` (2 pages, Camera sensor datasheet)

## Expected Extraction Results

### File 1: Jetson Orin NX Datasheet
**Type**: Board (SoC detected)  
**SoC**: NVIDIA Jetson Orin NX  
**Architecture**: ARM (Cortex-A78AE v8.2 64-bit)  
**GPU**: Ampere GPU  
**Key Specs**:
- 16GB or 8GB LPDDR5 RAM
- Ampere GPU + Arm Cortex-A78AE CPU

**Expected Interfaces/Peripherals**:
- CSI/MIPI camera connectors (standard for Jetson boards)
- USB interfaces
- Network interfaces
- Display connectors (HDMI, DP)
- Power delivery interfaces

**Validation**: ✓ Contains 'Jetson', ✓ Contains 'Orin', ✓ Contains 'Nvidia', ✓ Contains camera/CSI/MIPI refs

---

### File 2: AR2020 Camera Sensor
**Type**: Component (External sensor module)  
**Component Type**: Camera Sensor  
**IC/Model**: AR2020 (by onsemi)  
**Sensor Specs**:
- 20 MP image sensor
- Rolling shutter, Hyperlux LP technology
- 1/1.8 inch Back-Side Illuminated (BSI)
- 5120 x 3840 active pixel array
- Linear or eDR (enhanced Dynamic Range) mode
- Digital/CMOS image sensor

**Expected Connection**:
- **Primary**: CSI/MIPI (most likely for 20MP sensor)
- **Alternative**: USB (possible for some variants)

**Driver Requirements**:
- AR2020 camera driver (onsemi)
- MIPI_CSI host driver (if using CSI interface)

**Validation**: ✓ Contains 'AR2020', ✓ Contains 'sensor', ✓ Contains 'camera', ✓ Contains CSI/MIPI refs

---

## Multi-PDF Merge Test

**Expected Behavior**:
1. **Jetson PDF** → Board SoC detected (Nvidia Jetson Orin NX)
2. **AR2020 PDF** → Component detected (Camera sensor)
3. **Merge** → Single hardware map with:
   - Board: Nvidia Jetson Orin NX
   - Components: AR2020 camera sensor
   - Connection validation: AR2020 should match to CSI/MIPI interface

**Expected Output**:
```json
{
  "board_name": "Nvidia Jetson Orin NX",
  "soc": "Nvidia Jetson Orin NX",
  "arch": "arm64",
  "cpu_core": "Cortex-A78AE",
  "ram_mb": 8000 or 16000,
  "peripherals": [
    { "name": "CSI Camera Interface 0", "type": "camera", "bus": "MIPI_CSI" },
    { "name": "CSI Camera Interface 1", "type": "camera", "bus": "MIPI_CSI" },
    ...
  ],
  "components": [
    {
      "id": "camera_ar2020",
      "name": "AR2020 Camera Sensor",
      "type": "camera",
      "is_component": true,
      "component_ic": {
        "name": "AR2020",
        "category": "camera",
        "driver_status": "mainline"
      },
      "connection_type": "MIPI_CSI",
      "source_pdf": "AR2020.pdf"
    }
  ]
}
```

---

## Test Methodology

### Option 1: Web UI Test
1. Navigate to http://localhost:8000
2. Upload both PDF files
3. Select model (or use heuristics)
4. Verify extraction results show:
   - Jetson Orin NX as board SoC
   - AR2020 as detected camera component
   - MIPI_CSI as connection type
   - Driver status: mainline

### Option 2: API Test (SSE)
```bash
curl -X POST \
  -F "files=@tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf" \
  -F "files=@tests/AR2020.pdf" \
  http://localhost:8000/api/upload \
  -H "Accept: text/event-stream"
```

Expected SSE events:
- `component_found`: AR2020 camera sensor
- `log`: Extraction progress
- `upload_done`: Final merged hardware map

### Option 3: Python API Test
```python
from server.agents import librarian

# Load PDFs and extract
sections_jetson = extract_pdf_sections("tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf")
sections_ar2020 = extract_pdf_sections("tests/AR2020.pdf")

hw_jetson, _, _ = librarian.run_sections(sections_jetson)
hw_ar2020, _, _ = librarian.run_sections(sections_ar2020)

merged = librarian.merge_hardware_maps([hw_jetson, hw_ar2020])

# Verify
assert merged.get('soc') == 'Nvidia Jetson Orin NX'
assert any(c.get('component_ic', {}).get('name') == 'AR2020' 
           for c in merged.get('components', []))
```

---

## Verification Checklist

- [ ] Board SoC correctly identified as "Nvidia Jetson Orin NX"
- [ ] Board architecture identified as "arm64" or "arm"
- [ ] Component type "camera" detected for AR2020
- [ ] AR2020 IC correctly matched in known ICs database
- [ ] Connection type MIPI_CSI suggested (not USB)
- [ ] Driver status for AR2020: "mainline" or "vendor"
- [ ] No duplicate components in merge
- [ ] Validation report generated (if applicable)
- [ ] Web UI displays board and component separately
- [ ] API returns all components in response

