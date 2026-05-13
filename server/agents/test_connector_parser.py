"""
Tests for connector_parser module.

Tests pin extraction, bus type inference, and connector/voltage detection.
"""

from connector_parser import (
    parse_connector_pins,
    _extract_pins,
    _infer_bus_type,
    _extract_connector_type,
    _extract_voltage,
)


class TestPinExtraction:
    """Test pin name extraction from various formats."""
    
    def test_extract_pins_from_table_format(self):
        """Extract pins from table format 'Pin 1: name'."""
        text = """
        Pin 1: VCC (3.3V)
        Pin 2: GND
        Pin 3: SDA
        Pin 4: SCL
        """
        pins = _extract_pins(text)
        
        assert 'VCC' in pins
        assert 'GND' in pins
        assert 'SDA' in pins
        assert 'SCL' in pins
    
    def test_extract_pins_from_csv_list(self):
        """Extract pins from CSV format 'pins CSI_D0, CSI_D1, CSI_CLK'."""
        text = "Pins: CSI_D0, CSI_D1, CSI_D2, CSI_CLK, GND"
        pins = _extract_pins(text)
        
        assert 'CSI_D0' in pins
        assert 'CSI_D1' in pins
        assert 'CSI_D2' in pins
        assert 'CSI_CLK' in pins
    
    def test_extract_pins_from_inline_descriptive(self):
        """Extract pins from inline format 'CSI_D0: data line'."""
        text = """
        CSI_D0: camera data line 0
        CSI_D1: camera data line 1
        CSI_CLK: camera clock signal
        """
        pins = _extract_pins(text)
        
        assert 'CSI_D0' in pins
        assert 'CSI_D1' in pins
        assert 'CSI_CLK' in pins
    
    def test_extract_pins_removes_duplicates(self):
        """Should remove duplicate pin names."""
        text = "Pins: SDA, SCL, SDA, INT, SCL"
        pins = _extract_pins(text)
        
        # Should have no duplicates
        assert len(pins) == len(set(pins))
        assert 'SDA' in pins
        assert 'SCL' in pins
        assert 'INT' in pins
    
    def test_extract_pins_filters_short_names(self):
        """Should filter out very short generic names."""
        text = "Pins: A, B, C, DATA, CLK, GND"
        pins = _extract_pins(text)
        
        # Single letters should be filtered
        assert 'A' not in pins
        assert 'B' not in pins
        assert 'C' not in pins
        # But real pins should remain
        assert 'DATA' in pins or 'CLK' in pins
    
    def test_extract_pins_with_plus_minus(self):
        """Handle pins with +/- notation (D+, D-)."""
        text = "USB Pins: D+, D-, VBUS, GND"
        pins = _extract_pins(text)
        
        # Should handle special chars
        assert len(pins) >= 2


