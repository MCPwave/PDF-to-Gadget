"""
Generic IC Extractor: Extracts ANY IC/component from PDF text.

Works with unknown ICs not in the hardcoded database.
- Detects component type from keywords (camera, sensor, display, etc.)
- Extracts IC model numbers (any format)
- Infers connection types from context
- Looks up drivers if IC is known, otherwise marks as "unknown"
"""

import re
from typing import List, Dict, Tuple, Optional


# Generic patterns for IC/component model numbers (not specific ICs)
# Focused on real IC patterns, not numbers from text
_MODEL_PATTERNS = [
    r'\b([A-Z]{2,3}\d{3,5}[A-Z]?)\b',  # AR2020, OV5647, IMX219, BMP280 (strict word boundaries)
    r'\b(EDT-FT5[X\d]{2,3})\b',        # EDT-FT5X06 (touchscreen)
    r'\b([A-Z]{2,3}[89]\d{3})\b',      # Sensor/driver ICs
]

# Component type detection keywords
_COMPONENT_TYPES = {
    'camera': [
        r'\bcamera\b', r'\bimage\s*sensor\b', r'\bcmos\s*sensor\b',
        r'\bcamera\s*module\b', r'\bcamera\s*ic\b', r'\boptical\s*sensor\b',
        r'\bvideo\s*sensor\b', r'\bimage\s*sensor\b', r'\bphotograph',
        r'\bwebcam\b', r'\bweb\s*camera\b', r'\bipu\b', r'\bipu\d+\b',
        r'\bwindows\s*hello\b', r'\b1080p\b', r'\bfhd\b', r'\b4k\b', r'\b2k\b',
        r'\bintel\s*ipu\b', r'\bqualcomm\s*isp\b', r'\bimage\s*processor\b',
    ],
    'display': [
        r'\bdisplay\b', r'\blcd\b', r'\boled\b', r'\bscreen\b',
        r'\bpanel\b', r'\blcd\s*controller\b', r'\bvideo\s*driver\b',
        r'\bgraphics\s*controller\b',
    ],
    'touchscreen': [
        r'\btouch\s*screen\b', r'\btouch\s*panel\b', r'\btouch\s*controller\b',
        r'\bcapacitive\s*touch\b', r'\bresistive\s*touch\b',
    ],
    'sensor_temperature': [
        r'\btemperature\s*sensor\b', r'\btemp\s*sensor\b',
        r'\bthermal\s*sensor\b', r'\bthermistor\b',
    ],
    'sensor_accelerometer': [
        r'\baccelerometer\b', r'\bgyroscope\b', r'\bimu\b',
        r'\binertial\s*measurement\b', r'\b6-?axis\b', r'\b9-?axis\b',
    ],
    'sensor_proximity': [
        r'\bproximity\s*sensor\b', r'\bdistance\s*sensor\b',
        r'\btime-?of-?flight\b', r'\btof\b', r'\bmotion\s*sensor\b',
    ],
    'sensor_light': [
        r'\blight\s*sensor\b', r'\bals\b', r'\bambient\s*light\b',
        r'\bphotodiode\b', r'\billuminance\b',
    ],
    'sensor_humidity': [
        r'\bhumidity\s*sensor\b', r'\bhumidity\b', r'\brh\b',
    ],
    'sensor_pressure': [
        r'\bpressure\s*sensor\b', r'\bbarometer\b',
    ],
    'sensor_motion': [
        r'\bmotion\s*sensor\b', r'\bpir\b', r'\binfrared\s*motion\b',
    ],
    'pmic': [
        r'\bpmic\b', r'\bpower\s*management\b', r'\bregulator\b',
        r'\bdc-?dc\b', r'\bldo\b', r'\bchip\s*set\b',
    ],
    'adc': [
        r'\badc\b', r'\banalog\s*converter\b', r'\b16-?bit\b',
        r'\b12-?bit\b', r'\b8-?bit\b', r'\bconverter\b',
    ],
    'gpio_expander': [
        r'\bgpio\s*expander\b', r'\bportexpander\b', r'\bport\s*expander\b',
        r'\bi2c\s*expander\b', r'\bspi\s*expander\b',
    ],
    'rtc': [
        r'\brtc\b', r'\breal\s*time\s*clock\b', r'\bclock\s*module\b',
    ],
    'led': [
        r'\bled\s*driver\b', r'\bled\s*controller\b', r'\brgb\s*led\b',
        r'\bws2812\b', r'\baya102\b', r'\baddressable\s*led\b',
    ],
    'npu': [
        r'\bnpu\b', r'\bneural\s*processing\s*unit\b',
        r'\bcoral\b', r'\btpu\b(?!v\d)', r'\baccelerator\b',
        r'\bnvdla\b', r'\bkhan\b', r'\bvpu\b',
    ],
    'gpu': [
        r'\bgpu\b', r'\bgraphics\s*processing\s*unit\b',
        r'\badreno\b', r'\bmali\b', r'\bpowervr\b', r'\bvivante\b',
        r'\bgc\d{3,4}\b', r'\bgpgpu\b',
    ],
    'tpu': [
        r'\btpu\b', r'\btensor\s*processing\s*unit\b',
        r'\bv\d\b', r'\bedge\s*tpu\b',
    ],
    'cpu': [
        r'\bcpu\s*core\b', r'\bprocessor\s*core\b', r'\bcortex\b',
        r'\barm\s*cpu\b', r'\bx86\b', r'\bx86_64\b',
    ],
    'dsp': [
        r'\bdsp\b', r'\bdigital\s*signal\s*processor\b',
        r'\bhexagon\b', r'\bc6x\b', r'\bc7x\b',
    ],
    'accelerator': [
        r'\baccelerator\b', r'\bhardware\s*acceleration\b',
        r'\bvpu\b', r'\bio\s*accelerator\b',
    ],
    'audio': [
        r'\baudio\s*codec\b', r'\baudio\s*processor\b', r'\bsound\b',
        r'\bamp\b', r'\bamplifier\b', r'\baudio\s*driver\b',
        r'\bmic\b', r'\bmicrophone\b', r'\bspeaker\b', r'\bdac\s*audio\b',
    ],
    'security': [
        r'\btpm\b', r'\btrusted\s*platform\s*module\b',
        r'\bsecure\s*element\b', r'\bsecurity\s*processor\b',
        r'\bcrypto\b', r'\bencryption\b', r'\bse050\b',
        r'\bse\d{3}\b', r'\bhmac\b', r'\brng\b', r'\brandom\s*number\b',
    ],
    'power': [
        r'\bac\s*adapter\b', r'\bpower\s*supply\b', r'\bpsu\b',
        r'\bbattery\s*management\b', r'\bcharger\b', r'\busb\s*pd\b',
        r'\bpower\s*delivery\b', r'\bpowerbank\b',
    ],
    'acpi': [
        r'\bacpi\b', r'\badvanced\s*configuration\b',
        r'\bpower\s*interface\b', r'\bfadt\b', r'\bdsdt\b',
        r'\bssdt\b', r'\baml\b',
    ],
    'watchdog': [
        r'\bwatchdog\b', r'\bwdt\b', r'\btimer\b',
    ],
    'ipu': [
        r'\bipu\b', r'\bipu\d+\b', r'\bimage\s*processing\s*unit\b',
        r'\bintel\s*ipu\b', r'\bqualcomm\s*isp\b', r'\bvivid\b',
        r'\bisp\b', r'\bimage\s*signal\s*processor\b',
    ],
}

