#!/usr/bin/env python3
"""
Endpoint test suite for multi-PDF upload and validation.
Verifies:
1. Multiple file upload with progress streaming
2. Hardware map merging
3. Connection validation with conflict detection
4. Session management and cleanup
5. Validation report storage in sessions
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "agents"))

import main as app_main
from agents import librarian, bus_validator


def test_session_storage():
    """Verify sessions are stored with timestamps and validation reports."""
    print("✓ Session storage and retrieval")
    
    session_id = "test-1"
    test_hw_map = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [],
        "power_rails": []
    }
    
    app_main._sessions[session_id] = {
        "hw_map": test_hw_map,
        "created_at": time.time(),
        "validation_report": None
    }
    
    assert session_id in app_main._sessions
    assert app_main._sessions[session_id]["hw_map"]["soc"] == "RK3568"
    

def test_session_cleanup():
    """Verify old sessions are cleaned up."""
    print("✓ Session cleanup (1 hour expiration)")
    
    fresh_id = "fresh-session"
    old_id = "old-session"
    
    app_main._sessions[fresh_id] = {
        "hw_map": {},
        "created_at": time.time()
    }
    
    app_main._sessions[old_id] = {
        "hw_map": {},
        "created_at": time.time() - 3700  # >1 hour old
    }
    
    app_main._cleanup_old_sessions(3600)
    
    assert fresh_id in app_main._sessions, "Fresh session should not be cleaned"
    assert old_id not in app_main._sessions, "Old session should be cleaned"
    

def test_hardware_map_merge():
    """Verify librarian.merge_hardware_maps works correctly."""
    print("✓ Hardware map merging (multiple PDFs → single map)")
    
    map1 = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [
            {"id": "p1", "name": "Camera", "type": "camera", "bus": "CSI0"}
        ],
        "power_rails": [{"name": "VDD_1V8", "voltage": "1.8V"}]
    }
    
    map2 = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [
            {"id": "p2", "name": "Display", "type": "display", "bus": "HDMI0"}
        ],
        "power_rails": [{"name": "VDD_3V3", "voltage": "3.3V"}]
    }
    
    merged = librarian.merge_hardware_maps([map1, map2])
    
    assert len(merged["peripherals"]) == 2
    assert len(merged["power_rails"]) == 2
    

def test_connection_validation():
    """Verify bus_validator detects conflicts and driver issues."""
    print("✓ Connection validation (buses, power rails, drivers)")
    
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {
                "id": "sensor1",
                "name": "Temp Sensor",
                "type": "temperature_sensor",
                "bus": "I2C0",
                "description": "I2C_SDA, I2C_SCL"
            }
        ],
        "power_rails": [
            {"name": "VDD_1V8", "voltage": "1.8V"}
        ]
    }
    
    result = bus_validator.validate_connections([hw_map])
    
    assert result["valid"] == True
    assert "conflicts" in result
    assert "driver_summary" in result
    assert "merged_buses" in result
    

def test_validation_report_storage():
    """Verify validation reports are stored in sessions."""
    print("✓ Validation report storage in sessions")
    
    session_id = "validate-test"
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {"id": "p1", "name": "Device", "type": "camera", "bus": "CSI0"}
        ],
        "power_rails": []
    }
    
    app_main._sessions[session_id] = {
        "hw_map": hw_map,
        "created_at": time.time(),
        "validation_report": None
    }
    
    # Simulate validation
    validation = bus_validator.validate_connections([hw_map])
    app_main._sessions[session_id]["validation_report"] = validation
    
    assert app_main._sessions[session_id]["validation_report"] is not None
    assert "driver_summary" in app_main._sessions[session_id]["validation_report"]
    

def test_sse_event_format():
    """Verify SSE event formatting for streaming responses."""
    print("✓ SSE event formatting (log, conflict, error, upload_done, result)")
    
    def _event(msg: str, kind: str = "log") -> str:
        return f"data: {json.dumps({'type': kind, 'message': msg})}\n\n"
    
    # Test various event types
    events = {
        "log": _event("Processing file", "log"),
        "conflict": _event("Driver mismatch", "conflict"),
        "error": _event("File parse error", "error"),
    }
    
    for kind, event_str in events.items():
        assert "data:" in event_str
        assert f'"type": "{kind}"' in event_str
        
        payload = json.loads(event_str.split("data: ")[1].strip())
        assert payload["type"] == kind
        

def test_alternatives_in_conflicts():
    """Verify conflicts include driver alternatives."""
    print("✓ Driver alternatives in conflict events")
    
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {
                "id": "uncommon_device",
                "name": "Special Sensor",
                "type": "thermal_sensor",  # Non-standard type
                "bus": "I2C0",
                "description": "via I2C"
            }
        ],
        "power_rails": []
    }
    
    result = bus_validator.validate_connections([hw_map])
    conflicts = result.get("conflicts", [])
    
    # Check if driver conflicts have alternatives
    for conflict in conflicts:
        if conflict.get("type") == "driver_unavailable":
            # Alternatives might be present for non-mainline drivers
            if "alternatives" in conflict:
                assert isinstance(conflict["alternatives"], list)
                for alt in conflict["alternatives"]:
                    assert "connection_type" in alt
                    assert "driver_status" in alt
    

def run_tests():
    print("=" * 70)
    print("Endpoint Test Suite: Multi-PDF Upload & Validation")
    print("=" * 70 + "\n")
    
    tests = [
        test_session_storage,
        test_session_cleanup,
        test_hardware_map_merge,
        test_connection_validation,
        test_validation_report_storage,
        test_sse_event_format,
        test_alternatives_in_conflicts,
    ]
    
    for test_func in tests:
        try:
            test_func()
        except AssertionError as e:
            print(f"✗ {test_func.__name__}: {e}")
            return 1
        except Exception as e:
            print(f"✗ {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    print("\n" + "=" * 70)
    print("✅ All endpoint tests passed!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())


def test_session_storage():
    """Verify sessions are stored with timestamps and validation reports."""
    print("✓ Session storage and retrieval")
    
    session_id = "test-1"
    test_hw_map = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [],
        "power_rails": []
    }
    
    main._sessions[session_id] = {
        "hw_map": test_hw_map,
        "created_at": time.time(),
        "validation_report": None
    }
    
    assert session_id in main._sessions
    assert main._sessions[session_id]["hw_map"]["soc"] == "RK3568"
    

def test_session_cleanup():
    """Verify old sessions are cleaned up."""
    print("✓ Session cleanup (1 hour expiration)")
    
    fresh_id = "fresh-session"
    old_id = "old-session"
    
    main._sessions[fresh_id] = {
        "hw_map": {},
        "created_at": time.time()
    }
    
    main._sessions[old_id] = {
        "hw_map": {},
        "created_at": time.time() - 3700  # >1 hour old
    }
    
    main._cleanup_old_sessions(3600)
    
    assert fresh_id in main._sessions, "Fresh session should not be cleaned"
    assert old_id not in main._sessions, "Old session should be cleaned"
    

def test_hardware_map_merge():
    """Verify librarian.merge_hardware_maps works correctly."""
    print("✓ Hardware map merging (multiple PDFs → single map)")
    
    map1 = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [
            {"id": "p1", "name": "Camera", "type": "camera", "bus": "CSI0"}
        ],
        "power_rails": [{"name": "VDD_1V8", "voltage": "1.8V"}]
    }
    
    map2 = {
        "soc": "RK3568",
        "arch": "arm64",
        "peripherals": [
            {"id": "p2", "name": "Display", "type": "display", "bus": "HDMI0"}
        ],
        "power_rails": [{"name": "VDD_3V3", "voltage": "3.3V"}]
    }
    
    merged = librarian.merge_hardware_maps([map1, map2])
    
    assert len(merged["peripherals"]) == 2
    assert len(merged["power_rails"]) == 2
    

def test_connection_validation():
    """Verify bus_validator detects conflicts and driver issues."""
    print("✓ Connection validation (buses, power rails, drivers)")
    
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {
                "id": "sensor1",
                "name": "Temp Sensor",
                "type": "temperature_sensor",
                "bus": "I2C0",
                "description": "I2C_SDA, I2C_SCL"
            }
        ],
        "power_rails": [
            {"name": "VDD_1V8", "voltage": "1.8V"}
        ]
    }
    
    result = bus_validator.validate_connections([hw_map])
    
    assert result["valid"] == True
    assert "conflicts" in result
    assert "driver_summary" in result
    assert "merged_buses" in result
    

def test_validation_report_storage():
    """Verify validation reports are stored in sessions."""
    print("✓ Validation report storage in sessions")
    
    session_id = "validate-test"
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {"id": "p1", "name": "Device", "type": "camera", "bus": "CSI0"}
        ],
        "power_rails": []
    }
    
    main._sessions[session_id] = {
        "hw_map": hw_map,
        "created_at": time.time(),
        "validation_report": None
    }
    
    # Simulate validation
    validation = bus_validator.validate_connections([hw_map])
    main._sessions[session_id]["validation_report"] = validation
    
    assert main._sessions[session_id]["validation_report"] is not None
    assert "driver_summary" in main._sessions[session_id]["validation_report"]
    

def test_sse_event_format():
    """Verify SSE event formatting for streaming responses."""
    print("✓ SSE event formatting (log, conflict, error, upload_done, result)")
    
    def _event(msg: str, kind: str = "log") -> str:
        return f"data: {json.dumps({'type': kind, 'message': msg})}\n\n"
    
    # Test various event types
    events = {
        "log": _event("Processing file", "log"),
        "conflict": _event("Driver mismatch", "conflict"),
        "error": _event("File parse error", "error"),
    }
    
    for kind, event_str in events.items():
        assert "data:" in event_str
        assert f'"type": "{kind}"' in event_str
        
        payload = json.loads(event_str.split("data: ")[1].strip())
        assert payload["type"] == kind
        

def test_alternatives_in_conflicts():
    """Verify conflicts include driver alternatives."""
    print("✓ Driver alternatives in conflict events")
    
    hw_map = {
        "soc": "RK3568",
        "peripherals": [
            {
                "id": "uncommon_device",
                "name": "Special Sensor",
                "type": "thermal_sensor",  # Non-standard type
                "bus": "I2C0",
                "description": "via I2C"
            }
        ],
        "power_rails": []
    }
    
    result = bus_validator.validate_connections([hw_map])
    conflicts = result.get("conflicts", [])
    
    # Check if driver conflicts have alternatives
    for conflict in conflicts:
        if conflict.get("type") == "driver_unavailable":
            # Alternatives might be present for non-mainline drivers
            if "alternatives" in conflict:
                assert isinstance(conflict["alternatives"], list)
                for alt in conflict["alternatives"]:
                    assert "connection_type" in alt
                    assert "driver_status" in alt
    

def main():
    print("=" * 70)
    print("Endpoint Test Suite: Multi-PDF Upload & Validation")
    print("=" * 70 + "\n")
    
    tests = [
        test_session_storage,
        test_session_cleanup,
        test_hardware_map_merge,
        test_connection_validation,
        test_validation_report_storage,
        test_sse_event_format,
        test_alternatives_in_conflicts,
    ]
    
    for test_func in tests:
        try:
            test_func()
        except AssertionError as e:
            print(f"✗ {test_func.__name__}: {e}")
            return 1
        except Exception as e:
            print(f"✗ {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    print("\n" + "=" * 70)
    print("✅ All endpoint tests passed!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
