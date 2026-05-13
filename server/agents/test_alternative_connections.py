"""Tests for alternative_connections module."""

import pytest
from alternative_connections import (
    get_alternatives,
    validate_connections,
    ALTERNATIVE_CONNECTIONS,
)


def test_get_alternatives_camera():
    """Test camera peripheral has expected connection types."""
    result = get_alternatives("camera")
    assert result == ["usb", "mipi_csi", "mipi_dsi"]


def test_get_alternatives_display():
    """Test display peripheral has expected connection types."""
    result = get_alternatives("display")
    assert result == ["hdmi", "displayport", "mipi_dsi", "lvds"]


def test_get_alternatives_audio():
    """Test audio peripheral has expected connection types."""
    result = get_alternatives("audio")
    assert result == ["i2s", "sai", "usb", "spdif"]


def test_get_alternatives_case_insensitive():
    """Test case-insensitive peripheral lookup."""
    assert get_alternatives("CAMERA") == ["usb", "mipi_csi", "mipi_dsi"]
    assert get_alternatives("Camera") == ["usb", "mipi_csi", "mipi_dsi"]
    assert get_alternatives("camera") == ["usb", "mipi_csi", "mipi_dsi"]


def test_get_alternatives_with_whitespace():
    """Test peripheral lookup handles whitespace."""
    assert get_alternatives("  camera  ") == ["usb", "mipi_csi", "mipi_dsi"]


def test_get_alternatives_not_found():
    """Test unknown peripheral returns empty list."""
    result = get_alternatives("unknown_peripheral")
    assert result == []


def test_validate_connections_passes():
    """Test validation passes for all defined connections."""
    is_valid, errors = validate_connections()
    assert is_valid, f"Validation failed with errors: {errors}"
    assert len(errors) == 0


def test_all_peripherals_have_connections():
    """Test all peripherals map to at least one connection type."""
    for peripheral, connections in ALTERNATIVE_CONNECTIONS.items():
        assert connections, f"Peripheral '{peripheral}' has no connection types"
        assert isinstance(connections, list)
        assert all(isinstance(c, str) for c in connections)


def test_peripheral_coverage():
    """Test all expected peripheral types are covered."""
    expected_peripherals = {
        "camera", "display", "audio", "touchscreen",
        "sensor_accelerometer", "sensor_gyro", "sensor_compass",
        "sensor_temperature", "sensor_light", "sensor_pressure",
        "gps", "modem", "bluetooth", "wifi", "ethernet", "nfc",
    }
    assert expected_peripherals.issubset(ALTERNATIVE_CONNECTIONS.keys())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
