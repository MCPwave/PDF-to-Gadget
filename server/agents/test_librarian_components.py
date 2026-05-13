"""
Tests for component schema extension in librarian.py
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from librarian import (
    merge_hardware_maps,
    _validate_component,
    _separate_components,
    _normalise_hw_map,
)


# ── Test Fixtures ──────────────────────────────────────────────────────────────

def create_board_map(board_name: str = "Raspberry Pi 4") -> dict:
    """Create a test board hardware map with MIPI_CSI0 interface."""
    return {
        "board": board_name,
        "soc": "BCM2711",
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
                "description": "Camera interface with CLK, HS, D0-D3",
                "voltage": "1.8V",
                "regulator": "vcc-1v8"
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
                "regulator": "vcc-3v3"
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


def create_camera_component() -> dict:
    """Create a test camera component (OV5647)."""
    return {
        "board": None,
        "soc": None,
        "arch": None,
        "peripherals": [
            {
                "id": "camera_ov5647",
                "name": "OV5647 Camera Module",
                "type": "camera",
                "bus": "MIPI_CSI",
                "address": None,
                "irq": None,
                "description": "5MP camera with MIPI CSI-2 interface",
                "voltage": "3.3V",
                "regulator": None,
                "is_component": True,
                "connection_type": "mipi_csi",
                "connector": {
                    "pins": ["CSI_D0", "CSI_D1", "CSI_D2", "CSI_D3", "CSI_CLK", "CSI_HS", "GND", "VDDIO"],
                    "voltage": "1.8V",
                    "required_board_interface": "MIPI_CSI0"
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


def create_temperature_sensor_component() -> dict:
    """Create a test temperature sensor component (I2C)."""
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
                    "required_board_interface": "I2C1"
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


# ── Component Validation Tests ─────────────────────────────────────────────────

def test_validate_component_valid():
    """Test validation passes for valid component."""
    board_buses = {"MIPI_CSI0", "I2C1", "I2C0"}
    component = create_camera_component()["peripherals"][0]
    
    is_valid, errors = _validate_component(component, board_buses)
    assert is_valid, f"Expected valid component, got errors: {errors}"
    assert len(errors) == 0


def test_validate_component_missing_connection_type():
    """Test validation fails when connection_type missing."""
    component = create_camera_component()["peripherals"][0]
    component.pop("connection_type")
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("connection_type" in err for err in errors)


def test_validate_component_invalid_connection_type():
    """Test validation fails for unknown connection_type."""
    component = create_camera_component()["peripherals"][0]
    component["connection_type"] = "invalid_connection"
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("unknown connection_type" in err for err in errors)


def test_validate_component_missing_connector():
    """Test validation fails when connector missing."""
    component = create_camera_component()["peripherals"][0]
    component.pop("connector")
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("missing connector info" in err for err in errors)


def test_validate_component_missing_connector_voltage():
    """Test validation fails when connector voltage missing."""
    component = create_camera_component()["peripherals"][0]
    component["connector"].pop("voltage")
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("connector missing voltage" in err for err in errors)


def test_validate_component_board_interface_not_found():
    """Test validation fails when required board interface doesn't exist."""
    component = create_camera_component()["peripherals"][0]
    component["connector"]["required_board_interface"] = "MIPI_CSI1"
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("required board interface" in err for err in errors)


def test_validate_component_missing_ic_info():
    """Test validation fails when component_ic missing."""
    component = create_camera_component()["peripherals"][0]
    component.pop("component_ic")
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("missing component_ic info" in err for err in errors)


def test_validate_component_invalid_ic_type():
    """Test validation fails for unknown IC type."""
    component = create_camera_component()["peripherals"][0]
    component["component_ic"]["type"] = "invalid_ic_type"
    
    board_buses = {"MIPI_CSI0"}
    is_valid, errors = _validate_component(component, board_buses)
    
    assert not is_valid
    assert any("unknown IC type" in err for err in errors)


