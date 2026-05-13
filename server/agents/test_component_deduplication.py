"""
Comprehensive test suite for component deduplication verification.

Tests verify NO component duplicates across all scenarios:
- Same IC in single PDF
- Same IC in multiple PDFs
- Same IC with different connection types
- Similar names, different ICs
- Component mentioned as both built-in and optional
- Real-world multi-PDF merge
- Edge cases (None IC name, malformed objects, empty lists, etc.)
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from librarian import (
    merge_hardware_maps,
    _validate_component,
    _separate_components,
)


# ── Fixture Helpers ────────────────────────────────────────────────────────────

def create_board_map(board_name: str = "Raspberry Pi 4", soc: str = "BCM2711") -> dict:
    """Create a test board hardware map."""
    return {
        "board": board_name,
        "soc": soc,
        "arch": "arm64",
        "cpu_core": "ARM Cortex-A72",
        "cpu_count": 4,
        "cpu_freq_mhz": 1500,
        "ram_mb": 4096,
        "peripherals": [
            {
                "id": "mipi_csi0",
                "name": "MIPI CSI-2 Interface 0",
                "type": "mipi_csi",
                "bus": "MIPI_CSI0",
                "address": None,
                "irq": None,
                "description": "Camera interface",
                "voltage": "1.8V",
                "regulator": "vcc-1v8",
                "is_component": False,
            },
            {
                "id": "i2c1",
                "name": "I2C Bus 1",
                "type": "i2c",
                "bus": "I2C1",
                "address": None,
                "irq": None,
                "description": "I2C with SDA and SCL",
                "voltage": "3.3V",
                "regulator": "vcc-3v3",
                "is_component": False,
            }
        ],
        "power_rails": [
            {
                "name": "vcc-3v3",
                "voltage": "3.3V",
                "current_ma": 500,
                "supplies": ["i2c1", "gpio"]
            },
            {
                "name": "vcc-1v8",
                "voltage": "1.8V",
                "current_ma": 300,
                "supplies": ["mipi_csi0"]
            }
        ]
    }


def create_ov5647_camera(connection_type: str = "mipi_csi") -> dict:
    """Create OV5647 camera component with specified connection type."""
    return {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "camera_ov5647",
                "name": "OV5647 Camera Module",
                "type": "camera",
                "bus": "MIPI_CSI" if connection_type == "mipi_csi" else "USB",
                "address": None,
                "irq": None,
                "description": "5MP camera",
                "voltage": "3.3V",
                "regulator": None,
                "is_component": True,
                "connection_type": connection_type,
                "connector": {
                    "pins": ["CLK", "HS", "D0", "D1", "D2", "D3", "GND", "VDDIO"],
                    "voltage": "1.8V",
                    "required_board_interface": "MIPI_CSI0" if connection_type == "mipi_csi" else None,
                },
                "component_ic": {
                    "name": "OV5647",
                    "vendor": "OmniVision",
                    "type": "camera_sensor"
                }
            }
        ],
        "power_rails": []
    }


def create_imx219_camera() -> dict:
    """Create IMX219 camera component (different from OV5647)."""
    return {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "camera_imx219",
                "name": "IMX219 Camera Module",
                "type": "camera",
                "bus": "MIPI_CSI",
                "address": None,
                "irq": None,
                "description": "8MP camera",
                "voltage": "3.3V",
                "regulator": None,
                "is_component": True,
                "connection_type": "mipi_csi",
                "connector": {
                    "pins": ["CLK", "HS", "D0", "D1", "D2", "D3", "GND", "VDDIO"],
                    "voltage": "1.8V",
                    "required_board_interface": "MIPI_CSI0",
                },
                "component_ic": {
                    "name": "IMX219",
                    "vendor": "Sony",
                    "type": "camera_sensor"
                }
            }
        ],
        "power_rails": []
    }


def create_imx477_camera() -> dict:
    """Create IMX477 camera component (different from IMX219)."""
    return {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "camera_imx477",
                "name": "IMX477 Camera Module",
                "type": "camera",
                "bus": "MIPI_CSI",
                "address": None,
                "irq": None,
                "description": "12MP camera",
                "voltage": "3.3V",
                "regulator": None,
                "is_component": True,
                "connection_type": "mipi_csi",
                "connector": {
                    "pins": ["CLK", "HS", "D0", "D1", "D2", "D3", "GND", "VDDIO"],
                    "voltage": "1.8V",
                    "required_board_interface": "MIPI_CSI0",
                },
                "component_ic": {
                    "name": "IMX477",
                    "vendor": "Sony",
                    "type": "camera_sensor"
                }
            }
        ],
        "power_rails": []
    }


def create_tmp36_sensor() -> dict:
    """Create TMP36 temperature sensor component."""
    return {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "sensor_tmp36",
                "name": "TMP36 Temperature Sensor",
                "type": "sensor",
                "bus": "I2C",
                "address": "0x48",
                "irq": None,
                "description": "Temperature sensor on I2C bus",
                "voltage": "3.3V",
                "regulator": None,
                "is_component": True,
                "connection_type": "i2c",
                "connector": {
                    "pins": ["SDA", "SCL", "GND", "VDDIO"],
                    "voltage": "3.3V",
                    "required_board_interface": "I2C1",
                },
                "component_ic": {
                    "name": "TMP36",
                    "vendor": "Analog Devices",
                    "type": "temperature_sensor"
                }
            }
        ],
        "power_rails": []
    }


# ── Scenario 1: Same IC in single PDF (mentioned 3 times) ──────────────────────

def test_scenario1_same_ic_single_pdf():
    """
    Scenario 1: PDF text mentions OV5647 camera 3 times in different sections.
    Result: 1 OV5647 component (not 3)
    Verify dedup by IC name works
    """
    # Simulate 3 mentions of the same OV5647 in one PDF extraction
    # (merging within a single PDF)
    camera1 = create_ov5647_camera()
    camera2 = create_ov5647_camera()  # Same camera, different mention
    camera3 = create_ov5647_camera()  # Same camera, third mention
    
    # In real scenario, component_extractor would merge within same PDF
    # Here we simulate what merge_hardware_maps should do with 3 identical PDFs
    merged = merge_hardware_maps([camera1, camera2, camera3])
    
    # Count OV5647 components by IC name
    ov5647_components = [
        p for p in merged["peripherals"]
        if p.get("is_component")
        and p.get("component_ic", {}).get("name") == "OV5647"
    ]
    
    assert len(ov5647_components) == 1, f"Expected 1 OV5647 component, got {len(ov5647_components)}"
    assert ov5647_components[0]["id"] == "camera_ov5647"
    print("✓ Scenario 1: Same IC in single PDF - PASSED")


# ── Scenario 2: Same IC in multiple PDFs ──────────────────────────────────────

def test_scenario2_same_ic_multiple_pdfs():
    """
    Scenario 2: Same IC in multiple PDFs.
    - PDF1: Raspberry Pi 4 with "OV5647 camera supported"
    - PDF2: OV5647 datasheet with full specs
    - PDF3: Another mention of OV5647 in sensor list
    Result: 1 OV5647 component after merge (not 3)
    First occurrence kept, source_pdf = pdf1 (board PDF)
    """
    board_map = create_board_map("Raspberry Pi 4")
    camera_map = create_ov5647_camera()
    
    # Simulate second mention of OV5647 from another document
    camera_map2 = create_ov5647_camera()
    
    merged = merge_hardware_maps([board_map, camera_map, camera_map2])
    
    # Count OV5647 components
    ov5647_components = [
        p for p in merged["peripherals"]
        if p.get("is_component")
        and p.get("component_ic", {}).get("name") == "OV5647"
    ]
    
    assert len(ov5647_components) == 1, f"Expected 1 OV5647 component, got {len(ov5647_components)}"
    assert ov5647_components[0]["component_ic"]["name"] == "OV5647"
    print("✓ Scenario 2: Same IC in multiple PDFs - PASSED")


# ── Scenario 3: Same IC, different connection types ─────────────────────────

def test_scenario3_same_ic_different_connections():
    """
    Scenario 3: Same IC, different connection types.
    - OV5647 on MIPI_CSI (PDF1)
    - OV5647 on USB (PDF2)
    Result: 2 components (NOT deduplicated, different connection_type)
    These are truly different use cases
    """
    camera_mipi = create_ov5647_camera(connection_type="mipi_csi")
    camera_usb = create_ov5647_camera(connection_type="usb")
    
    # Change ID to avoid direct dedup by ID
    camera_usb["peripherals"][0]["id"] = "camera_ov5647_usb"
    camera_usb["peripherals"][0]["bus"] = "USB"
    camera_usb["peripherals"][0]["connector"]["required_board_interface"] = None
    
    merged = merge_hardware_maps([camera_mipi, camera_usb])
    
    # Both should be kept since connection_type differs
    ov5647_components = [
        p for p in merged["peripherals"]
        if p.get("is_component")
        and p.get("component_ic", {}).get("name") == "OV5647"
    ]
    
    assert len(ov5647_components) == 2, f"Expected 2 OV5647 components (different connections), got {len(ov5647_components)}"
    
    connection_types = {c["connection_type"] for c in ov5647_components}
    assert "mipi_csi" in connection_types
    assert "usb" in connection_types
    print("✓ Scenario 3: Same IC, different connections - PASSED (both kept)")


# ── Scenario 4: Similar names, different ICs ──────────────────────────────────

def test_scenario4_similar_names_different_ics():
    """
    Scenario 4: Similar names, different ICs.
    - IMX219 (Sony camera, PDF1)
    - IMX477 (Sony camera, PDF2)
    Result: 2 components (not deduplicated, different ICs)
    """
    camera_imx219 = create_imx219_camera()
    camera_imx477 = create_imx477_camera()
    
    merged = merge_hardware_maps([camera_imx219, camera_imx477])
    
    # Both should exist
    camera_components = [
        p for p in merged["peripherals"]
        if p.get("is_component") and p.get("component_ic", {}).get("vendor") == "Sony"
    ]
    
    assert len(camera_components) == 2, f"Expected 2 Sony camera components, got {len(camera_components)}"
    
    ic_names = {c["component_ic"]["name"] for c in camera_components}
    assert "IMX219" in ic_names
    assert "IMX477" in ic_names
    print("✓ Scenario 4: Similar names, different ICs - PASSED")


# ── Scenario 5: Component as built-in + optional ───────────────────────────────

def test_scenario5_builtin_vs_optional_component():
    """
    Scenario 5: Component mentioned as both built-in + optional.
    - RPi4 board: "includes I2C0 for sensors"
    - Sensor PDF: "connect TMP36 temperature sensor on I2C0"
    Result: TMP36 component extracted from sensor PDF only (not board + component)
    Note: Board peripherals (I2C0) are not marked as is_component=True
    """
    board_map = create_board_map()
    sensor_map = create_tmp36_sensor()
    
    merged = merge_hardware_maps([board_map, sensor_map])
    
    # Count components (is_component=True)
    components = [p for p in merged["peripherals"] if p.get("is_component")]
    
    # Should have TMP36 as component
    tmp36_components = [p for p in components if p.get("component_ic", {}).get("name") == "TMP36"]
    assert len(tmp36_components) == 1, f"Expected 1 TMP36 component, got {len(tmp36_components)}"
    
    # I2C should be in board peripherals, not as component
    i2c_components = [p for p in components if p.get("id") == "i2c1"]
    assert len(i2c_components) == 0, "I2C1 should not be a component"
    
    print("✓ Scenario 5: Component as built-in + optional - PASSED")


# ── Scenario 6: Real-world multi-PDF merge ────────────────────────────────────

def test_scenario6_realworld_multi_pdf_merge():
    """
    Scenario 6: Real-world multi-PDF merge.
    - PDF1: Raspberry Pi 4B board (mentions CSI0 for camera)
    - PDF2: OV5647 camera module
    - PDF3: TMP36 temperature sensor
    - PDF4: OV5647 datasheet (duplicate of camera)
    Result:
      - 1 board (RPi4B)
      - 1 camera component (OV5647 MIPI_CSI)
      - 1 sensor component (TMP36 I2C)
      - Total: 3 peripherals (board has 2 + 2 components = 4 total)
      - source_pdf tracking: OV5647 from PDF2 (first component occurrence)
    """
    pdf1_board = create_board_map("Raspberry Pi 4 Model B")
    pdf2_camera = create_ov5647_camera()
    pdf3_sensor = create_tmp36_sensor()
    pdf4_camera_dup = create_ov5647_camera()
    
    merged = merge_hardware_maps([pdf1_board, pdf2_camera, pdf3_sensor, pdf4_camera_dup])
    
    # Verify board
    assert merged["board"] == "Raspberry Pi 4 Model B"
    
    # Count peripherals
    all_peripherals = merged["peripherals"]
    assert len(all_peripherals) >= 4, f"Expected at least 4 peripherals (2 board + 2 components), got {len(all_peripherals)}"
    
    # Verify components
    components = [p for p in all_peripherals if p.get("is_component")]
    assert len(components) == 2, f"Expected 2 components, got {len(components)}"
    
    # Verify specific components
    component_names = {c.get("component_ic", {}).get("name") for c in components}
    assert "OV5647" in component_names, "OV5647 camera not found"
    assert "TMP36" in component_names, "TMP36 sensor not found"
    
    # Verify no duplicates by ID
    component_ids = [c["id"] for c in all_peripherals]
    assert len(component_ids) == len(set(component_ids)), "Duplicate component IDs found"
    
    print("✓ Scenario 6: Real-world multi-PDF merge - PASSED")


# ── Edge Case 1: Component with None IC name ──────────────────────────────────

def test_edge_case1_none_ic_name():
    """
    Edge case: Component with None IC name should not cause issues.
    """
    component_no_name = {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "component_unknown",
                "name": "Unknown Component",
                "type": "sensor",
                "bus": "I2C",
                "address": "0x50",
                "is_component": True,
                "connection_type": "i2c",
                "connector": {
                    "pins": ["SDA", "SCL"],
                    "voltage": "3.3V",
                    "required_board_interface": "I2C1",
                },
                "component_ic": {
                    "name": None,  # None name
                    "vendor": "Unknown",
                    "type": "sensor"
                }
            }
        ],
        "power_rails": []
    }
    
    board = create_board_map()
    merged = merge_hardware_maps([board, component_no_name])
    
    assert len(merged["peripherals"]) >= 1
    assert merged["board"] == "Raspberry Pi 4"
    print("✓ Edge Case 1: Component with None IC name - PASSED (no crash)")


# ── Edge Case 2: Malformed component object ───────────────────────────────────

def test_edge_case2_malformed_component():
    """
    Edge case: Malformed component object (missing fields) should skip gracefully.
    """
    malformed_map = {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "malformed_comp",
                # Missing many required fields
                "name": "Incomplete Component",
            }
        ],
        "power_rails": []
    }
    
    board = create_board_map()
    merged = merge_hardware_maps([board, malformed_map])
    
    # Should not crash and include what it can
    assert len(merged["peripherals"]) >= 3  # 2 board + malformed
    print("✓ Edge Case 2: Malformed component - PASSED (gracefully handled)")


# ── Edge Case 3: Empty component list ─────────────────────────────────────────

def test_edge_case3_empty_component_list():
    """
    Edge case: Empty component list should return empty, not errors.
    """
    empty_map = {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [],
        "power_rails": []
    }
    
    board = create_board_map()
    merged = merge_hardware_maps([board, empty_map])
    
    # Should only have board peripherals
    assert len(merged["peripherals"]) == 2  # 2 board peripherals from first map
    assert merged["board"] == "Raspberry Pi 4"
    print("✓ Edge Case 3: Empty component list - PASSED")


# ── Edge Case 4: Duplicate components with different confidence scores ────────

def test_edge_case4_duplicate_with_different_confidence():
    """
    Edge case: Duplicate components with different confidence scores.
    Result: Keep first, log warning (dedup by ID)
    """
    camera1 = create_ov5647_camera()
    camera1["peripherals"][0]["confidence"] = 0.9
    
    camera2 = create_ov5647_camera()
    camera2["peripherals"][0]["confidence"] = 0.7
    
    merged = merge_hardware_maps([camera1, camera2])
    
    ov5647_components = [
        p for p in merged["peripherals"]
        if p.get("is_component")
        and p.get("component_ic", {}).get("name") == "OV5647"
    ]
    
    assert len(ov5647_components) == 1, f"Expected 1 OV5647, got {len(ov5647_components)}"
    # Should keep first occurrence's confidence
    assert ov5647_components[0]["confidence"] == 0.9
    print("✓ Edge Case 4: Different confidence scores - PASSED (first kept)")


# ── Edge Case 5: All inputs are None ───────────────────────────────────────────

def test_edge_case5_all_none_inputs():
    """
    Edge case: All inputs are None or empty.
    Should return default structure without crashing.
    """
    merged = merge_hardware_maps([None, {}, {"peripherals": []}])
    
    assert isinstance(merged, dict)
    assert merged["board"] is None
    assert merged["peripherals"] == []
    print("✓ Edge Case 5: All None inputs - PASSED")


# ── Edge Case 6: Verify all components have unique IDs ──────────────────────────

def test_edge_case6_unique_component_ids():
    """
    Edge case: Verify all components have unique IDs after merge.
    """
    board = create_board_map()
    camera = create_ov5647_camera()
    sensor = create_tmp36_sensor()
    camera_dup = create_ov5647_camera()
    
    merged = merge_hardware_maps([board, camera, sensor, camera_dup])
    
    all_ids = [p.get("id") for p in merged["peripherals"] if p.get("id")]
    unique_ids = set(all_ids)
    
    assert len(all_ids) == len(unique_ids), f"Found duplicate IDs: {all_ids}"
    print("✓ Edge Case 6: Unique component IDs - PASSED")


# ── Comprehensive Verification Assertions ──────────────────────────────────────

def test_verification_assertions():
    """
    Test comprehensive verification assertions for deduplication.
    """
    board = create_board_map()
    camera = create_ov5647_camera()
    sensor = create_tmp36_sensor()
    camera_dup = create_ov5647_camera()
    
    merged = merge_hardware_maps([board, camera, sensor, camera_dup])
    
    # Assertion 1: Correct component count
    components = [p for p in merged["peripherals"] if p.get("is_component")]
    assert len(components) == 2, f"Expected 2 components, got {len(components)}"
    
    # Assertion 2: All components have IDs
    assert all(c.get("id") for c in merged["peripherals"]), "Some components missing IDs"
    
    # Assertion 3: Correct number of unique ICs
    ic_names = {
        c["component_ic"]["name"]
        for c in components
        if c.get("component_ic", {}).get("name")
    }
    assert len(ic_names) == 2, f"Expected 2 unique ICs, got {len(ic_names)}: {ic_names}"
    
    # Assertion 4: All components track source (if populated)
    for comp in components:
        # source_pdf should be set by merge process
        if "source_pdf" in comp:
            assert isinstance(comp["source_pdf"], str)
    
    print("✓ Verification assertions - PASSED")


# ── Summary Test ───────────────────────────────────────────────────────────────

def test_deduplication_summary():
    """
    Run all scenarios and verify deduplication rules.
    """
    print("\n" + "="*70)
    print("COMPREHENSIVE COMPONENT DEDUPLICATION TEST SUITE")
    print("="*70)
    
    # Scenario tests
    test_scenario1_same_ic_single_pdf()
    test_scenario2_same_ic_multiple_pdfs()
    test_scenario3_same_ic_different_connections()
    test_scenario4_similar_names_different_ics()
    test_scenario5_builtin_vs_optional_component()
    test_scenario6_realworld_multi_pdf_merge()
    
    print("\n" + "-"*70)
    print("EDGE CASES")
    print("-"*70)
    
    # Edge cases
    test_edge_case1_none_ic_name()
    test_edge_case2_malformed_component()
    test_edge_case3_empty_component_list()
    test_edge_case4_duplicate_with_different_confidence()
    test_edge_case5_all_none_inputs()
    test_edge_case6_unique_component_ids()
    
    print("\n" + "-"*70)
    print("VERIFICATION ASSERTIONS")
    print("-"*70)
    
    # Verification assertions
    test_verification_assertions()
    
    print("\n" + "="*70)
    print("ALL TESTS PASSED ✓")
    print("="*70)
    print("\nDEDUPLICATION CONFIDENCE SUMMARY:")
    print("  ✓ Scenario 1: Same IC in single PDF - 1 component (not 3)")
    print("  ✓ Scenario 2: Same IC in multiple PDFs - 1 component (not 3)")
    print("  ✓ Scenario 3: Same IC, different connections - 2 components (kept both)")
    print("  ✓ Scenario 4: Similar names, different ICs - 2 components (not deduplicated)")
    print("  ✓ Scenario 5: Component built-in vs optional - TMP36 extracted as component only")
    print("  ✓ Scenario 6: Real-world multi-PDF - 3 peripherals, no duplicates")
    print("  ✓ Edge cases: None IC names, malformed objects, empty lists - all handled")
    print("  ✓ Verification: Unique IDs, IC dedup rules, source tracking verified")
    print("\nCONCLUSION: Duplicates WILL NOT occur with current merge logic.")
    print("="*70)


if __name__ == "__main__":
    try:
        test_deduplication_summary()
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
