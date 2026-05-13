"""
Tests for bus_validator.py
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from bus_validator import validate_connections


def test_single_map():
    """Test with a single map (should return empty conflicts)."""
    maps = [
        {
            "peripherals": [
                {
                    "id": "i2c0",
                    "name": "I2C Bus 0",
                    "type": "i2c",
                    "bus": "I2C0",
                    "description": "I2C0 with SDA and SCL pins"
                }
            ],
            "power_rails": []
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True
    assert len(result["conflicts"]) == 0
    print("✓ test_single_map passed")


def test_matching_i2c_buses():
    """Test with matching I2C buses across two maps."""
    maps = [
        {
            "peripherals": [
                {
                    "id": "i2c0_sensor",
                    "name": "Temperature Sensor",
                    "type": "i2c",
                    "bus": "I2C0",
                    "description": "Uses I2C0 with SDA and SCL"
                }
            ],
            "power_rails": []
        },
        {
            "peripherals": [
                {
                    "id": "i2c0_eeprom",
                    "name": "EEPROM",
                    "type": "i2c",
                    "bus": "I2C0",
                    "description": "Connects to I2C0 SDA SCL"
                }
            ],
            "power_rails": []
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True
    assert len(result["conflicts"]) == 0
    assert "I2C0" in result["merged_buses"]
    pins = result["merged_buses"]["I2C0"]
    assert "SDA" in pins
    assert "SCL" in pins
    print("✓ test_matching_i2c_buses passed")


def test_conflicting_spi_buses():
    """Test with conflicting SPI pin counts."""
    maps = [
        {
            "peripherals": [
                {
                    "id": "spi0_flash",
                    "name": "SPI Flash",
                    "type": "spi",
                    "bus": "SPI0",
                    "description": "SPI0 with MOSI MISO CLK CS"
                }
            ],
            "power_rails": []
        },
        {
            "peripherals": [
                {
                    "id": "spi0_display",
                    "name": "SPI Display",
                    "type": "spi",
                    "bus": "SPI0",
                    "description": "SPI0 with MOSI MISO CLK CS RESET ENABLE"
                }
            ],
            "power_rails": []
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True  # Still valid, just warned
    assert len(result["conflicts"]) > 0  # Should have conflict
    conflict = result["conflicts"][0]
    assert conflict["type"] == "bus_pin_mismatch"
    assert conflict["bus_name"] == "SPI0"
    assert conflict["severity"] == "warning"
    print(f"✓ test_conflicting_spi_buses passed: {conflict['message']}")


def test_power_rail_conflict():
    """Test power rail voltage conflict detection."""
    maps = [
        {
            "peripherals": [],
            "power_rails": [
                {
                    "name": "VCC_3V3",
                    "voltage": "3.3V"
                }
            ]
        },
        {
            "peripherals": [],
            "power_rails": [
                {
                    "name": "VCC_3V3",
                    "voltage": "3.0V"
                }
            ]
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True
    assert len(result["conflicts"]) > 0
    conflict = result["conflicts"][0]
    assert conflict["type"] == "power_rail_mismatch"
    assert "3.3V" in str(conflict["map_a_pins"])
    assert "3.0V" in str(conflict["map_b_pins"])
    print(f"✓ test_power_rail_conflict passed: {conflict['message']}")


def test_empty_list():
    """Test with empty list."""
    result = validate_connections([])
    assert result["valid"] is True
    assert len(result["conflicts"]) == 0
    assert result["merged_buses"] == {}
    print("✓ test_empty_list passed")


def test_multiple_buses():
    """Test with multiple different bus types."""
    maps = [
        {
            "peripherals": [
                {
                    "id": "i2c0",
                    "name": "I2C0",
                    "type": "i2c",
                    "bus": "I2C0",
                    "description": "I2C0 SDA SCL"
                },
                {
                    "id": "spi0",
                    "name": "SPI0",
                    "type": "spi",
                    "bus": "SPI0",
                    "description": "SPI0 MOSI MISO CLK"
                }
            ],
            "power_rails": []
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True
    assert len(result["conflicts"]) == 0
    assert "I2C0" in result["merged_buses"]
    assert "SPI0" in result["merged_buses"]
    print("✓ test_multiple_buses passed")


def test_uart_bus():
    """Test UART bus detection."""
    maps = [
        {
            "peripherals": [
                {
                    "id": "uart0",
                    "name": "Serial",
                    "type": "uart",
                    "bus": "UART0",
                    "description": "UART0 with RX TX RTS CTS"
                }
            ],
            "power_rails": []
        }
    ]
    
    result = validate_connections(maps)
    assert result["valid"] is True
    assert "UART0" in result["merged_buses"]
    uart_pins = result["merged_buses"]["UART0"]
    assert "RX" in uart_pins or "RXD" in uart_pins
    assert "TX" in uart_pins or "TXD" in uart_pins
    print("✓ test_uart_bus passed")


if __name__ == "__main__":
    test_single_map()
    test_matching_i2c_buses()
    test_conflicting_spi_buses()
    test_power_rail_conflict()
    test_empty_list()
    test_multiple_buses()
    test_uart_bus()
    print("\n✅ All tests passed!")
