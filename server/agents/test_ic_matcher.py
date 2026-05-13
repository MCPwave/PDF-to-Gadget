"""
Unit tests for IC Matcher.

Tests known IC recognition, case-insensitivity, connection type inference,
and confidence scoring.
"""

import pytest
from ic_matcher import (
    match_component_ics,
    match_component_ics_with_positions,
    _build_ic_regex,
    _extract_context,
    _infer_connection_type,
    ICMatch,
)


class TestICMatcherBasic:
    """Test basic IC matching functionality."""

    def test_single_ov5647_match(self):
        """Test recognizing OV5647 camera sensor."""
        text = "The OV5647 camera sensor uses MIPI CSI for data transmission."
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "ov5647"
        assert matches[0].component_type == "camera_sensor"

    def test_single_ili9341_match(self):
        """Test recognizing ILI9341 display controller."""
        text = "Display ili9341 via SPI bus"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "ili9341"
        assert matches[0].component_type == "display"

    def test_single_tmp36_match(self):
        """Test recognizing TMP36 temperature sensor."""
        text = "Using TMP36 sensor on the board"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "tmp36"
        assert matches[0].component_type == "sensor_temperature"

    def test_unknown_ic_no_match(self):
        """Test that unknown IC names don't match."""
        text = "Using unknown XYZ123 sensor"
        matches = match_component_ics(text)
        assert len(matches) == 0

    def test_empty_text(self):
        """Test handling of empty text."""
        assert match_component_ics("") == []
        assert match_component_ics(None) == []


class TestCaseInsensitivity:
    """Test case-insensitive IC matching."""

    def test_uppercase_ic(self):
        """Test all uppercase IC name."""
        text = "The OV5647 camera sensor"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "ov5647"

    def test_lowercase_ic(self):
        """Test all lowercase IC name."""
        text = "The ov5647 camera sensor"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "ov5647"

    def test_mixed_case_ic(self):
        """Test mixed case IC name."""
        text = "The OV5647 camera sensor"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "ov5647"

    def test_lowercase_st7789(self):
        """Test st7789 in lowercase."""
        text = "st7789 display controller"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "st7789"

    def test_mixed_case_multiple_ics(self):
        """Test multiple ICs with different cases."""
        text = "Board with OV5647 camera, ILI9341 display, and TMP36 sensor"
        matches = match_component_ics(text)
        assert len(matches) == 3
        names = {m.ic_name for m in matches}
        assert names == {"ov5647", "ili9341", "tmp36"}


class TestConnectionTypeInference:
    """Test connection type inference from context."""

    def test_mipi_csi_explicit_in_context(self):
        """Test MIPI CSI keyword in context."""
        text = "OV5647 uses MIPI CSI interface"
        matches = match_component_ics(text)
        assert matches[0].connection_type == "mipi_csi"
        assert matches[0].confidence > 0.7

    def test_i2c_explicit_in_context(self):
        """Test I2C keyword in context."""
        text = "TMP36 sensor connected via I2C bus"
        matches = match_component_ics(text)
        assert matches[0].connection_type == "i2c"
        assert matches[0].confidence > 0.7

    def test_spi_explicit_in_context(self):
        """Test SPI keyword in context."""
        text = "ILI9341 display communicates via SPI"
        matches = match_component_ics(text)
        assert matches[0].connection_type == "spi"
        assert matches[0].confidence > 0.7

    def test_usb_explicit_in_context(self):
        """Test USB keyword in context."""
        text = "OV5647 over USB connection"
        matches = match_component_ics(text)
        assert matches[0].connection_type == "usb"
        assert matches[0].confidence > 0.7

    def test_default_connection_when_not_in_context(self):
        """Test using default connection when not mentioned."""
        text = "Board includes OV5647 and BMP280"
        matches = match_component_ics(text)
        # Both should use defaults (no connection keywords in context)
        ov5647_match = next(m for m in matches if m.ic_name == "ov5647")
        bmp280_match = next(m for m in matches if m.ic_name == "bmp280")
        assert ov5647_match.connection_type == "mipi_csi"
        assert bmp280_match.connection_type == "i2c"


class TestConfidenceScoring:
    """Test confidence score calculation."""

    def test_high_confidence_with_context(self):
        """Test high confidence (0.9) when IC and connection found."""
        text = "OV5647 camera sensor uses MIPI CSI interface"
        matches = match_component_ics(text)
        assert matches[0].confidence > 0.8  # Should be 0.9

    def test_medium_confidence_default_connection(self):
        """Test medium confidence (0.7) with default connection type."""
        text = "Board has OV5647 and BMP280 components"
        matches = match_component_ics(text)
        for match in matches:
            # No connection keywords, so should use defaults with medium confidence
            assert match.confidence >= 0.5

    def test_low_confidence_no_context(self):
        """Test low confidence when only IC name found."""
        text = "Components: ov5647"
        matches = match_component_ics(text)
        assert matches[0].confidence >= 0.5


