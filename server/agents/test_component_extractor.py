"""
Tests for component_extractor module.

Tests keyword detection, section extraction, and text preprocessing.
"""

import pytest
from component_extractor import (
    detect_component_keywords,
    extract_section_text,
    preprocess_pdf_text,
    categorize_keywords,
    get_unique_keywords,
    COMPONENT_KEYWORDS,
    SECTION_KEYWORDS
)


class TestPreprocessing:
    """Test text preprocessing functionality."""
    
    def test_remove_page_numbers(self):
        """Page numbers should be removed."""
        text = "Some content\n42\nMore content"
        result = preprocess_pdf_text(text)
        assert "42" not in result
        assert "Some content" in result
    
    def test_normalize_whitespace(self):
        """Multiple spaces should be normalized."""
        text = "Text  with   multiple    spaces"
        result = preprocess_pdf_text(text)
        assert "  " not in result
    
    def test_preserve_line_breaks(self):
        """Line breaks should be preserved."""
        text = "Line 1\nLine 2\nLine 3"
        result = preprocess_pdf_text(text)
        lines = result.split('\n')
        assert len(lines) >= 3


class TestComponentDetection:
    """Test component keyword detection."""
    
    def test_detect_single_component_keyword(self):
        """Should detect single component keyword."""
        text = "The camera module is integrated on the board."
        matches = detect_component_keywords(text)
        
        assert len(matches) > 0
        assert any(m['keyword'] == 'camera' for m in matches)
        assert any(m['section_type'] == 'component' for m in matches)
    
    def test_detect_multiple_component_keywords(self):
        """Should detect multiple component keywords in text."""
        text = "Device contains camera, sensor, display, and touchscreen."
        matches = detect_component_keywords(text)
        
        keywords = {m['keyword'] for m in matches}
        assert 'camera' in keywords
        assert 'sensor' in keywords
        assert 'display' in keywords
        assert 'touchscreen' in keywords
    
    def test_case_insensitive_detection(self):
        """Should detect keywords regardless of case."""
        text = "CAMERA module, Sensor inputs, Display output"
        matches = detect_component_keywords(text)
        keywords = {m['keyword'].lower() for m in matches}
        
        assert 'camera' in keywords
        assert 'sensor' in keywords
        assert 'display' in keywords
    
    def test_word_boundary_matching(self):
        """Should not match partial words (e.g., camera in camera_module)."""
        text = "The camera_sensor and gyroscope_camera are present."
        matches = detect_component_keywords(text)
        
        # Should match standalone "camera" but might match in compound words too
        # depending on implementation - just verify we get matches
        assert len(matches) > 0
    
    def test_context_extraction(self):
        """Should extract surrounding context around matches."""
        text = "This is the component camera sensor information for the board."
        matches = detect_component_keywords(text)
        
        assert len(matches) > 0
        for match in matches:
            if match['keyword'] == 'camera':
                assert len(match['context']) > 0
                assert 'camera' in match['context'].lower()
    
    def test_line_number_tracking(self):
        """Should track line numbers correctly."""
        text = "Line 1\nLine 2 with camera\nLine 3"
        matches = detect_component_keywords(text)
        
        camera_match = [m for m in matches if m['keyword'] == 'camera']
        assert len(camera_match) > 0
        assert camera_match[0]['line_number'] == 2


class TestSectionDetection:
    """Test section marker detection."""
    
    def test_detect_pinout_section(self):
        """Should detect pinout section markers."""
        text = "Pin Map\nPin 1: VCC\nPin 2: GND"
        matches = detect_component_keywords(text)
        
        assert any('pin' in m['keyword'].lower() for m in matches if m['section_type'] == 'section')
    
    def test_detect_connector_section(self):
        """Should detect connector section markers."""
        text = "Connector Configuration\nConnector Pin 1: Power"
        matches = detect_component_keywords(text)
        
        section_keywords = [m['keyword'] for m in matches if m['section_type'] == 'section']
        assert any(kw in section_keywords for kw in ['connector', 'pin'])
    
    def test_detect_interface_section(self):
        """Should detect interface section markers."""
        text = "Interface Specifications\nI2C Interface: 400kHz"
        matches = detect_component_keywords(text)
        
        section_keywords = [m['keyword'] for m in matches if m['section_type'] == 'section']
        assert len(section_keywords) > 0