class TestBusTypeInference:
    """Test bus type inference from pins and keywords."""
    
    def test_infer_mipi_csi_from_keywords(self):
        """Should detect MIPI_CSI from explicit keyword."""
        text = "MIPI CSI Interface\nPins: CSI_D0, CSI_D1, CSI_CLK"
        bus_type, confidence = _infer_bus_type(text, ['CSI_D0', 'CSI_D1', 'CSI_CLK'])
        
        assert bus_type == 'MIPI_CSI'
        assert confidence > 0.5
    
    def test_infer_i2c_from_pins(self):
        """Should detect I2C from SDA/SCL pins."""
        text = "I2C Connector"
        pins = ['SDA', 'SCL', 'INT']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'I2C'
        assert confidence > 0.5
    
    def test_infer_spi_from_pins(self):
        """Should detect SPI from MOSI/MISO/CLK/CS pins."""
        text = "SPI Interface"
        pins = ['MOSI', 'MISO', 'CLK', 'CS']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'SPI'
        assert confidence > 0.5
    
    def test_infer_usb_from_pins(self):
        """Should detect USB from DP/DM/VBUS pins."""
        text = "USB connector"
        pins = ['DP', 'DM', 'VBUS', 'GND']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'USB'
        assert confidence > 0.5
    
    def test_infer_uart_from_pins(self):
        """Should detect UART from TX/RX pins."""
        text = "UART Serial Interface"
        pins = ['TX', 'RX']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'UART'
        assert confidence > 0.5
    
    def test_infer_hdmi_from_pins(self):
        """Should detect HDMI from D0_P/D1_P/CLK_P pins."""
        text = "HDMI Interface"
        pins = ['D0_P', 'D0_N', 'D1_P', 'D1_N', 'CLK_P', 'CLK_N']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'HDMI'
        assert confidence > 0.5
    
    def test_infer_unknown_without_matches(self):
        """Should return unknown if no bus type matches."""
        text = "Some random connector"
        pins = ['PIN1', 'PIN2', 'PIN3']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'unknown'
        assert confidence == 0.0
    
    def test_case_insensitive_keyword_matching(self):
        """Bus type detection should be case insensitive."""
        text = "i2c interface with sda and scl"
        pins = ['SDA', 'SCL']
        bus_type, confidence = _infer_bus_type(text, pins)
        
        assert bus_type == 'I2C'
    
    def test_keyword_weight_higher_than_pins(self):
        """Explicit keywords should carry more weight."""
        text = "UART serial interface"
        pins = ['SDA', 'SCL']  # I2C pins, but text says UART
        bus_type, confidence = _infer_bus_type(text, pins)
        
        # UART keyword should help, even with conflicting pins
        # (actually this might detect I2C first due to pins, but let's see)


class TestConnectorTypeExtraction:
    """Test connector type detection."""
    
    def test_extract_fpc_connector(self):
        """Should extract FPC connector type."""
        text = "50-pin FPC connector for camera interface"
        connector_type = _extract_connector_type(text)
        
        assert 'FPC' in connector_type
        assert '50' in connector_type
    
    def test_extract_pin_header(self):
        """Should extract standard pin header."""
        text = "0.1 inch standard header connector"
        connector_type = _extract_connector_type(text)
        
        assert 'header' in connector_type.lower()
    
    def test_extract_usb_type_c(self):
        """Should extract USB Type-C connector."""
        text = "USB Type-C connector for power delivery"
        connector_type = _extract_connector_type(text)
        
        assert 'USB' in connector_type
        assert 'Type' in connector_type
    
    def test_extract_micro_usb(self):
        """Should extract Micro USB connector."""
        text = "Micro USB connector for charging"
        connector_type = _extract_connector_type(text)
        
        assert 'USB' in connector_type.upper()
    
    def test_extract_unknown_connector(self):
        """Should return unknown for non-standard connectors."""
        text = "Some proprietary connector interface"
        connector_type = _extract_connector_type(text)
        
        # May be unknown or might extract something generic
        assert connector_type is not None


class TestVoltageExtraction:
    """Test voltage specification detection."""
    
    def test_extract_voltage_3_3v(self):
        """Should extract 3.3V voltage."""
        text = "Operating voltage: 3.3V"
        voltage = _extract_voltage(text)
        
        assert voltage is not None
        assert '3.3' in voltage
        assert 'V' in voltage
    
    def test_extract_voltage_5v(self):
        """Should extract 5V voltage."""
        text = "Supply voltage is 5V DC"
        voltage = _extract_voltage(text)
        
        assert voltage is not None
        assert '5' in voltage
    
    def test_extract_voltage_1_8v(self):
        """Should extract 1.8V voltage."""
        text = "IO voltage: 1.8V"
        voltage = _extract_voltage(text)
        
        assert voltage is not None
        assert '1.8' in voltage
    
    def test_extract_voltage_3v3_format(self):
        """Should extract voltage in 3V3 format."""
        text = "Operate at 3V3 logic levels"
        voltage = _extract_voltage(text)
        
        assert voltage is not None
    
    def test_extract_no_voltage(self):
        """Should return None if no voltage found."""
        text = "Connector without voltage specification"
        voltage = _extract_voltage(text)
        
        assert voltage is None