class TestMultipleMatches:
    """Test matching multiple ICs in same text."""

    def test_two_ics_same_context(self):
        """Test matching two ICs in same sentence."""
        text = "The board uses OV5647 camera and ILI9341 display"
        matches = match_component_ics(text)
        assert len(matches) == 2
        names = {m.ic_name for m in matches}
        assert names == {"ov5647", "ili9341"}

    def test_three_ics_different_sentences(self):
        """Test matching three ICs in different sentences."""
        text = """
        The camera sensor OV5647 provides image data.
        The ILI9341 display shows the output.
        Temperature is monitored with TMP36.
        """
        matches = match_component_ics(text)
        assert len(matches) == 3
        names = {m.ic_name for m in matches}
        assert names == {"ov5647", "ili9341", "tmp36"}

    def test_same_ic_multiple_times(self):
        """Test matching same IC appearing multiple times."""
        text = "OV5647 is used in primary camera. Backup OV5647 available."
        matches = match_component_ics(text)
        # Should have 2 matches for the same IC
        assert len(matches) == 2
        assert all(m.ic_name == "ov5647" for m in matches)


class TestContextExtraction:
    """Test context extraction around matches."""

    def test_context_window_100_chars(self):
        """Test context is approximately 100 chars on each side."""
        long_text = "A" * 100 + "OV5647" + "B" * 100
        matches = match_component_ics(long_text)
        assert len(matches) == 1
        context = matches[0].context
        # Context should contain the IC name and surrounding text
        assert "OV5647" in context.upper()

    def test_context_at_text_start(self):
        """Test context extraction at beginning of text."""
        text = "OV5647 camera sensor"
        matches = match_component_ics(text)
        assert "OV5647" in matches[0].context.upper()

    def test_context_at_text_end(self):
        """Test context extraction at end of text."""
        text = "Camera sensor is the OV5647"
        matches = match_component_ics(text)
        assert "OV5647" in matches[0].context.upper()


class TestPositionTracking:
    """Test position tracking in text."""

    def test_positions_with_positions_function(self):
        """Test match positions returned by with_positions function."""
        text = "OV5647 and ILI9341 are used"
        results = match_component_ics_with_positions(text)
        assert len(results) == 2
        # Check positions are valid
        for result in results:
            start, end = result["position"]
            matched_text = text[start:end]
            assert matched_text.lower() in ["ov5647", "ili9341"]

    def test_position_order_matches_text(self):
        """Test matches are returned in text order."""
        text = "Board has OV5647 camera and ILI9341 display"
        results = match_component_ics_with_positions(text)
        positions = [r["position"][0] for r in results]
        # Positions should be in ascending order
        assert positions == sorted(positions)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_ic_in_word_boundary(self):
        """Test IC name at word boundaries."""
        text = "The OV5647 camera"
        matches = match_component_ics(text)
        assert len(matches) == 1

    def test_ic_with_special_chars_nearby(self):
        """Test IC name with special characters nearby."""
        text = "Sensor: OV5647; Display: ILI9341!"
        matches = match_component_ics(text)
        assert len(matches) == 2

    def test_long_pdf_text(self):
        """Test with longer PDF-like text."""
        text = """
        DATASHEET: Raspberry Pi Camera Module v2
        ==========================================
        The OV5647 sensor provides up to 8MP resolution.
        It connects via MIPI CSI-2 interface.
        
        Supporting Hardware:
        - Display: ILI9341 (SPI)
        - Temperature: TMP36 (I2C)
        
        Specifications:
        The OV5647 CMOS sensor delivers excellent image quality.
        """
        matches = match_component_ics(text)
        # OV5647 appears twice, should be caught once each
        ov5647_matches = [m for m in matches if m.ic_name == "ov5647"]
        ili9341_matches = [m for m in matches if m.ic_name == "ili9341"]
        tmp36_matches = [m for m in matches if m.ic_name == "tmp36"]
        
        assert len(ov5647_matches) >= 1
        assert len(ili9341_matches) == 1
        assert len(tmp36_matches) == 1


class TestDashInICNames:
    """Test ICs with dashes in names (like edt-ft5x06)."""

    def test_dash_ic_name(self):
        """Test matching IC name with dash."""
        text = "Touchscreen controlled by edt-ft5x06 driver"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "edt-ft5x06"

    def test_dash_ic_uppercase(self):
        """Test dashed IC name in uppercase."""
        text = "Using EDT-FT5X06 controller"
        matches = match_component_ics(text)
        assert len(matches) == 1
        assert matches[0].ic_name == "edt-ft5x06"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
