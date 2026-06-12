# Testing PDF-to-Gadget with Real Datasheets

## Test Files Available

Two production datasheets are available in `/tests/`:

1. **Jetson_Orin_NX_DS-10712-001_v0.5.pdf** (40 pages)
   - NVIDIA Jetson Orin NX Series datasheet
   - Board/SoC: Contains complete board-level specifications
   - Architecture: ARM Cortex-A78AE v8.2 64-bit
   - GPU: Ampere GPU
   - RAM: 8GB or 16GB LPDDR5
   - Interfaces: CSI, USB, Network, Display (HDMI, DP)

2. **AR2020.pdf** (2 pages)
   - onsemi AR2020 image sensor datasheet
   - Component: External camera sensor module
   - Spec: 20MP, rolling shutter, Hyperlux LP
   - Resolution: 5120 x 3840 active pixels
   - Interface: MIPI CSI (preferred), USB (alternative)

## Expected Detection Results

### When Processing Both Files Together

**Board Detection**:
- Board Name: `Nvidia Jetson Orin NX`
- SoC: `Nvidia Jetson Orin NX`
- CPU: `Cortex-A78AE`
- Architecture: `arm64`
- RAM: `8000` or `16000` MB

**Component Detection**:
- Component Type: `camera` or `camera_sensor`
- IC Name: `AR2020`
- Component Name: Will be inferred (e.g., "AR2020 Camera Sensor")
- Connection Type: `MIPI_CSI` (primary suggestion)
- Driver Status: `vendor` (onsemi-supplied driver)

**Multi-PDF Merge**:
- ✓ No duplicates (AR2020 only appears once)
- ✓ Component is associated with board CSI interface
- ✓ Validation shows compatibility between AR2020 and Jetson CSI

## Test Procedures

### 1. Web UI Test (Recommended for Visual Verification)

```bash
# Start server
cd server
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then:
1. Navigate to `http://localhost:8000`
2. Click "Upload PDFs" (or drag-drop both files)
3. Select PDFs:
   - `tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf`
   - `tests/AR2020.pdf`
4. Leave LLM model blank (uses heuristics)
5. Click "Upload & Extract"
6. Watch extraction progress:
   - Should see "Found X sections" for each PDF
   - Should see "Component discovered: AR2020" 
   - Should show final merge with board + components
7. Verify results:
   - Board tab shows Jetson Orin NX
   - Components tab shows AR2020
   - Validation (if enabled) shows MIPI_CSI connection

### 2. API Test (Programmatic)

```bash
cd tests

# Stream extraction events (SSE)
curl -s -X POST \
  -F "files=@Jetson_Orin_NX_DS-10712-001_v0.5.pdf" \
  -F "files=@AR2020.pdf" \
  http://localhost:8000/api/upload \
  -H "Accept: text/event-stream" | jq .
```

Expected SSE events:
```
data: {"type":"log","message":"📂 Processing 2 file(s)…"}
data: {"type":"log","message":"📄 File 1/2: Jetson_Orin_NX_DS-10712-001_v0.5.pdf"}
data: {"type":"component_found","ic_name":"AR2020",...}
data: {"type":"upload_done","board_name":"Nvidia Jetson Orin NX",...}
```

### 3. Python Direct Test

```python
import sys
import os

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from agents import librarian
import pdfplumber

def get_pdf_sections(path):
     sections = []
     with pdfplumber.open(path) as pdf:
         for i, page in enumerate(pdf.pages):
             text = page.extract_text() or ""
             if text.strip():
                 sections.append({
                     "heading": f"Page {i+1}",
                     "text": text,
                     "page_start": i+1,
                     "page_end": i+1
                 })
     return sections

# Extract Jetson board
sections_board = get_pdf_sections('Jetson_Orin_NX_DS-10712-001_v0.5.pdf')
hw_board, _, logs = librarian.run_sections(sections_board)
print("Board SoC:", hw_board.get('soc'))

# Extract AR2020 component
sections_camera = get_pdf_sections('AR2020.pdf')
hw_camera, _, logs = librarian.run_sections(sections_camera)

# Find components
comps = [p for p in hw_camera.get('peripherals', []) if p.get('is_component')]
print(f"Components found: {len(comps)}")
for comp in comps:
    print(f"  - {comp.get('name')}")

# Merge
merged = librarian.merge_hardware_maps([hw_board, hw_camera])
print(f"\nMerged board: {merged.get('soc')}")
print(f"Total components: {len([p for p in merged.get('peripherals', []) if p.get('is_component')])}")
```

## Verification Checklist

When testing, verify:

- [ ] **Board Detection**
  - [ ] SoC correctly identified as "Nvidia Jetson Orin NX"
  - [ ] Architecture is "arm64"
  - [ ] CPU core is "Cortex-A78AE"
  - [ ] RAM detected (8000+ MB)

- [ ] **Component Detection**
  - [ ] AR2020 is recognized as a component (not a peripheral)
  - [ ] Component type is "camera" or "camera_sensor"
  - [ ] IC name is "AR2020"
  - [ ] Connection type is "MIPI_CSI"

- [ ] **IC Database Matching**
  - [ ] AR2020 found in known ICs list
  - [ ] Driver status shows (mainline/vendor/backport/unknown)
  - [ ] Default connection (MIPI_CSI) matches expectations

- [ ] **Multi-PDF Merge**
  - [ ] No duplicate AR2020 entries in merged map
  - [ ] Component references board peripherals correctly
  - [ ] Final peripherals list includes both board interfaces and components

- [ ] **UI Display**
  - [ ] Board section shows Jetson specs
  - [ ] Components section lists AR2020
  - [ ] Validation (if enabled) shows compatibility warnings or confirmations
  - [ ] No error messages in extraction

## Known ICs Database

The system now includes both components in its database:

```python
_KNOWN_COMPONENTS = {
    "ar2020": ("camera_sensor", "mipi_csi"),
    "econ200": ("camera_module", "mipi_csi"),
    # ... 31 other ICs
}
```

And in kernel_scout driver database:

```python
("camera_sensor", "ar2020", "mipi_csi", {
    "module": "ar2020",
    "since": "v5.15",
    "status": "vendor",
}),
```

## Troubleshooting

**Extraction takes too long**:
- Default behavior requires LLM (Ollama/GPT/Claude)
- Heuristic-only mode works without LLM
- If no models available, set `model=""` in upload (uses heuristics)

**Component not detected**:
- Check if LLM is available (Ollama running? API keys set?)
- Try manual merge of extracted maps
- Heuristic detection should still find AR2020 and ECON200

**MIPI_CSI not suggested as connection**:
- Check ic_matcher.py has AR2020 with correct default
- Check AR2020.pdf contains CSI/MIPI keywords
- Connection inference uses both IC defaults and context

## Next Steps

After verifying basic extraction works:

1. **Validate Connections**: Use `/api/validate` endpoint to check component-to-board compatibility
2. **Generate Device Tree**: Use `/api/generate` to create Device Tree with both board and component
3. **Generate Snap**: Use `/api/snap` to create Gadget Snap with hardware declarations
4. **Test on Hardware**: Deploy generated snap to actual Jetson Orin NX with AR2020 camera

