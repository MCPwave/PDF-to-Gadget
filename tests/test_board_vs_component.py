"""
Test suite for board vs component PDF detection.

Tests the auto-detection logic for distinguishing between:
  - Board PDFs (contain SoC, have internal peripherals, registers, power rails)
  - Component PDFs (no SoC, just connectors and pinout info)
"""
import json
from server.agents.librarian import (
    classify_pdf_type,
    _detect_connection_type_from_pins as detect_connection_type_from_pins,
    _extract_connector_pins as extract_connector_pins,
    enrich_component_peripheral,
    enrich_hardware_map_for_type,
)


# ── Test fixtures ──────────────────────────────────────────────────────────────

BOARD_HARDWARE_MAP = {
    "board": "Raspberry Pi 4 Model B",
    "soc": "BCM2711",
    "arch": "arm64",
    "cpu_core": "Cortex-A72",
    "cpu_count": 4,
    "cpu_freq_mhz": 1500,
    "ram_mb": 4096,
    "peripherals": [
        {
            "id": "uart_0",
            "name": "UART0",
            "type": "uart",
            "bus": "UART0",
            "address": "0x7e201000",
            "description": "Primary UART interface",
            "voltage": "3.3V",
            "regulator": "vcc-3v3",
        },
        {
            "id": "i2c_1",
            "name": "I2C1",
            "type": "i2c",
            "bus": "I2C1",
            "address": "0x7e804000",
            "description": "I2C bus for peripherals",
            "voltage": "3.3V",
            "regulator": "vcc-3v3",
        },
    ],
    "power_rails": [
        {"name": "vcc-3v3", "voltage": "3.3V", "supplies": ["gpio", "uart", "i2c"]},
        {"name": "vcc-5v0", "voltage": "5V", "supplies": ["usb", "eth"]},
    ],
}

COMPONENT_HARDWARE_MAP = {
    "board": None,
    "soc": "Unknown SoC",
    "arch": "arm64",
    "cpu_core": None,
    "peripherals": [
        {
            "id": "csi_connector",
            "name": "MIPI CSI Camera Connector",
            "type": "mipi_csi",
            "bus": "CSI0",
            "address": "",
            "description": "Camera connector with pins: CSI_D0, CSI_D1, CSI_CLK, CSI_HS, CSI_VS, GND, VCC_3V3",
            "voltage": "3.3V",
            "regulator": "vcc-3v3",
        },
    ],
    "power_rails": [
        {"name": "vcc-3v3", "voltage": "3.3V", "supplies": []},
    ],
}

COMPONENT_I2C_MAP = {
    "board": None,
    "soc": "",
    "arch": "arm64",
    "cpu_core": "",
    "peripherals": [
        {
            "id": "i2c_sensor",
            "name": "I2C Temperature Sensor Module",
            "type": "i2c",
            "bus": "I2C_EXT",
            "address": "",
            "description": "Sensor module with I2C interface: SDA, SCL, INT, GND, VCC_3V3",
            "voltage": "3.3V",
            "regulator": "vcc-3v3",
        },
    ],
    "power_rails": [
        {"name": "vcc-3v3", "voltage": "3.3V", "supplies": []},
    ],
}


# ── Classification tests ────────────────────────────────────────────────────────

def test_classify_board():
    """Board with SoC should be classified as 'board'."""
    result = classify_pdf_type(BOARD_HARDWARE_MAP)
    assert result == "board", f"Expected 'board', got '{result}'"
    print("✓ test_classify_board passed")


def test_classify_component_no_soc():
    """Component with 'Unknown SoC' should be classified as 'component'."""
    result = classify_pdf_type(COMPONENT_HARDWARE_MAP)
    assert result == "component", f"Expected 'component', got '{result}'"
    print("✓ test_classify_component_no_soc passed")


def test_classify_component_empty_soc():
    """Component with empty SoC should be classified as 'component'."""
    result = classify_pdf_type(COMPONENT_I2C_MAP)
    assert result == "component", f"Expected 'component', got '{result}'"
    print("✓ test_classify_component_empty_soc passed")


def test_classify_no_soc_field():
    """Map with missing SoC field should be classified as 'component'."""
    hw_map = {"board": "Custom Module"}
    result = classify_pdf_type(hw_map)
    assert result == "component", f"Expected 'component', got '{result}'"
    print("✓ test_classify_no_soc_field passed")


# ── Connection type detection tests ────────────────────────────────────────────

