"""
Tests for component_validator.py — component connection validation.
Uses unittest framework (no pytest required).
"""
import unittest
from component_validator import (
    validate_component_connections,
    _parse_voltage,
    _voltages_compatible,
    _find_board_interface,
    _get_interface_type,
    _get_connection_alternatives,
)


# ─── Test fixtures ────────────────────────────────────────────────────────────

def create_rpi4_board_map() -> dict:
    """Create a Raspberry Pi 4 board map with common interfaces."""
    return {
        "soc": "BCM2711",
        "board": "Raspberry Pi 4 Model B",
        "arch": "arm64",
        "peripherals": [
            {
                "id": "mipi_csi0",
                "name": "MIPI CSI Camera Interface 0",
                "type": "mipi_csi",
                "bus": "MIPI_CSI0",
                "voltage": "1.8V",
                "description": "Primary camera interface"
            },
            {
                "id": "mipi_dsi0",
                "name": "MIPI DSI Display Interface 0",
                "type": "mipi_dsi",
                "bus": "MIPI_DSI0",
                "voltage": "1.2V",
                "description": "Primary display interface"
            },
            {
                "id": "i2c1",
                "name": "I2C Bus 1",
                "type": "i2c",
                "bus": "I2C1",
                "voltage": "3.3V",
                "description": "General purpose I2C"
            },
            {
                "id": "gpio",
                "name": "GPIO",
                "type": "gpio",
                "bus": "GPIO",
                "voltage": "3.3V",
                "description": "General purpose I/O"
            }
        ],
        "power_rails": []
    }