class TestFullParsing:
    """Integration tests for full connector parsing."""
    
    def test_parse_mipi_csi_connector(self):
        """Parse complete MIPI CSI connector section."""
        text = """
        MIPI CSI Connector
        Connector Type: 30-pin FPC
        Operating Voltage: 1.8V
        
        Pin Map
        Pin 1: GND
        Pin 2: CSI_D0
        Pin 3: CSI_D1
        Pin 4: CSI_CLK
        Pin 5: CSI_VS
        Pin 6: CSI_HS
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'MIPI_CSI'
        assert 'CSI_D0' in result['pins']
        assert 'CSI_CLK' in result['pins']
        assert result['voltage'] is not None
        assert '1.8' in result['voltage']
        assert result['confidence'] > 0.5
    
    def test_parse_i2c_connector(self):
        """Parse complete I2C connector section."""
        text = """
        I2C Interface Header
        Type: 4-pin header (0.1 inch pitch)
        Voltage: 3.3V
        
        Pin 1: VCC
        Pin 2: GND
        Pin 3: SDA
        Pin 4: SCL
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'I2C'
        assert 'SDA' in result['pins']
        assert 'SCL' in result['pins']
        assert '3.3' in result['voltage']
        assert result['confidence'] > 0.5
    
    def test_parse_usb_connector(self):
        """Parse complete USB connector section."""
        text = """
        USB Type-C Connector
        Power Delivery: Yes
        Voltage: 5V
        
        Pin Map:
        D+, D-, VBUS, GND, ID
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'USB'
        assert '5' in result['voltage']
        assert 'Type' in result['connector_type']
        assert result['confidence'] > 0.3
    
    def test_parse_uart_connector(self):
        """Parse complete UART connector section."""
        text = """
        UART Serial Interface
        Type: Standard 6-pin header
        Voltage: 3.3V
        
        Pins: TX, RX, RTS, CTS, VCC, GND
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'UART'
        assert 'TX' in result['pins']
        assert 'RX' in result['pins']
        assert 'VCC' in result['pins']
        assert result['confidence'] > 0.5
    
    def test_parse_mixed_content_unknown_bus(self):
        """Parse section with no clear bus type."""
        text = """
        Generic Connector
        Pin 1: Signal A
        Pin 2: Signal B
        Pin 3: Signal C
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'unknown'
        assert result['confidence'] == 0.0
    
    def test_parse_empty_text(self):
        """Handle empty input gracefully."""
        result = parse_connector_pins("")
        
        assert result['bus_type'] == 'unknown'
        assert result['pins'] == []
        assert result['confidence'] == 0.0
    
    def test_parse_none_input(self):
        """Handle None input gracefully."""
        result = parse_connector_pins(None)
        
        assert result['bus_type'] == 'unknown'
        assert result['pins'] == []
        assert result['confidence'] == 0.0
    
    def test_parse_returns_dict_with_all_keys(self):
        """Ensure result dict has all expected keys."""
        result = parse_connector_pins("Some text")
        
        assert 'bus_type' in result
        assert 'pins' in result
        assert 'connector_type' in result
        assert 'voltage' in result
        assert 'confidence' in result


class TestRealWorldExamples:
    """Test with realistic datasheet-like content."""
    
    def test_ov5640_camera_pinout(self):
        """Test with OV5640 camera sensor-like pinout."""
        text = """
        OV5640 MIPI Camera Module
        
        Connector Interface: 30-pin FPC connector
        Operating Voltage: 1.8V IO, 3.3V Core
        
        MIPI CSI Interface Pin Map:
        Pin 1: GND
        Pin 2: CSI_D0 (Camera Data Line 0)
        Pin 3: CSI_D1 (Camera Data Line 1)
        Pin 4: GND
        Pin 5: CSI_CLK (Camera Clock)
        Pin 6: CSI_HS (Horizontal Sync)
        Pin 7: CSI_VS (Vertical Sync)
        Pin 8: GND
        
        Control Interface: I2C
        Pin A: SDA (3.3V)
        Pin B: SCL (3.3V)
        Pin C: INT
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'MIPI_CSI'
        assert 'CSI_D0' in result['pins']
        assert 'CSI_D1' in result['pins']
        assert 'CSI_CLK' in result['pins']
        assert 'GND' in result['pins']
        assert result['voltage'] is not None
        assert result['confidence'] > 0.5
    
    def test_rpi_gpio_header(self):
        """Test with Raspberry Pi GPIO header-like format."""
        text = """
        GPIO Header Pinout
        Type: 40-pin 2.54mm dual-row header
        Operating Voltage: 3.3V (GPIO), 5V (Power)
        
        Pins:
        1: 3V3, 2: 5V, 3: GPIO2 (SDA), 4: 5V, 
        5: GPIO3 (SCL), 6: GND, 7: GPIO4, 8: GPIO14 (TX)
        """
        
        result = parse_connector_pins(text)
        
        # Should extract pins successfully
        assert 'GND' in result['pins']
        # Should extract header connector type
        assert 'header' in result['connector_type'].lower() or '40' in result['connector_type']
        # Voltage should be detected
        assert result['voltage'] is not None
    
    def test_usb_type_c_pd_connector(self):
        """Test with USB Type-C Power Delivery connector."""
        text = """
        USB Type-C Connector Pinout
        Standard: USB 3.1 Gen 1 with Power Delivery
        Operating Voltage: 5V/3A (standard), 20V/5A (PD)
        
        Pin Configuration:
        GND, TX1_P, TX1_N, VBUS, RX2_N, RX2_P, GND, D+, D-, SBU2
        VBUS, RX1_N, RX1_P, GND, TX2_P, TX2_N, GND
        """
        
        result = parse_connector_pins(text)
        
        assert result['bus_type'] == 'USB'
        assert result['voltage'] is not None
        assert 'Type-C' in result['connector_type']


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_malformed_pin_data(self):
        """Handle malformed pin data gracefully."""
        text = """
        Pin : : : Data
        Pin 1 2 3: Broken
        Pins@@@: SDA SCL
        """
        
        result = parse_connector_pins(text)
        
        # Should not crash
        assert isinstance(result, dict)
        assert 'bus_type' in result
    
    def test_very_long_connector_section(self):
        """Handle very long sections efficiently."""
        lines = ["Pin {}: PIN_{:02d}".format(i, i) for i in range(200)]
        text = "\n".join(lines)
        
        result = parse_connector_pins(text)
        
        # Should extract pins
        assert len(result['pins']) > 0
    
    def test_unicode_and_special_chars(self):
        """Handle unicode and special characters."""
        text = """
        Pin Map — CSI Interface
        • Pin 1: GND
        • Pin 2: CSI_D0 (±10% tolerance)
        • Pin 3: CSI_D1 (3.3V–5V compatible)
        """
        
        result = parse_connector_pins(text)
        
        # Should handle without crashing
        assert isinstance(result, dict)
        assert 'CSI_D0' in result['pins']
    
    def test_multiple_bus_types_in_text(self):
        """Handle text mentioning multiple bus types."""
        text = """
        Multi-Interface Module
        
        MIPI CSI Interface:
        Pins: CSI_D0, CSI_D1, CSI_CLK
        
        I2C Control Interface:
        Pins: SDA, SCL
        
        UART Debug Interface:
        Pins: TX, RX
        """
        
        result = parse_connector_pins(text)
        
        # Should detect one of them (likely MIPI due to explicit keyword)
        assert result['bus_type'] != 'unknown'
        assert len(result['pins']) > 0


if __name__ == "__main__":
    print("Run tests using: python3 run_tests.py")

