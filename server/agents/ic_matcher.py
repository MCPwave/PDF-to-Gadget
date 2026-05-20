"""
IC Matcher: Recognizes known component ICs from PDF text.

Scans text for known camera, sensor, display ICs and infers their
connection types based on context and datasheet defaults.
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class ICMatch:
    """Matched IC with metadata."""
    ic_name: str
    component_type: str
    connection_type: str
    context: str
    confidence: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


# Known component ICs from kernel_scout driver DB
_KNOWN_COMPONENTS = {
    # (ic_name) -> (component_type, default_connection)
    "ov5647": ("camera_sensor", "mipi_csi"),
    "imx219": ("camera_sensor", "mipi_csi"),
    "imx477": ("camera_sensor", "mipi_csi"),
    "econ200": ("camera_module", "mipi_csi"),
    "ar0521": ("camera_sensor", "mipi_csi"),
    "ar2020": ("camera_sensor", "mipi_csi"),
    "ili9341": ("display", "spi"),
    "st7789": ("display", "spi"),
    "st7735": ("display", "spi"),
    "uc8159": ("display", "spi"),
    "ft5406": ("touchscreen", "i2c"),
    "edt-ft5x06": ("touchscreen", "i2c"),
    "goodix": ("touchscreen", "i2c"),
    "tmp36": ("sensor_temperature", "i2c"),
    "bmp280": ("sensor_temperature", "i2c"),
    "mpu6050": ("sensor_accelerometer", "i2c"),
    "lsm6dsm": ("sensor_accelerometer", "i2c"),
    "apds9960": ("sensor_proximity", "i2c"),
    "bh1750": ("sensor_light", "i2c"),
    "axp209": ("pmic", "i2c"),
    "tps65217": ("pmic", "i2c"),
    "ads1015": ("adc", "i2c"),
    "ads1115": ("adc", "i2c"),
    "mcp3008": ("adc", "spi"),
    "mcp3208": ("adc", "spi"),
    "pcf8574": ("gpio_expander", "i2c"),
    "mcp23017": ("gpio_expander", "i2c"),
    "mcp23008": ("gpio_expander", "i2c"),
    "ds1307": ("rtc", "i2c"),
    "pcf8563": ("rtc", "i2c"),
    "apa102": ("led", "spi"),
    "ws2812": ("led", "spi"),
    # Accelerators & Processors
    "tpu": ("tpu", "pcie"),
    "coral": ("npu", "usb"),
    "tpu_v2": ("tpu", "pcie"),
    "tpu_v3": ("tpu", "pcie"),
    "tpu_v4": ("tpu", "pcie"),
    "npu": ("npu", "pcie"),
    "gpu": ("gpu", "pcie"),
    "vpu": ("npu", "pcie"),
    "dsp": ("dsp", "local"),
    "cpu": ("cpu", "local"),
    # Audio components
    "rt5651": ("audio", "i2c"),
    "rt5640": ("audio", "i2c"),
    "wm8960": ("audio", "i2c"),
    "da7213": ("audio", "i2c"),
    "ssm3515": ("audio", "i2c"),
    "realtek": ("audio", "i2c"),
    "cirrus": ("audio", "i2c"),
    # Security/TPM components
    "tpm2": ("security", "i2c"),
    "tpm1.2": ("security", "i2c"),
    "se050": ("security", "i2c"),
    "tpm_infineon": ("security", "i2c"),
    "tpm_st": ("security", "i2c"),
    # Power management
    "axp803": ("power", "i2c"),
    "axp809": ("power", "i2c"),
    "max77686": ("power", "i2c"),
    "bd71847": ("power", "i2c"),
    "pf8100": ("power", "i2c"),
    # Watchdog
    "wdt": ("watchdog", "i2c"),
}

# Connection type keywords for context inference
_CONNECTION_KEYWORDS = {
    "mipi_csi": [r"\bmipi\b", r"\bcsi\b", r"\bcsi-2\b"],
    "i2c": [r"\bi2c\b", r"\biic\b", r"\btwi\b"],
    "spi": [r"\bspi\b", r"\b3-wire\b", r"\b4-wire\b"],
    "usb": [r"\busb\b", r"\buvc\b"],
    "uart": [r"\buart\b", r"\bserial\b", r"\brs-232\b"],
    "gpio": [r"\bgpio\b", r"\bdigital\b"],
    "hdmi": [r"\bhdmi\b"],
    "dsi": [r"\bdsi\b", r"\bdisplay serial\b"],
}


def _build_ic_regex(ic_names: List[str]) -> re.Pattern:
    """Build regex pattern matching any of the IC names (case-insensitive).

    Handles special characters in names like dashes, numbers.
    """
    # Escape special regex characters and sort by length (longest first)
    # to match longer names before shorter substrings
    escaped = sorted(
        [re.escape(name) for name in ic_names],
        key=len,
        reverse=True
    )
    pattern = "|".join(escaped)
    return re.compile(f"({pattern})", re.IGNORECASE)


def _extract_context(text: str, match_start: int, match_end: int, window: int = 100) -> str:
    """Extract surrounding context around match position."""
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    context = text[start:end].strip()
    # Clean up whitespace
    context = " ".join(context.split())
    return context


def _infer_connection_type(context: str, ic_name: str, defaults: Dict[str, str]) -> tuple[str, float]:
    """Infer connection type from context or use defaults.

    Returns (connection_type, confidence_boost)
    """
    context_lower = context.lower()

    # Check for explicit connection keywords in context
    for conn_type, keywords in _CONNECTION_KEYWORDS.items():
        for pattern in keywords:
            if re.search(pattern, context_lower):
                return (conn_type, 0.2)  # Found in context: +0.2 confidence

    # Fall back to default connection type from DB
    if ic_name in defaults:
        return (defaults[ic_name], 0.0)  # Default: no confidence boost

    return ("unknown", 0.0)


def _calculate_confidence(
    found_in_context: bool,
    connection_explicit: bool,
    has_default: bool
) -> float:
    """Calculate confidence score.

    - High (0.9): IC name + connection type both in context
    - Medium (0.7): IC name found, connection type inferred from defaults
    - Low (0.5): IC name found, no connection type info
    """
    if found_in_context and connection_explicit:
        return 0.9
    elif found_in_context and has_default:
        return 0.7
    else:
        return 0.5


def match_component_ics(pdf_text: str) -> List[ICMatch]:
    """Match known component ICs in PDF text.

    Scans PDF text for known camera, sensor, display ICs and extracts:
    - IC name, component type
    - Surrounding context (100 chars each side)
    - Estimated connection type from context or defaults
    - Confidence score

    Args:
        pdf_text: Text extracted from PDF

    Returns:
        List of ICMatch objects with metadata
    """
    if not pdf_text:
        return []

    matches = []
    ic_names = list(_KNOWN_COMPONENTS.keys())
    ic_regex = _build_ic_regex(ic_names)

    # Track unique matches to avoid duplicates
    seen = set()

    for match in ic_regex.finditer(pdf_text):
        ic_name = match.group(1).lower()
        match_start = match.start()
        match_end = match.end()

        # Avoid duplicate matches at same position
        position_key = (ic_name, match_start)
        if position_key in seen:
            continue
        seen.add(position_key)

        # Get IC metadata
        component_type, default_conn = _KNOWN_COMPONENTS[ic_name]

        # Extract context
        context = _extract_context(pdf_text, match_start, match_end, window=100)

        # Infer connection type
        connection_type, conn_confidence = _infer_connection_type(
            context,
            ic_name,
            {ic_name: default_conn}
        )

        # Calculate confidence
        found_in_context = True  # We found it via regex
        connection_explicit = conn_confidence > 0  # Found keywords
        has_default = True  # All components have defaults

        base_confidence = 0.7 if connection_explicit else 0.5
        confidence = min(0.9, base_confidence + conn_confidence)

        matches.append(
            ICMatch(
                ic_name=ic_name,
                component_type=component_type,
                connection_type=connection_type,
                context=context,
                confidence=confidence
            )
        )

    # Sort by position in text for better readability
    return sorted(matches, key=lambda m: pdf_text.find(m.ic_name, 0))


def match_component_ics_with_positions(pdf_text: str) -> List[Dict]:
    """Match ICs and return with original text positions.

    Useful for highlighting or precise mapping.

    Returns:
        List of dicts with ICMatch data plus 'position' key
    """
    if not pdf_text:
        return []

    results = []
    ic_names = list(_KNOWN_COMPONENTS.keys())
    ic_regex = _build_ic_regex(ic_names)
    seen = set()

    for match in ic_regex.finditer(pdf_text):
        ic_name = match.group(1).lower()
        match_start = match.start()
        match_end = match.end()

        position_key = (ic_name, match_start)
        if position_key in seen:
            continue
        seen.add(position_key)

        component_type, default_conn = _KNOWN_COMPONENTS[ic_name]
        context = _extract_context(pdf_text, match_start, match_end, window=100)
        connection_type, conn_confidence = _infer_connection_type(
            context,
            ic_name,
            {ic_name: default_conn}
        )

        base_confidence = 0.7 if conn_confidence > 0 else 0.5
        confidence = min(0.9, base_confidence + conn_confidence)

        result_dict = {
            "ic_name": ic_name,
            "component_type": component_type,
            "connection_type": connection_type,
            "context": context,
            "confidence": confidence,
            "position": (match_start, match_end),
        }
        results.append(result_dict)

    return results


if __name__ == "__main__":
    # Test the IC matcher
    test_texts = [
        "The OV5647 camera sensor uses MIPI CSI for data transmission.",
        "Display controller ili9341 communicates via SPI interface.",
        "Temperature sensor tmp36 is connected through I2C bus.",
        "The board includes both IMX219 and BMP280 components.",
        "Unknown sensor XYZ123 should not match.",
        "case insensitive: ST7789 display and OV5647 camera.",
    ]

    print("Testing IC Matcher\n" + "=" * 50)
    for i, text in enumerate(test_texts, 1):
        print(f"\nTest {i}: {text}")
        matches = match_component_ics(text)
        if matches:
            for match in matches:
                print(f"  ✓ Found {match.ic_name} ({match.component_type})")
                print(f"    Connection: {match.connection_type} (confidence: {match.confidence})")
                print(f"    Context: ...{match.context[-80:]}...")
        else:
            print("  (no matches)")