def test_detect_mipi_csi():
    """Detect MIPI CSI from pin names."""
    pins = ["CSI_D0", "CSI_D1", "CSI_CLK", "CSI_HS", "CSI_VS", "GND"]
    result = detect_connection_type_from_pins(pins)
    assert result == "mipi_csi", f"Expected 'mipi_csi', got '{result}'"
    print("✓ test_detect_mipi_csi passed")


def test_detect_i2c():
    """Detect I2C from pin names."""
    pins = ["SDA", "SCL", "INT", "GND", "VCC"]
    result = detect_connection_type_from_pins(pins)
    assert result == "i2c", f"Expected 'i2c', got '{result}'"
    print("✓ test_detect_i2c passed")


def test_detect_spi():
    """Detect SPI from pin names."""
    pins = ["MOSI", "MISO", "CLK", "CS", "GND"]
    result = detect_connection_type_from_pins(pins)
    assert result == "spi", f"Expected 'spi', got '{result}'"
    print("✓ test_detect_spi passed")


def test_detect_usb():
    """Detect USB from pin names."""
    pins = ["DP", "DM", "VBUS", "GND"]
    result = detect_connection_type_from_pins(pins)
    assert result == "usb", f"Expected 'usb', got '{result}'"
    print("✓ test_detect_usb passed")


def test_detect_uart():
    """Detect UART from pin names."""
    pins = ["TX", "RX", "GND", "VCC"]
    result = detect_connection_type_from_pins(pins)
    assert result == "uart", f"Expected 'uart', got '{result}'"
    print("✓ test_detect_uart passed")


def test_detect_generic():
    """Unknown pin pattern should default to 'generic'."""
    pins = ["PIN1", "PIN2", "PIN3"]
    result = detect_connection_type_from_pins(pins)
    assert result == "generic", f"Expected 'generic', got '{result}'"
    print("✓ test_detect_generic passed")


# ── Pin extraction tests ───────────────────────────────────────────────────────

def test_extract_pins_from_description():
    """Extract pin names from peripheral description."""
    peripheral = {
        "id": "csi_0",
        "name": "Camera Connector",
        "description": "MIPI CSI camera interface with pins: CSI_D0, CSI_D1, CSI_CLK, GND, VCC_3V3",
        "bus": "CSI0",
    }
    pins = extract_connector_pins(peripheral)
    assert len(pins) > 0, "Should extract at least one pin"
    assert "CSI_D0" in pins or "CSI_CLK" in pins, f"Expected CSI pins, got {pins}"
    print(f"✓ test_extract_pins_from_description passed (pins: {pins})")


def test_extract_pins_fallback_to_bus():
    """Fallback to bus label if no pins found in description."""
    peripheral = {
        "id": "i2c_ext",
        "name": "I2C Module",
        "description": "External I2C interface",
        "bus": "I2C_EXT",
    }
    pins = extract_connector_pins(peripheral)
    assert len(pins) > 0, "Should fallback to bus label"
    print(f"✓ test_extract_pins_fallback_to_bus passed (pins: {pins})")


# ── Component enrichment tests ──────────────────────────────────────────────────

def test_enrich_component_peripheral():
    """Enrich peripheral with component-specific fields."""
    peripheral = {
        "id": "csi_0",
        "name": "Camera Connector",
        "type": "mipi_csi",
        "bus": "CSI0",
        "address": "0x12345678",
        "description": "MIPI CSI with pins: CSI_D0, CSI_D1, CSI_CLK, GND",
        "voltage": "3.3V",
        "regulator": "vcc-3v3",
    }
    enriched = enrich_component_peripheral(peripheral)
    
    assert enriched.get("is_component") is True, "Should have is_component=True"
    assert enriched.get("connection_type") == "mipi_csi", f"Wrong connection_type: {enriched.get('connection_type')}"
    assert len(enriched.get("connector_pins", [])) > 0, "Should extract connector_pins"
    assert "address" not in enriched, "Should remove address field"
    assert "irq" not in enriched, "Should remove irq field"
    print("✓ test_enrich_component_peripheral passed")


def test_enrich_hardware_map_component():
    """Enrich entire hardware map for component PDF."""
    enriched = enrich_hardware_map_for_type(COMPONENT_HARDWARE_MAP, pdf_type="component")
    
    assert enriched.get("pdf_type") == "component", "Should mark as component"
    assert len(enriched.get("peripherals", [])) > 0, "Should have peripherals"
    
    peripheral = enriched["peripherals"][0]
    assert peripheral.get("is_component") is True, "Peripheral should have is_component=True"
    assert "connection_type" in peripheral, "Peripheral should have connection_type"
    assert "connector_pins" in peripheral, "Peripheral should have connector_pins"
    
    print("✓ test_enrich_hardware_map_component passed")