def test_validate_non_component_skips_validation():
    """Test validation skips for non-component peripherals."""
    peripheral = {
        "id": "uart0",
        "name": "UART Interface",
        "type": "uart",
        "is_component": False  # Not a component
    }
    
    board_buses = set()
    is_valid, errors = _validate_component(peripheral, board_buses)
    
    assert is_valid
    assert len(errors) == 0


# ── Component Separation Tests ─────────────────────────────────────────────────

def test_separate_components_both_types():
    """Test separation of board peripherals and components."""
    peripherals = [
        {
            "id": "uart0",
            "is_component": False,
            "name": "UART0"
        },
        {
            "id": "camera_ov5647",
            "is_component": True,
            "name": "Camera"
        },
        {
            "id": "i2c0",
            "is_component": False,
            "name": "I2C0"
        },
        {
            "id": "temp_sensor",
            "is_component": True,
            "name": "Temperature Sensor"
        }
    ]
    
    board_perips, components = _separate_components(peripherals)
    
    assert len(board_perips) == 2
    assert len(components) == 2
    assert board_perips[0]["id"] == "uart0"
    assert board_perips[1]["id"] == "i2c0"
    assert components[0]["id"] == "camera_ov5647"
    assert components[1]["id"] == "temp_sensor"


def test_separate_components_only_board():
    """Test separation when only board peripherals exist."""
    peripherals = [
        {"id": "uart0", "is_component": False},
        {"id": "i2c0", "is_component": False}
    ]
    
    board_perips, components = _separate_components(peripherals)
    
    assert len(board_perips) == 2
    assert len(components) == 0


def test_separate_components_only_components():
    """Test separation when only components exist."""
    peripherals = [
        {"id": "camera", "is_component": True},
        {"id": "sensor", "is_component": True}
    ]
    
    board_perips, components = _separate_components(peripherals)
    
    assert len(board_perips) == 0
    assert len(components) == 2


def test_separate_components_default_false():
    """Test separation with default is_component=False."""
    peripherals = [
        {"id": "uart0"},  # No is_component field, defaults to False
        {"id": "camera", "is_component": True}
    ]
    
    board_perips, components = _separate_components(peripherals)
    
    assert len(board_perips) == 1
    assert len(components) == 1


# ── Merge with Components Tests ────────────────────────────────────────────────

def test_merge_board_and_components():
    """Test merging board map with component maps."""
    board_map = create_board_map("Raspberry Pi 4")
    camera_map = create_camera_component()
    sensor_map = create_temperature_sensor_component()
    
    merged = merge_hardware_maps([board_map, camera_map, sensor_map])
    
    # Should have all peripherals
    assert merged["board"] == "Raspberry Pi 4"
    assert len(merged["peripherals"]) >= 4  # 2 board + 2 components
    
    # Find components by ID
    component_ids = {p["id"] for p in merged["peripherals"] if p.get("is_component")}
    assert "camera_ov5647" in component_ids
    assert "sensor_tmp36" in component_ids


def test_merge_components_marked_with_source_pdf():
    """Test components get source_pdf field."""
    board_map = create_board_map()
    camera_map = create_camera_component()
    
    merged = merge_hardware_maps([board_map, camera_map])
    
    camera_periph = next(
        (p for p in merged["peripherals"] if p["id"] == "camera_ov5647"),
        None
    )
    assert camera_periph is not None
    assert camera_periph.get("source_pdf") == "pdf_2"


def test_merge_components_preserve_connector_info():
    """Test connector info preserved during merge."""
    board_map = create_board_map()
    camera_map = create_camera_component()
    
    merged = merge_hardware_maps([board_map, camera_map])
    
    camera_periph = next(
        (p for p in merged["peripherals"] if p["id"] == "camera_ov5647"),
        None
    )
    assert camera_periph is not None
    assert "connector" in camera_periph
    assert camera_periph["connector"]["voltage"] == "1.8V"
    assert camera_periph["connector"]["required_board_interface"] == "MIPI_CSI0"