# Connection type keywords
_CONNECTION_KEYWORDS = {
    'mipi_csi': [r'\bmipi\b', r'\bcsi\b', r'\bcsi-?2\b', r'\bcamera\s*serial\b'],
    'dsi': [r'\bdsi\b', r'\bdisplay\s*serial\b'],
    'i2c': [r'\bi2c\b', r'\biic\b', r'\btwi\b', r'\bsmbus\b'],
    'spi': [r'\bspi\b', r'\b3-?wire\b', r'\b4-?wire\b', r'\bssp\b'],
    'usb': [r'\busb\b', r'\buvc\b', r'\busb\s*device\b'],
    'uart': [r'\buart\b', r'\bserial\b', r'\brs-?232\b', r'\brs-?485\b'],
    'gpio': [r'\bgpio\b', r'\bdigital\b', r'\bgeneral\s*purpose\b'],
    'hdmi': [r'\bhdmi\b'],
    'ethernet': [r'\bethernet\b', r'\brj45\b'],
    'can': [r'\bcan\b', r'\bcontroller\s*area\b'],
    'pcie': [r'\bpcie\b', r'\bpci\s*express\b', r'\bpci-?e\b'],
    'local': [r'\blocal\b', r'\bintegrated\b', r'\bon-?chip\b', r'\binternal\b'],
}


def detect_component_type(text: str) -> Tuple[str, float]:
    """Detect component type from PDF text.
    
    Returns (component_type, confidence) tuple.
    Confidence 0-1.0 indicates how confident the match is.
    """
    text_lower = text.lower()
    best_match = None
    best_confidence = 0.0
    
    for comp_type, keywords in _COMPONENT_TYPES.items():
        matches = 0
        for kw_pattern in keywords:
            if re.search(kw_pattern, text_lower, re.IGNORECASE):
                matches += 1
        
        if matches > 0:
            # More keyword matches = higher confidence
            confidence = min(1.0, matches / len(keywords))
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = comp_type
    
    return (best_match or "unknown_component", best_confidence)


