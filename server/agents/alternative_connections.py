"""
Alternative connection types for peripherals.

Maps peripheral types to their supported connection types.
Validation ensures all types are supported by librarian.py.
"""

from typing import List

# Supported connection types from librarian.py
SUPPORTED_CONNECTION_TYPES = {
    "i2c", "spi", "uart", "usart", "gpio", "pwm", "usb", "ethernet",
    "can", "can_fd", "hdmi", "displayport", "mipi_dsi", "mipi_csi",
    "camera", "lvds", "pcie", "sata", "emmc", "sd", "sdio", "i2s",
    "sai", "audio", "adc", "dac", "jtag", "swd", "rtc", "watchdog",
    "qspi", "flexcan", "flexspi", "lpspi", "lpi2c", "lpuart", "spdif",
}

# Mapping of peripheral types to their alternative connection types
ALTERNATIVE_CONNECTIONS = {
    "camera": ["usb", "mipi_csi", "mipi_dsi"],
    "display": ["hdmi", "displayport", "mipi_dsi", "lvds"],
    "audio": ["i2s", "sai", "usb", "spdif"],
    "touchscreen": ["i2c", "spi", "usb"],
    "sensor_accelerometer": ["i2c", "spi"],
    "sensor_gyro": ["i2c", "spi"],
    "sensor_compass": ["i2c", "spi"],
    "sensor_temperature": ["i2c", "adc"],
    "sensor_light": ["i2c", "adc"],
    "sensor_pressure": ["i2c", "spi"],
    "gps": ["uart", "usart", "usb"],
    "modem": ["uart", "usart", "usb", "spi"],
    "bluetooth": ["uart", "usart", "usb"],
    "wifi": ["sdio", "spi", "usb", "pcie"],
    "ethernet": ["ethernet", "usb"],
    "nfc": ["i2c", "spi", "usb"],
}


def get_alternatives(peripheral_type: str) -> List[str]:
    """
    Get alternative connection types for a peripheral.

    Args:
        peripheral_type: Type of peripheral (case-insensitive)

    Returns:
        List of valid connection types for the peripheral.
        Empty list if peripheral type not found.
    """
    normalized = peripheral_type.lower().strip()
    return ALTERNATIVE_CONNECTIONS.get(normalized, [])


def validate_connections() -> tuple[bool, List[str]]:
    """
    Validate that all connection types are supported.

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    for peripheral, connections in ALTERNATIVE_CONNECTIONS.items():
        # Check peripheral has at least 1 connection type
        if not connections:
            errors.append(f"Peripheral '{peripheral}' has no connection types")

        # Check all connection types are valid
        for conn_type in connections:
            if conn_type not in SUPPORTED_CONNECTION_TYPES:
                errors.append(
                    f"Invalid connection type '{conn_type}' "
                    f"for peripheral '{peripheral}'. "
                    f"Supported types: {sorted(SUPPORTED_CONNECTION_TYPES)}"
                )

    return len(errors) == 0, errors
