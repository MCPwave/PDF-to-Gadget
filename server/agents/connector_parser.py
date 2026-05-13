"""
Connector Pin Parser for PDFs.

Extracts bus types and pin information from Connector/Interface/Pinout sections.
Infers bus type from pin names and explicit mentions.
"""

import re
from typing import Dict, List, Optional, Tuple


# Bus type inference patterns
BUS_PATTERNS = {
    'MIPI_CSI': {
        'keywords': ['mipi', 'csi', 'camera serial interface'],
        'pin_patterns': [
            r'CSI_D\d+',  # CSI_D0, CSI_D1, etc.
            r'CSI_CLK',
            r'CSI_HS',
            r'CSI_VS',
            r'MIPI_D\d+',
        ]
    },
    'I2C': {
        'keywords': ['i2c', 'i²c', 'iic', 'two-wire', 'twi'],
        'pin_patterns': [
            r'SDA',
            r'SCL',
        ],
        'optional_pins': ['INT', 'ALERT']
    },
    'SPI': {
        'keywords': ['spi', 'serial peripheral interface'],
        'pin_patterns': [
            r'MOSI',
            r'MISO',
            r'CLK',
            r'CS',
        ],
        'optional_pins': ['RESET', 'INT']
    },
    'USB': {
        'keywords': ['usb', 'universal serial bus'],
        'pin_patterns': [
            r'DP|D\+',  # USB D+
            r'DM|D-',   # USB D-
            r'VBUS|VCC|VDD',
            r'GND',
        ]
    },
    'UART': {
        'keywords': ['uart', 'serial', 'rs-232', 'ttl'],
        'pin_patterns': [
            r'TX|TXD',
            r'RX|RXD',
        ],
        'optional_pins': ['RTS', 'CTS', 'DTR', 'DSR']
    },
    'HDMI': {
        'keywords': ['hdmi', 'high-definition multimedia'],
        'pin_patterns': [
            r'D\d+_P',  # D0_P, D1_P, etc.
            r'D\d+_N',  # D0_N, D1_N, etc.
            r'CLK_P|CLKP',
            r'CLK_N|CLKN',
        ]
    },
}


def parse_connector_pins(section_text: str) -> Dict:
    """
    Parse connector/interface section to extract bus type and pin information.
    
    Args:
        section_text: Text block from Connector/Interface/Pinout section
        
    Returns:
        Dict with keys:
        - bus_type: str, inferred bus type (MIPI_CSI, I2C, SPI, USB, UART, HDMI, or 'unknown')
        - pins: List[str], extracted pin names
        - connector_type: str, connector type description (e.g., "50-pin FPC", "standard header")
        - voltage: Optional[str], voltage specification if found (e.g., "3.3V", "5V")
        - confidence: float, confidence score (0-1) based on evidence quality
    """
    if not section_text or not isinstance(section_text, str):
        return {
            'bus_type': 'unknown',
            'pins': [],
            'connector_type': 'unknown',
            'voltage': None,
            'confidence': 0.0
        }
    
    # Extract pins from various formats
    pins = _extract_pins(section_text)
    
    # Infer bus type from pins and keywords
    bus_type, bus_confidence = _infer_bus_type(section_text, pins)
    
    # Extract connector type
    connector_type = _extract_connector_type(section_text)
    
    # Extract voltage
    voltage = _extract_voltage(section_text)
    
    # Calculate overall confidence
    confidence = _calculate_confidence(bus_type, pins, connector_type, voltage, bus_confidence)
    
    return {
        'bus_type': bus_type,
        'pins': pins,
        'connector_type': connector_type,
        'voltage': voltage,
        'confidence': confidence
    }


def _extract_pins(text: str) -> List[str]:
    """
    Extract pin names from various text formats.
    
    Handles:
    - Tables (Pin | Name | Description)
    - Lists (PIN 1: name — description)
    - Inline text (pins CSI_D0, CSI_D1, CSI_D2...)
    - ASCII tables
    - GPIO-style (1: GPIO2, 2: GPIO3, etc.)
    """
    pins = []
    
    # Pattern 1: Table format "Pin 1 | Name | Description" or "Pin | Name"
    table_pattern = r'(?:pin|p)\s+\d+[:\s]+([A-Z0-9_]+(?:\+|-)?)'
    pins.extend(re.findall(table_pattern, text, re.IGNORECASE))
    
    # Pattern 2: Number followed by colon then pin name "1: GPIO2, 2: GPIO3"
    gpio_pattern = r'\d+\s*:\s*([A-Z][A-Z0-9_]*(?:\+|-)?)'
    pins.extend(re.findall(gpio_pattern, text))
    
    # Pattern 3: CSV/List format with pins listed: "SDA, SCL, INT"
    # Look for sequences of 2+ uppercase identifiers separated by commas
    csv_pattern = r'(?:pins?[\s:]*)?([A-Z][A-Z0-9_]*(?:\+|-)?(?:\s*,\s*[A-Z][A-Z0-9_]*(?:\+|-)?)+)'
    csv_matches = re.finditer(csv_pattern, text)
    for match in csv_matches:
        # Split and clean
        csv_list = [p.strip() for p in match.group(1).split(',')]
        # Filter: keep items that look like pin names (2+ chars, mostly uppercase)
        valid_pins = [p for p in csv_list if len(p) >= 2 and p.isupper()]
        pins.extend(valid_pins)
    
    # Pattern 4: Inline descriptive format "CSI_D0: data line"
    inline_pattern = r'([A-Z][A-Z0-9_]*(?:\+|-)?)\s*:(?:\s+[a-z]|\s*\d)'
    pins.extend(re.findall(inline_pattern, text))
    
    # Pattern 5: Pin diagram format with explicit names
    diagram_pattern = r'(?:pad|pin|signal)\s+(?:name|#)?\s*[:\s]*([A-Z][A-Z0-9_]*(?:\+|-)?)'
    pins.extend(re.findall(diagram_pattern, text, re.IGNORECASE))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_pins = []
    for pin in pins:
        pin_upper = pin.upper()
        if pin_upper not in seen:
            seen.add(pin_upper)
            unique_pins.append(pin_upper)
    
    # Filter out common false positives (short generic words)
    false_positives = {'A', 'B', 'C', 'D', 'E', 'F', 'V', 'I', 'O', 'R', 'X', 'Y', 'Z'}
    filtered_pins = [p for p in unique_pins if p not in false_positives and len(p) >= 2]
    
    return filtered_pins