def extract_ic_models(text: str) -> List[Dict]:
    """Extract potential IC model numbers from text.
    
    Returns list of detected models with context.
    """
    models = []
    seen = set()
    
    for pattern in _MODEL_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            ic_name = match.group(1).upper()
            
            # Avoid duplicates and too-generic matches
            if ic_name in seen or len(ic_name) < 3:
                continue
            
            seen.add(ic_name)
            
            # Extract context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()
            context = " ".join(context.split())
            
            models.append({
                'ic_name': ic_name,
                'context': context,
                'position': match.start(),
                'confidence': 0.7,  # Default confidence for unknown ICs
            })
    
    # Sort by position
    models.sort(key=lambda x: x['position'])
    return models


def infer_connection_type(text: str, ic_name: str = "") -> Tuple[str, float]:
    """Infer connection type from context.
    
    Uses both explicit keywords and IC defaults.
    Returns (connection_type, confidence).
    """
    best_match = None
    best_confidence = 0.0
    
    for conn_type, keywords in _CONNECTION_KEYWORDS.items():
        for kw_pattern in keywords:
            if re.search(kw_pattern, text, re.IGNORECASE):
                confidence = 0.8
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = conn_type
    
    # Fallback: infer from IC name patterns
    if not best_match:
        ic_lower = ic_name.lower()
        if any(x in ic_lower for x in ['ar', 'ov', 'imx']):
            best_match = 'mipi_csi'
            best_confidence = 0.5
        elif any(x in ic_lower for x in ['ili', 'st7', 'uc8']):
            best_match = 'spi'
            best_confidence = 0.5
        elif any(x in ic_lower for x in ['ft5', 'goodix']):
            best_match = 'i2c'
            best_confidence = 0.5
    
    return (best_match or "unknown", best_confidence or 0.3)


def extract_generic_components(pdf_text: str) -> List[Dict]:
    """Extract ANY component from PDF (known or unknown).
    
    Returns list of detected components with all inferred metadata.
    """
    components = []
    
    # Get overall component type (fallback)
    comp_type, comp_confidence = detect_component_type(pdf_text)
    
    # Extract IC models
    models = extract_ic_models(pdf_text)
    
    if not models:
        # No specific ICs found, but component type detected
        if comp_type != "unknown_component":
            return [{
                'ic_name': f'Generic {comp_type}'.replace('_', ' ').title(),
                'component_type': comp_type,
                'connection_type': infer_connection_type(pdf_text)[0],
                'context': 'Detected from PDF content',
                'confidence': comp_confidence,
                'source': 'heuristic',
            }]
        return []
    
    # Build components from extracted models
    for model in models:
        ic_name = model['ic_name']
        context = model['context']
        
        # Infer type from LOCAL context (the text around the IC)
        inferred_type, type_conf = detect_component_type(context)
        
        # If local context doesn't detect type well, try broader scope
        if type_conf < 0.4:
            # Look for component type keywords in broader area
            broader_start = max(0, model['position'] - 500)
            broader_end = min(len(pdf_text), model['position'] + 500)
            broader_context = pdf_text[broader_start:broader_end]
            inferred_type, type_conf = detect_component_type(broader_context)
        
        inferred_conn, conn_conf = infer_connection_type(context, ic_name)
        
        # Use detected type if high confidence, else fallback
        final_type = inferred_type if type_conf > 0.4 else comp_type
        
        components.append({
            'ic_name': ic_name,
            'component_type': final_type,
            'connection_type': inferred_conn,
            'context': context,
            'confidence': model['confidence'],
            'type_confidence': type_conf,
            'conn_confidence': conn_conf,
            'source': 'extracted',
        })
    
    return components


if __name__ == "__main__":
    # Test
    test_text = """
    AR2020 Image Sensor
    The AR2020 is a 20MP CMOS image sensor with MIPI CSI-2 interface.
    It connects via a 4-lane MIPI CSI-2 connector.
    
    ST7789 Display Controller
    Supports SPI interface (3-wire or 4-wire mode).
    
    BMP280 Pressure Sensor
    I2C address 0x77.
    """
    
    comps = extract_generic_components(test_text)
    for c in comps:
        print(f"IC: {c['ic_name']}")
        print(f"  Type: {c['component_type']} (conf: {c['type_confidence']:.0%})")
        print(f"  Connection: {c['connection_type']} (conf: {c['conn_confidence']:.0%})")
        print()
