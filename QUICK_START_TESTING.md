# Quick Start: Testing PDF Extraction

## 🚀 Ready to Test

Two production datasheets are available for testing:

```
tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf  (Board: NVIDIA Jetson Orin NX)
tests/AR2020.pdf                             (Component: onsemi AR2020 camera sensor)
```

## ⚡ 60-Second Test

```bash
# 1. Start server
cd server
uvicorn main:app --host 0.0.0.0 --port 8000

# 2. Open browser
open http://localhost:8000

# 3. Upload both PDFs
# Click "Upload PDFs" → select both files → "Upload & Extract"

# 4. Watch results
# Should see: Jetson Orin NX (board) + AR2020 (component)
```

## 📋 What to Expect

**Board Detection**:
- Name: `Nvidia Jetson Orin NX`
- CPU: `Cortex-A78AE` (arm64)
- RAM: `8000-16000 MB`

**Component Detection**:
- Type: `camera_sensor`
- IC: `AR2020` ← newly added to database
- Connection: `MIPI_CSI` ← recommended for 20MP sensor

**Merge Result**:
- ✓ One board + one component (no duplicates)
- ✓ AR2020 validated against Jetson CSI interface

## 📖 Full Documentation

For detailed testing procedures, see:

- **`TESTING_SUMMARY.md`** — Overview of test setup
- **`docs/TEST_GUIDE.md`** — 3 test methods (UI, API, Python)

## ✅ Verification

After uploading both PDFs, verify:

```
Board:
  ☐ SoC: "Nvidia Jetson Orin NX"
  ☐ CPU: "Cortex-A78AE"
  ☐ Architecture: "arm64"

Component:
  ☐ Found: "AR2020"
  ☐ Type: "camera_sensor"
  ☐ Connection: "MIPI_CSI"
```

All checked = ✅ Test passed

---

**Status**: ✅ Ready  
**Test Files**: 2 (board + component)  
**Known ICs**: 32 (including AR2020)  
**Expected Time**: 2-5 minutes per upload