def test_merge_duplicate_components_warning():
    """Test warning when same component appears in multiple maps."""
    board_map = create_board_map()
    camera_map1 = create_camera_component()
    camera_map2 = create_camera_component()
    
    merged = merge_hardware_maps([board_map, camera_map1, camera_map2])
    
    # Should only have one camera
    camera_count = sum(
        1 for p in merged["peripherals"]
        if p["id"] == "camera_ov5647"
    )
    assert camera_count == 1


def test_merge_normalizes_new_fields():
    """Test merged map normalized with component fields."""
    board_map = create_board_map()
    
    merged = merge_hardware_maps([board_map])
    normalized = _normalise_hw_map(merged)
    
    # All peripherals should have component fields after normalization
    for p in normalized["peripherals"]:
        assert "is_component" in p
        assert "connection_type" in p
        assert "source_pdf" in p


# ── Normalization Tests ────────────────────────────────────────────────────────

def test_normalise_adds_component_defaults():
    """Test _normalise_hw_map adds component field defaults."""
    hw_map = {
        "board": "Test",
        "peripherals": [
            {"id": "p1", "name": "Peripheral 1"},
            {
                "id": "comp1",
                "name": "Component 1",
                "is_component": True,
                "connection_type": "i2c"
            }
        ],
        "power_rails": []
    }
    
    normalized = _normalise_hw_map(hw_map)
    
    for p in normalized["peripherals"]:
        assert "is_component" in p
        assert "connection_type" in p
        assert "source_pdf" in p


def test_normalise_preserves_component_info():
    """Test _normalise_hw_map preserves component info."""
    hw_map = {
        "board": "Test",
        "peripherals": [
            {
                "id": "camera",
                "name": "Camera",
                "is_component": True,
                "connection_type": "mipi_csi",
                "connector": {
                    "pins": ["D0", "D1"],
                    "voltage": "1.8V",
                    "required_board_interface": "MIPI_CSI0"
                }
            }
        ],
        "power_rails": []
    }
    
    normalized = _normalise_hw_map(hw_map)
    
    camera = normalized["peripherals"][0]
    assert camera["is_component"] is True
    assert camera["connection_type"] == "mipi_csi"
    assert camera["connector"]["voltage"] == "1.8V"


# ── Integration Tests ──────────────────────────────────────────────────────────

def test_full_workflow_board_and_components():
    """Test full workflow: merge board with multiple components."""
    board_map = create_board_map("Raspberry Pi 4")
    camera_map = create_camera_component()
    sensor_map = create_temperature_sensor_component()
    
    # Merge all maps
    merged = merge_hardware_maps([board_map, camera_map, sensor_map])
    
    # Normalize
    normalized = _normalise_hw_map(merged)
    
    # Verify structure
    assert normalized["board"] == "Raspberry Pi 4"
    assert normalized["soc"] == "BCM2711"
    
    # Verify components are marked
    components = [p for p in normalized["peripherals"] if p.get("is_component")]
    assert len(components) == 2
    
    # Verify board peripherals are unmarked
    board_perips = [p for p in normalized["peripherals"] if not p.get("is_component")]
    assert len(board_perips) >= 2
    
    # Verify camera has required fields
    camera = next((p for p in components if p["id"] == "camera_ov5647"), None)
    assert camera is not None
    assert camera["connection_type"] == "mipi_csi"
    assert "connector" in camera
    assert "component_ic" in camera


def test_full_workflow_multiple_boards_and_components():
    """Test merging multiple boards with components."""
    board1 = create_board_map("Raspberry Pi 4")
    board2_map = {
        "board": "NVIDIA Jetson",
        "soc": "Tegra Xavier",
        "arch": "arm64",
        "peripherals": [
            {
                "id": "csi_camera0",
                "name": "CSI Camera Interface 0",
                "type": "camera",
                "bus": "CSI_CAMERA0",
                "voltage": "1.8V"
            }
        ],
        "power_rails": []
    }
    camera_map = create_camera_component()
    
    # First map is used for board metadata
    merged = merge_hardware_maps([board1, board2_map, camera_map])
    
    assert merged["board"] == "Raspberry Pi 4"
    assert merged["soc"] == "BCM2711"
    
    # All peripherals merged
    assert len(merged["peripherals"]) >= 4


# ── Run tests ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
