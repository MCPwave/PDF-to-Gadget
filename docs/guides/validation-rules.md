# Multi-PDF Upload & Validation Endpoint Changes

## Summary

Updated FastAPI endpoints in `server/main.py` to support:
- **Multiple PDF uploads** with hardware map merging
- **Connection validation** with driver availability checking
- **Session management** with auto-cleanup for old sessions
- **SSE streaming** of validation conflicts and alternatives

## Detailed Changes

### 1. Imports & Dependencies

**Added:**
```python
import time  # For session timestamp tracking
from agents import bus_validator  # Connection validator
```

**Fixed:**
```python
# bus_validator.py: Changed absolute imports to relative imports
try:
    from kernel_scout import _lookup_db
except ImportError:
    from .kernel_scout import _lookup_db
```

---

### 2. Session Management

#### Enhanced Session Store
```python
_sessions: dict[str, dict] = {}
# Now includes: hw_map, sections, created_at, validation_report
```

#### New: Session Cleanup Function
```python
def _cleanup_old_sessions(max_age_seconds: int = 3600):
    """Remove sessions older than max_age_seconds (default 1 hour)."""
```

**Called:**
- At start of `/api/upload` to clean up before new upload
- Can be called periodically by scheduler in production

---

### 3. `/api/upload` Endpoint

#### Old Behavior
```python
@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),  # Single file
    model: str = Form(""),
    api_key: str = Form(""),
):
```

#### New Behavior
```python
@app.post("/api/upload")
async def upload_pdf(
    files: list[UploadFile] = File(...),  # Multiple files
    model: str = Form(""),
    api_key: str = Form(""),
):
```

#### New `_upload_stream()` Implementation

**Accepts:** `list[tuple[bytes, str]]` (file bytes + filenames)

**Process Flow:**
1. **Per-file extraction** (for each file):
   - Parse PDF sections (or plain text)
   - Log progress: "📄 File X/N: filename"
   - Extract hardware map with @librarian
   - Log section processing
   - Append to `all_maps` list

2. **Extraction summary**:
   - Count successful files and failures
   - Log: "📋 Extraction complete: N file(s) succeeded, M failed"

3. **Hardware map merging**:
   - Call `librarian.merge_hardware_maps(all_maps)`
   - Log: "✅ Maps merged: X peripherals, Y power rails"

4. **Session creation**:
   - Generate unique `session_id`
   - Store: `hw_map`, `created_at` timestamp, `validation_report=None`
   - Stream final `upload_done` event with merged map

**SSE Events:**
- `log`: Progress messages (file parsing, section extraction, etc.)
- `error`: File-specific errors (continues to next file)
- `upload_done`: Final event with session_id, board info, peripherals

---

### 4. New `/api/validate` Endpoint

**Purpose:** Validate a merged hardware map (called after upload)

```python
@app.post("/api/validate")
async def validate_session(req: ValidateRequest):
    """Validate the merged hardware map and return conflicts/alternatives."""
```

**Input:**
```python
class ValidateRequest(BaseModel):
    session_id: str
```

**Output:**
```python
{
    "valid": True,                    # Always true (warn-continue mode)
    "conflicts": [                    # Bus, power rail, driver issues
        {
            "type": "driver_unavailable",
            "bus_name": "I2C0",
            "peripheral_type": "camera",
            "message": "...",
            "alternatives": [         # Alternative connection types
                {
                    "connection_type": "usb",
                    "driver_status": "mainline",
                    "effort": "low"
                }
            ]
        }
    ],
    "merged_buses": {                 # Consolidated bus pins
        "I2C0": ["SDA", "SCL"],
        "SPI0": ["MOSI", "MISO", "CLK", "CS"]
    },
    "driver_summary": {               # Driver status counts
        "mainline": 5,
        "backport": 2,
        "vendor": 1,
        "unknown": 1
    }
}
```

**Stores:** Validation report in session for later retrieval

---

### 5. `/api/generate` Endpoint

#### Enhanced Signature
```python
class GenerateRequest(BaseModel):
    session_id: str
    selected_ids: list[str]
    alternatives: dict = {}  # NEW: Maps conflict ID to chosen alternative
```

#### New `_pipeline_stream()` Implementation

**Added Step: Connection Validation**

1. **@bus_validator step** (after loading hardware map):
   ```python
   # Stream validation progress
   yield event("🔗 @bus_validator — validating connections...")
   
   # Call validator
   validation_result = bus_validator.validate_connections([hw_map])
   
   # Stream conflict events
   for conflict in validation_result.get("conflicts", []):
       yield event(conflict_message, "conflict")
   ```

2. **Conflict Streaming**:
   - For `driver_unavailable` conflicts:
     ```
     ⚠️  CAMERA via I2C0 — ... | Alternatives: usb (mainline), hdmi (vendor)
     ```
   - For `bus_pin_mismatch`, `power_rail_mismatch`:
     ```
     ⚠️  I2C0 pin count differs: 2 vs 3 pins
     ```

3. **Driver Summary**:
   ```
   ✅ Driver availability: 5/9 mainline, 2 backport, 1 vendor
   ```

4. **Store Report**:
   - Save to `session["validation_report"]` for UI display

5. **Final Result**:
   - Includes `validation_report` in result payload (before DTS generation)

**SSE Events:**
- `log`: Validation progress + driver summary
- `conflict`: Each detected conflict with alternatives
- `error`: Validation or pipeline failures
- `result`: Final output with validation_report included

---

### 6. Error Handling