def create_ov5647_camera_component() -> dict:
    """Create OV5647 camera component compatible with Raspberry Pi 4."""
    return {
        "id": "camera_ov5647",
        "name": "OV5647 Camera Module",
        "type": "camera",
        "bus": "MIPI_CSI",
        "voltage": "3.3V",
        "is_component": True,
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


def create_display_component() -> dict:
    """Create HDMI display component (incompatible with DSI interface)."""
    return {
        "id": "display_hdmi",
        "name": "HDMI Display",
        "type": "display",
        "bus": "HDMI",
        "voltage": "5V",
        "is_component": True,
        "connector": {
            "pins": ["HDMI_D0", "HDMI_D1", "HDMI_CLK"],
            "voltage": "5V",
            "required_board_interface": "MIPI_DSI0"  # Intentional mismatch
        },
        "component_ic": {
            "name": "GENERIC_HDMI",
            "vendor": "Generic",
            "type": "display"
        }
    }


def create_unknown_camera() -> dict:
    """Create camera with unknown/nonexistent driver."""
    return {
        "id": "camera_unknown",
        "name": "Mythical Camera",
        "type": "mythical_device",  # This type won't match any driver
        "bus": "MIPI_CSI",
        "voltage": "3.3V",
        "is_component": True,
        "connector": {
            "pins": ["CSI_D0"],
            "voltage": "1.8V",
            "required_board_interface": "MIPI_CSI0"
        },
        "component_ic": {
            "name": "MYTHICAL9000",
            "vendor": "FakeVendor",
            "type": "mythical_ic_type"  # This type won't match any driver
        }
    }


def create_missing_interface_component() -> dict:
    """Create component requiring non-existent interface."""
    return {
        "id": "camera_pcie",
        "name": "PCIe Camera",
        "type": "camera",
        "bus": "PCIE",
        "voltage": "3.3V",
        "is_component": True,
        "connector": {
            "pins": ["PCIE_D0", "PCIE_D1"],
            "voltage": "3.3V",
            "required_board_interface": "PCIE_X4"  # RPi4 doesn't have this
        },
        "component_ic": {
            "name": "PCIE_CAM",
            "vendor": "FakeVendor",
            "type": "camera_sensor"
        }
    }


# ─── Unit tests ────────────────────────────────────────────────────────────────

class TestParseVoltage(unittest.TestCase):
    """Tests for voltage parsing."""
    
    def test_parse_3v3(self):
        self.assertEqual(_parse_voltage("3.3V"), 3.3)
    
    def test_parse_1v8(self):
        self.assertEqual(_parse_voltage("1.8V"), 1.8)
    
    def test_parse_5v(self):
        self.assertEqual(_parse_voltage("5V"), 5.0)
    
    def test_parse_5v_lowercase(self):
        self.assertEqual(_parse_voltage("5v"), 5.0)
    
    def test_parse_with_space(self):
        self.assertEqual(_parse_voltage("3.3 V"), 3.3)
    
    def test_parse_invalid_returns_none(self):
        self.assertIsNone(_parse_voltage("invalid"))
    
    def test_parse_empty_returns_none(self):
        self.assertIsNone(_parse_voltage(""))


class TestVoltagesCompatible(unittest.TestCase):
    """Tests for voltage compatibility checking."""
    
    def test_exact_match(self):
        self.assertTrue(_voltages_compatible("3.3V", "3.3V"))
    
    def test_1v8_match(self):
        self.assertTrue(_voltages_compatible("1.8V", "1.8V"))
    
    def test_within_tolerance(self):
        # Default tolerance is 0.1V
        self.assertTrue(_voltages_compatible("3.3V", "3.2V"))  # 0.1V difference
    
    def test_outside_tolerance(self):
        # 3.3V vs 5V is 1.7V difference > 0.1V
        self.assertFalse(_voltages_compatible("3.3V", "5V"))
    
    def test_custom_tolerance(self):
        # With 2.0V tolerance, 3.3V and 5V should be compatible
        self.assertTrue(_voltages_compatible("3.3V", "5V", tolerance=2.0))
    
    def test_invalid_voltages(self):
        self.assertFalse(_voltages_compatible("invalid", "3.3V"))
        self.assertFalse(_voltages_compatible("3.3V", "invalid"))


class TestFindBoardInterface(unittest.TestCase):
    """Tests for finding board interfaces."""
    
    def test_find_by_bus_name(self):
        board = create_rpi4_board_map()
        interface = _find_board_interface(board, "MIPI_CSI0")
        self.assertIsNotNone(interface)
        self.assertEqual(interface["bus"], "MIPI_CSI0")
    
    def test_find_by_id(self):
        board = create_rpi4_board_map()
        interface = _find_board_interface(board, "mipi_csi0")
        self.assertIsNotNone(interface)
        self.assertEqual(interface["id"], "mipi_csi0")
    
    def test_not_found(self):
        board = create_rpi4_board_map()
        interface = _find_board_interface(board, "NONEXISTENT")
        self.assertIsNone(interface)
    
    def test_empty_board_map(self):
        board = {"peripherals": []}
        interface = _find_board_interface(board, "MIPI_CSI0")
        self.assertIsNone(interface)


class TestGetInterfaceType(unittest.TestCase):
    """Tests for extracting interface type from name."""
    
    def test_mipi_csi0(self):
        self.assertEqual(_get_interface_type("MIPI_CSI0"), "mipi_csi")
    
    def test_i2c0(self):
        self.assertEqual(_get_interface_type("I2C0"), "i2c")
    
    def test_spi1(self):
        self.assertEqual(_get_interface_type("SPI1"), "spi")
    
    def test_mipi_dsi0(self):
        self.assertEqual(_get_interface_type("MIPI_DSI0"), "mipi_dsi")
    
    def test_empty_returns_unknown(self):
        self.assertEqual(_get_interface_type(""), "unknown")
    
    def test_none_returns_unknown(self):
        self.assertEqual(_get_interface_type(None), "unknown")


# ─── Integration tests ─────────────────────────────────────────────────────────

class TestValidateComponentConnections(unittest.TestCase):
    """Tests for the main validation function."""
    
    def test_ok_status_rpi4_ov5647(self):
        """Test successful validation: RPi4 + OV5647 camera."""
        board = create_rpi4_board_map()
        components = [create_ov5647_camera_component()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        self.assertEqual(status["component_id"], "camera_ov5647")
        self.assertEqual(status["status"], "OK")
        self.assertEqual(status["drivers"]["ic_driver"]["status"], "mainline")
        self.assertEqual(status["drivers"]["interface_driver"]["status"], "mainline")
        
        summary = result["summary"]
        self.assertEqual(summary["total_components"], 1)
        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["warnings"], 0)
    
    def test_no_interface_status(self):
        """Test validation with missing interface."""
        board = create_rpi4_board_map()
        components = [create_missing_interface_component()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        self.assertEqual(status["component_id"], "camera_pcie")
        self.assertEqual(status["status"], "NO_INTERFACE")
        self.assertIn("PCIE_X4", status["message"])
        self.assertGreater(len(status["alternatives"]), 0)  # Should suggest alternatives
        
        summary = result["summary"]
        self.assertEqual(summary["warnings"], 1)
    
    def test_mismatch_status_voltage(self):
        """Test validation with voltage mismatch."""
        board = create_rpi4_board_map()
        components = [create_display_component()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        self.assertEqual(status["component_id"], "display_hdmi")
        self.assertEqual(status["status"], "MISMATCH")
        self.assertIn("Voltage mismatch", status["message"])
        
        summary = result["summary"]
        self.assertEqual(summary["warnings"], 1)
    
    def test_no_driver_status(self):
        """Test validation with unknown/missing driver."""
        board = create_rpi4_board_map()
        components = [create_unknown_camera()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        self.assertEqual(status["component_id"], "camera_unknown")
        self.assertEqual(status["status"], "NO_DRIVER")
        self.assertIn("No driver found", status["message"])
        
        summary = result["summary"]
        self.assertEqual(summary["warnings"], 1)
    
    def test_multiple_components(self):
        """Test validation with multiple components."""
        board = create_rpi4_board_map()
        components = [
            create_ov5647_camera_component(),
            create_missing_interface_component(),
            create_unknown_camera()
        ]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 3)
        
        summary = result["summary"]
        self.assertEqual(summary["total_components"], 3)
        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["warnings"], 2)
    
    def test_empty_components_list(self):
        """Test validation with empty components list."""
        board = create_rpi4_board_map()
        components = []
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["component_status"], [])
        self.assertEqual(result["summary"]["total_components"], 0)
        self.assertEqual(result["summary"]["ok"], 0)
    
    def test_component_missing_connector(self):
        """Test component with missing connector info."""
        board = create_rpi4_board_map()
        component = create_ov5647_camera_component()
        component.pop("connector")
        components = [component]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        self.assertEqual(status["status"], "MISMATCH")
        self.assertIn("missing required_board_interface", status["message"])
    
    def test_component_missing_ic_info(self):
        """Test component with missing IC info but valid interface."""
        board = create_rpi4_board_map()
        component = create_ov5647_camera_component()
        component.pop("component_ic")
        components = [component]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        
        status = result["component_status"][0]
        # Should still check by component type
        self.assertIn(status["status"], ["OK", "NO_DRIVER"])


class TestAlternativeConnections(unittest.TestCase):
    """Tests for alternative connection suggestions."""
    
    def test_camera_alternatives(self):
        """Test that camera provides USB and DSI alternatives."""
        alternatives = _get_connection_alternatives("camera", "BCM2711")
        
        self.assertGreater(len(alternatives), 0)
        connection_types = [alt["connection_type"] for alt in alternatives]
        self.assertTrue("usb" in connection_types or "mipi_dsi" in connection_types)
    
    def test_display_alternatives(self):
        """Test that display provides HDMI alternatives."""
        alternatives = _get_connection_alternatives("display", "BCM2711")
        
        self.assertGreater(len(alternatives), 0)
        connection_types = [alt["connection_type"] for alt in alternatives]
        self.assertTrue("hdmi" in connection_types or "displayport" in connection_types)
    
    def test_unknown_type_no_alternatives(self):
        """Test that unknown types have no alternatives."""
        alternatives = _get_connection_alternatives("mythical_thing", "BCM2711")
        
        self.assertEqual(alternatives, [])
    
    def test_alternatives_have_driver_status(self):
        """Test that alternatives include driver status."""
        alternatives = _get_connection_alternatives("camera", "BCM2711")
        
        self.assertGreater(len(alternatives), 0)
        for alt in alternatives:
            self.assertIn("connection_type", alt)
            self.assertIn("driver_status", alt)
            self.assertIn("effort", alt)
            self.assertIn(alt["driver_status"], ["mainline", "backport", "vendor", "unknown"])
            self.assertIn(alt["effort"], ["low", "medium", "high"])


# ─── Edge case tests ───────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""
    
    def test_board_map_missing_soc(self):
        """Test that validator handles missing SoC gracefully."""
        board = create_rpi4_board_map()
        board.pop("soc")
        components = [create_ov5647_camera_component()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        # Should still work, might just fail driver lookup
        self.assertEqual(len(result["component_status"]), 1)
    
    def test_board_map_missing_peripherals(self):
        """Test that validator handles missing peripherals gracefully."""
        board = {"soc": "BCM2711"}
        components = [create_ov5647_camera_component()]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["component_status"]), 1)
        self.assertEqual(result["component_status"][0]["status"], "NO_INTERFACE")
    
    def test_invalid_component_dict(self):
        """Test that validator handles invalid components gracefully."""
        board = create_rpi4_board_map()
        components = [
            create_ov5647_camera_component(),
            "not a dict",  # Invalid
            None,  # Invalid
            create_missing_interface_component()
        ]
        
        result = validate_component_connections(board, components)
        
        self.assertTrue(result["valid"])
        # Should skip invalid items and process valid ones
        self.assertEqual(len(result["component_status"]), 2)
    
    def test_voltage_tolerance_boundary(self):
        """Test voltage compatibility at tolerance boundary."""
        # 3.3V and 3.2V are exactly 0.1V apart (at default tolerance)
        self.assertTrue(_voltages_compatible("3.3V", "3.2V"))
        # 3.3V and 3.19V are 0.11V apart (just outside tolerance)
        self.assertFalse(_voltages_compatible("3.3V", "3.19V"))


if __name__ == "__main__":
    unittest.main()