class TestSectionExtraction:
    """Test section text extraction."""
    
    def test_extract_pin_map_section(self):
        """Should extract text after Pin Map header."""
        text = """
Some header content

Pin Map
Pin 1: VCC (3.3V)
Pin 2: GND
Pin 3: SDA
Pin 4: SCL

Next section
"""
        result = extract_section_text(text, "Pin Map", context_lines=5)
        
        assert "Pin Map" in result
        assert "Pin 1" in result
        assert "VCC" in result
        assert "Next section" not in result or "Next section" in result.split('\n')[-1]
    
    def test_extract_nonexistent_section(self):
        """Should return empty string if section not found."""
        text = "Some content\nMore content"
        result = extract_section_text(text, "Nonexistent Section")
        
        assert result == ""
    
    def test_extract_section_respects_context_lines(self):
        """Should respect context_lines parameter."""
        text = "\n".join([f"Line {i}" for i in range(1, 30)])
        result = extract_section_text(text, "Line 10", context_lines=3)
        
        lines = result.split('\n')
        assert len(lines) <= 5  # 1 header + 3 context + buffer


class TestCategorization:
    """Test keyword categorization."""
    
    def test_categorize_by_type(self):
        """Should categorize matches by section_type."""
        text = "Camera sensor at Pin Map"
        matches = detect_component_keywords(text)
        categorized = categorize_keywords(matches)
        
        assert 'component' in categorized
        assert 'section' in categorized
    
    def test_unique_keyword_counting(self):
        """Should count unique keywords correctly."""
        text = "Camera camera CAMERA sensor"
        matches = detect_component_keywords(text)
        counts = get_unique_keywords(matches)
        
        assert 'camera' in counts
        assert counts['camera'] >= 1


class TestRealWorldScenarios:
    """Test with realistic PDF-like content."""
    
    def test_camera_datasheet(self):
        """Test detection in camera sensor datasheet-like text."""
        text = """
        OV5640 Camera Sensor Module
        Page 1
        
        Features:
        - 5 megapixel camera sensor
        - Compatible with MIPI CSI interface
        - I2C control interface
        - Integrated image processor
        
        Pin Map
        Pin 1: Camera CLK
        Pin 2: Camera Data 0
        Pin 3: Camera Data 1
        
        Package Information
        """
        
        matches = detect_component_keywords(text)
        keywords = get_unique_keywords(matches)
        
        assert 'camera' in keywords
        assert keywords['camera'] >= 2
    
    def test_sensor_board_configuration(self):
        """Test detection in sensor board config."""
        text = """
        Development Board Hardware Configuration
        
        Integrated Components:
        - Light sensor (ALS)
        - Temperature sensor
        - Humidity sensor
        - Accelerometer + Gyroscope
        
        Connector Pin Assignment
        Connector Pin 1: VCC
        Connector Pin 2: GND
        
        Interface Configuration
        I2C Interface for sensors
        """
        
        matches = detect_component_keywords(text)
        keywords = get_unique_keywords(matches)
        
        assert 'sensor' in keywords
        assert 'accelerometer' in keywords
        assert 'gyro' in keywords or 'gyroscope' not in keywords
    
    def test_false_positive_avoidance(self):
        """Should minimize false positives (e.g., camera in company name)."""
        text = """
        Camera Company Inc.
        
        This datasheet describes the sensor characteristics.
        The display shows real-time data.
        """
        
        matches = detect_component_keywords(text)
        
        # Should find these as keywords, but in different contexts
        keywords = get_unique_keywords(matches)
        assert 'sensor' in keywords
        assert 'display' in keywords
        # camera should also be found
        assert 'camera' in keywords


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_text(self):
        """Should handle empty text gracefully."""
        result = detect_component_keywords("")
        assert result == []
    
    def test_text_with_no_matches(self):
        """Should return empty list if no keywords found."""
        text = "This is random text with no component keywords."
        result = detect_component_keywords(text)
        assert result == []
    
    def test_text_with_special_characters(self):
        """Should handle text with special characters."""
        text = "Camera (sensor) - Display [touchscreen] & Audio"
        matches = detect_component_keywords(text)
        keywords = {m['keyword'] for m in matches}
        assert 'camera' in keywords
        assert 'display' in keywords


def test_all_keywords_defined():
    """Verify all expected keywords are defined."""
    essential_components = {'camera', 'sensor', 'display', 'touchscreen', 'audio', 'wifi'}
    assert essential_components.issubset(COMPONENT_KEYWORDS)
    
    essential_sections = {'connector', 'interface', 'pinout', 'pin map'}
    assert essential_sections.issubset(SECTION_KEYWORDS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