def _infer_bus_type(text: str, pins: List[str]) -> Tuple[str, float]:
    """
    Infer bus type from keywords and pin names.
    
    Returns:
        Tuple of (bus_type, confidence)
    """
    text_lower = text.lower()
    
    # Score each bus type
    scores = {}
    
    for bus_type, patterns in BUS_PATTERNS.items():
        score = 0.0
        
        # Check for explicit keyword mentions (high weight)
        for keyword in patterns['keywords']:
            if keyword in text_lower:
                score += 0.4
        
        # Check for pin pattern matches
        pins_upper = [p.upper() for p in pins]
        pin_matches = 0
        for pin_pattern in patterns['pin_patterns']:
            for pin in pins_upper:
                if re.search(pin_pattern, pin):
                    pin_matches += 1
        
        if pin_matches > 0:
            # Score based on match ratio
            pattern_count = len(patterns['pin_patterns'])
            score += min(0.5, (pin_matches / pattern_count) * 0.5)
        
        # Check for optional pins
        if 'optional_pins' in patterns:
            for opt_pin in patterns['optional_pins']:
                if opt_pin.upper() in pins_upper:
                    score += 0.1
        
        if score > 0:
            scores[bus_type] = score
    
    if not scores:
        return ('unknown', 0.0)
    
    # Get best match
    best_bus = max(scores, key=scores.get)
    confidence = min(1.0, scores[best_bus])
    
    return (best_bus, confidence)


def _extract_connector_type(text: str) -> str:
    """
    Extract connector type from text.
    
    Looks for patterns like:
    - "50-pin FPC connector"
    - "0.1 inch header"
    - "USB Type-C"
    - "standard header"
    - "40-pin dual-row header"
    - "2.54mm pitch header"
    """
    # Pattern: Flexible pin + descriptor + header/connector
    pattern1 = r'(\d+.*?(?:header|connector|fpc))'
    match = re.search(pattern1, text, re.IGNORECASE)
    if match:
        result = match.group(1).strip()
        # Make sure we didn't capture too much (stop at punctuation or next section)
        if len(result) < 100:  # reasonable length limit
            return result
    
    # Pattern: Named connector types
    pattern2 = r'(USB\s+Type[-\-‐–—]?[A-C]|Micro\s+USB|Mini\s+USB|HDMI|DSub|DIN|RJ45)'
    match = re.search(pattern2, text)
    if match:
        return match.group(1).strip()
    
    # Pattern: Pitch + header
    pattern3 = r'((\d+\.?\d*)\s*mm\s+pitch[^.]*(?:header|connector)?)'
    match = re.search(pattern3, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern: Generic connector with descriptor
    pattern4 = r'(0\.1\s+inch\s+header|standard\s+header|edge\s+connector|ribbon\s+connector)'
    match = re.search(pattern4, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return 'unknown'


def _extract_voltage(text: str) -> Optional[str]:
    """
    Extract voltage specification from text.
    
    Looks for patterns:
    - "3.3V"
    - "1.8V IO"
    - "5V"
    - "3V3"
    """
    # Pattern: Voltage in standard formats
    pattern = r'(\d+\.?\d*\s*[Vv](?:\s*[0-9]+)?)'
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    
    # Pattern: 3V3 format
    pattern2 = r'([0-9]V[0-9])'
    match = re.search(pattern2, text)
    if match:
        return match.group(1).strip()
    
    # Pattern: IO voltage
    pattern3 = r'([0-9]+\.?[0-9]*)\s*V\s*(?:IO|power|supply)'
    match = re.search(pattern3, text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}V"
    
    return None


def _calculate_confidence(bus_type: str, pins: List[str], 
                         connector_type: str, voltage: Optional[str],
                         bus_confidence: float) -> float:
    """
    Calculate overall confidence based on evidence.
    """
    if bus_type == 'unknown':
        return 0.0
    
    # Start with bus type confidence
    confidence = bus_confidence
    
    # Add bonus for having pins
    if pins:
        confidence += 0.1 * min(1.0, len(pins) / 5.0)  # Up to +0.1
    
    # Add bonus for known connector type
    if connector_type and connector_type != 'unknown':
        confidence += 0.1
    
    # Add bonus for voltage specification
    if voltage:
        confidence += 0.05
    
    return min(1.0, confidence)