#### Upload Endpoint
```python
# Per-file error handling (continues to next file)
try:
    sections = _extract_pdf_sections(data)
except Exception as e:
    yield _event(f"PDF parse error: {e}", "error")
    failed_files.append(filename)
    continue

# Merge error (stops processing)
try:
    merged = librarian.merge_hardware_maps(all_maps)
except Exception as e:
    yield _event(f"Merge failed: {e}", "error")
    return
```

#### Generate Pipeline
```python
# Validation error (continues with defaults)
try:
    validation_result = bus_validator.validate_connections([hw_map])
except Exception as e:
    yield event(f"⚠️  Validation failed: {e}", "log")
    validation_result = {"valid": True, "conflicts": [], ...}
```

---

## Testing

Run endpoint test suite:
```bash
cd /home/capo02/work/cop1
python3 test_endpoints.py
```

**Tests Cover:**
1. ✅ Session storage with timestamps
2. ✅ Session cleanup (1 hour expiration)
3. ✅ Hardware map merging (2 maps → 1 merged)
4. ✅ Connection validation (buses, rails, drivers)
5. ✅ Validation report storage in sessions
6. ✅ SSE event formatting (log, conflict, error, upload_done, result)
7. ✅ Driver alternatives in conflict events

---

## API Examples

### Example: Upload Multiple PDFs
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "files=@board1.pdf" \
  -F "files=@board2.pdf" \
  -F "model=ollama_model_name" \
  -F "api_key=" \
  -H "Accept: text/event-stream"
```

**Response Stream:**
```
data: {"type": "log", "message": "📂 Processing 2 file(s)…"}
data: {"type": "log", "message": "📄 File 1/2: board1.pdf"}
data: {"type": "log", "message": "✅ Hardware map extracted: 5 peripherals"}
data: {"type": "log", "message": "📄 File 2/2: board2.pdf"}
data: {"type": "log", "message": "✅ Hardware map extracted: 3 peripherals"}
data: {"type": "log", "message": "✅ Maps merged: 8 peripherals, 4 power rails"}
data: {"type": "upload_done", "session_id": "...", "files_processed": 2, ...}
```

### Example: Validate Merged Map
```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...'}'
```

**Response:**
```json
{
  "valid": true,
  "conflicts": [
    {
      "type": "driver_unavailable",
      "peripheral_type": "camera",
      "bus_name": "CSI0",
      "message": "Camera via CSI0 has driver status: unknown",
      "alternatives": [
        {"connection_type": "usb", "driver_status": "mainline", "effort": "low"}
      ]
    }
  ],
  "driver_summary": {"mainline": 6, "backport": 1, "vendor": 0, "unknown": 2},
  "merged_buses": {"I2C0": ["SDA", "SCL"], "CSI0": ["CLK", "DATA0", "DATA1"]}
}
```

### Example: Generate Pipeline (with validation)
```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "selected_ids": ["p1", "p2"], "alternatives": {}}' \
  -H "Accept: text/event-stream"
```

**Response Stream:**
```
data: {"type": "log", "message": "🔗 @bus_validator — validating connections..."}
data: {"type": "conflict", "message": "⚠️  CAMERA via CSI0 — ... | Alternatives: usb (mainline)"}
data: {"type": "log", "message": "✅ Driver availability: 6/9 mainline, 1 backport, 2 vendor"}
data: {"type": "log", "message": "✅ Pinmux check passed..."}
data: {"type": "log", "message": "🏗️ @dt_architect — generating Device Tree..."}
...
data: {"type": "result", ..., "validation_report": {...}}
```

---

## Files Modified

1. **`server/main.py`** (Primary changes)
   - Added `time` import
   - Added `bus_validator` import
   - Enhanced session store structure
   - New `_cleanup_old_sessions()` function
   - Refactored `_upload_stream()` for multiple files + merging
   - Updated `/api/upload` endpoint
   - New `/api/validate` endpoint
   - Enhanced `/api/generate` + `_pipeline_stream()` with validation
   - Updated `GenerateRequest` to include `alternatives`

2. **`server/agents/bus_validator.py`** (Import fix)
   - Changed `from kernel_scout import _lookup_db` to try-except with relative import
   - Same for `alternative_connections`

3. **`test_endpoints.py`** (New test suite)
   - 7 test functions covering all new functionality
   - Verifies session management, merging, validation, SSE format

---

## Production Considerations

1. **Session Cleanup**: Current cleanup runs on each upload. For production:
   - Consider periodic scheduler (APScheduler) for background cleanup
   - Or increase max_age_seconds if sessions are valuable

2. **Concurrent Uploads**: FastAPI/Uvicorn handles concurrency, but _sessions dict is not thread-safe:
   - Add `threading.Lock()` for thread-safety in multi-worker setup
   - Or use Redis for distributed session storage

3. **Large Merges**: Merging many PDFs could consume memory:
   - Consider streaming/chunked approach for >10 PDFs
   - Monitor merged_map size and add warnings

4. **Validation Performance**: Bus validator runs on executor (CPU-bound):
   - Caching validation results recommended for same maps
   - Consider pre-validation in upload step

---

## Backwards Compatibility

**Breaking Changes:**
- `/api/upload` now requires `files` (list) instead of `file` (single)
  - UI must send `files[]=file1 files[]=file2`
- `GenerateRequest` now has optional `alternatives` dict (backward compatible)

**Non-breaking:**
- New endpoints (`/api/validate`) are optional
- Existing `/api/generate` still works with old requests (alternatives default to {})