def test_enrich_hardware_map_board():
    """Board PDFs should not be enriched with component fields."""
    enriched = enrich_hardware_map_for_type(BOARD_HARDWARE_MAP, pdf_type="board")
    
    assert enriched.get("pdf_type") == "board", "Should mark as board"
    
    # Board peripherals should not be modified
    for peripheral in enriched.get("peripherals", []):
        assert peripheral.get("is_component") != True, "Board peripheral should not have is_component=True"
        assert "connection_type" not in peripheral or peripheral.get("connection_type") == "generic", \
            "Board peripheral should not have connection_type"
    
    print("✓ test_enrich_hardware_map_board passed")


def test_enrich_auto_detect():
    """Auto-detect PDF type during enrichment."""
    # Should auto-detect as board
    board_enriched = enrich_hardware_map_for_type(BOARD_HARDWARE_MAP)
    assert board_enriched.get("pdf_type") == "board", "Should auto-detect as board"
    
    # Should auto-detect as component
    component_enriched = enrich_hardware_map_for_type(COMPONENT_HARDWARE_MAP)
    assert component_enriched.get("pdf_type") == "component", "Should auto-detect as component"
    
    print("✓ test_enrich_auto_detect passed")


# ── Integration tests ──────────────────────────────────────────────────────────

def test_full_workflow_board():
    """Complete workflow for board PDF."""
    # Classify
    pdf_type = classify_pdf_type(BOARD_HARDWARE_MAP)
    assert pdf_type == "board"
    
    # Enrich
    enriched = enrich_hardware_map_for_type(BOARD_HARDWARE_MAP, pdf_type=pdf_type)
    assert enriched["pdf_type"] == "board"
    assert len(enriched["peripherals"]) == 2
    assert all(p.get("address") for p in enriched["peripherals"]), "Board peripherals should have addresses"
    
    print("✓ test_full_workflow_board passed")


def test_full_workflow_component():
    """Complete workflow for component PDF."""
    # Classify
    pdf_type = classify_pdf_type(COMPONENT_HARDWARE_MAP)
    assert pdf_type == "component"
    
    # Enrich
    enriched = enrich_hardware_map_for_type(COMPONENT_HARDWARE_MAP, pdf_type=pdf_type)
    assert enriched["pdf_type"] == "component"
    
    peripheral = enriched["peripherals"][0]
    assert peripheral["is_component"] is True
    assert peripheral["connection_type"] == "mipi_csi"
    assert len(peripheral["connector_pins"]) > 0
    assert "address" not in peripheral
    
    print("✓ test_full_workflow_component passed")


def test_json_serializable():
    """Enriched maps should be JSON-serializable."""
    enriched_board = enrich_hardware_map_for_type(BOARD_HARDWARE_MAP)
    enriched_component = enrich_hardware_map_for_type(COMPONENT_HARDWARE_MAP)
    
    try:
        json.dumps(enriched_board)
        json.dumps(enriched_component)
        print("✓ test_json_serializable passed")
    except Exception as e:
        raise AssertionError(f"Failed to serialize enriched maps: {e}")


# ── Test runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*70)
    print("BOARD vs COMPONENT PDF Detection Tests")
    print("="*70 + "\n")
    
    # Classification tests
    print("Classification Tests:")
    test_classify_board()
    test_classify_component_no_soc()
    test_classify_component_empty_soc()
    test_classify_no_soc_field()
    
    # Connection type detection
    print("\nConnection Type Detection Tests:")
    test_detect_mipi_csi()
    test_detect_i2c()
    test_detect_spi()
    test_detect_usb()
    test_detect_uart()
    test_detect_generic()
    
    # Pin extraction
    print("\nPin Extraction Tests:")
    test_extract_pins_from_description()
    test_extract_pins_fallback_to_bus()
    
    # Component enrichment
    print("\nComponent Enrichment Tests:")
    test_enrich_component_peripheral()
    test_enrich_hardware_map_component()
    test_enrich_hardware_map_board()
    test_enrich_auto_detect()
    
    # Integration tests
    print("\nIntegration Tests:")
    test_full_workflow_board()
    test_full_workflow_component()
    test_json_serializable()
    
    print("\n" + "="*70)
    print("All tests passed! ✓")
    print("="*70 + "\n")
