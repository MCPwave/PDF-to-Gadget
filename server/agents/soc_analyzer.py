"""
SoC Analyzer: Accurately identifies SoCs vs SOMs and extracts underlying SoCs.

ONLY detects and classifies device type. Does NOT include hardware-specific constraints.
Constraints (UART direction, pin multiplexing, etc) are looked up separately via hardware DB.

Distinguishes between:
- Actual SoCs (System-on-Chip): bare silicon
- SOMs (System-on-Module): pre-packaged SoC + support circuitry
"""

import re
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class SoCInfo:
    """Extracted SoC information - DETECTION ONLY."""
    soc_name: str          # Underlying SoC (e.g., "i.MX8M")
    type: str              # "soc" or "som"
    form_factor: str       # "soc", "som", "module", "breakout", "board", "unknown"
    architecture: str      # "arm64", "armhf", "riscv", etc.
    cpu_core: str          # "Cortex-A72", "Cortex-A53", etc.
    confidence: float      # 0.0-1.0


# Pattern: (regex, underlying_soc, form_factor, arch, cpu_core)
# Note: Match SOMs BEFORE bare SoCs to avoid false positives
_DEVICE_PATTERNS = [
    # ===== SYSTEM-ON-MODULE (SOM) Patterns =====
    # NXP i.MX-based SOMs
    (r"(?:i\.MX8[A-Z]|iMX8[A-Z]|IMX8[A-Z])\s*(?:-|based)?\s*(?:SOM|system[- ]?on[- ]?module|module|breakout)", 
     "i.MX8M", "som", "arm64", "Cortex-A53"),
    
    (r"(?:i\.MX9|iMX9|IMX9)\s*(?:-|based)?\s*(?:SOM|system[- ]?on[- ]?module|module)", 
     "i.MX9", "som", "arm64", "Cortex-A55"),
    
    (r"(?:i\.MX6|iMX6|IMX6)\s*(?:-|based)?\s*(?:SOM|system[- ]?on[- ]?module|module)", 
     "i.MX6", "som", "armhf", "Cortex-A9"),
    
    # NVIDIA Jetson SOMs/Modules
    (r"Jetson\s+(?:Orin|Xavier|Nano|TX)\s*(?:NX|AGX|Nano|Module|SOM)", 
     "Tegra Orin", "som", "arm64", "Cortex-A78"),
    
    # STM32 Breakout boards / Modules
    (r"STM32MP\d+\s*(?:-|based)?\s*(?:breakout|module|evaluation|eval|evk)", 
     "STM32MP", "breakout", "armhf", "Cortex-A7"),
    
    # RockChip SOMs
    (r"RK3588\s*(?:-|based)?\s*(?:SOM|module|breakout)", 
     "RK3588", "som", "arm64", "Cortex-A76"),
    
    (r"RK3[5-9]\d{2}\s*(?:-|based)?\s*(?:SOM|module|breakout)", 
     "RK3", "som", "arm64", "Cortex-A55"),
    
    # Allwinner SOMs
    (r"(?:Allwinner|[AH]\d{2,3})\s*(?:-|based)?\s*(?:SOM|module|breakout)", 
     "Allwinner", "som", "arm64", "Cortex-A53"),
    
    # ===== BARE SoC Patterns (match after SOMs to avoid false positives) =====
    # NXP i.MX bare SoCs
    (r"(?:i\.MX|iMX|IMX)\s*8[A-Z](?!\s*(?:SOM|module))", 
     "i.MX8", "soc", "arm64", "Cortex-A53"),
    
    (r"(?:i\.MX|iMX|IMX)\s*9[A-Z](?!\s*(?:SOM|module))", 
     "i.MX9", "soc", "arm64", "Cortex-A55"),
    
    (r"(?:i\.MX|iMX|IMX)\s*[67][A-Z0-9]*(?!\s*(?:SOM|module))", 
     "i.MX", "soc", "armhf", "Cortex-A9"),
    
    # NVIDIA Tegra bare SoCs
    (r"Tegra\s+X\d|T\d{3}[A-Z]?(?!\s*(?:module|som))", 
     "Tegra", "soc", "arm64", "Cortex-A78AE"),
    
    # Jetson Orin bare SoCs
    (r"Jetson\s+Orin(?!\s+(?:NX|AGX|Module|SOM))", 
     "Tegra Orin", "soc", "arm64", "Cortex-A78"),
    
    # RockChip bare SoCs
    (r"RK3588(?!\s*(?:SOM|module))", 
     "RK3588", "soc", "arm64", "Cortex-A76"),
    
    (r"RK3[5-9]\d{2}(?!\s*(?:SOM|module))", 
     "Rockchip RK3", "soc", "arm64", "Cortex-A55"),
    
    # Broadcom
    (r"BCM2\d{3}[A-Z0-9]*(?!\s*(?:SOM|module))", 
     "BCM2835", "soc", "arm64", "Cortex-A72"),
    
    # STM32MP bare SoCs
    (r"STM32MP\d+(?!\s*(?:breakout|module|eval))", 
     "STM32MP", "soc", "armhf", "Cortex-A7"),
    
    # Allwinner bare SoCs
    (r"(?:Allwinner\s+)?[AH]\d{2,3}(?!\s*(?:SOM|module|board))", 
     "Allwinner", "soc", "arm64", "Cortex-A53"),
    
    # TI Sitara SoCs
    (r"(?:TI\s+)?(?:AM\d{4}|AM[67]\d{3})", 
     "TI Sitara", "soc", "arm64", "Cortex-A53"),
]


def detect_soc_or_som(text: str) -> Optional[SoCInfo]:
    """
    Detect SoC or SOM from text.
    
    Prioritizes SOM detection (most specific patterns first) before SoC detection.
    
    Args:
        text: Text to search for SoC/SOM identifiers
    
    Returns:
        SoCInfo with classification, or None if not detected
    """
    if not text:
        return None
    
    for pattern, soc_name, form_factor, arch, cpu_core in _DEVICE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Determine type from form_factor
            device_type = "som" if form_factor in ("som", "module", "breakout") else "soc"
            
            return SoCInfo(
                soc_name=soc_name,
                type=device_type,
                form_factor=form_factor,
                architecture=arch,
                cpu_core=cpu_core,
                confidence=0.95
            )
    
    return None


def classify_device(text: str) -> Dict[str, any]:
    """
    Full classification of device from PDF text.
    
    Returns:
        {
            'soc': str,                    # Underlying SoC (e.g., "i.MX8M")
            'type': str,                   # "soc" or "som"
            'form_factor': str,            # "soc", "som", "module", etc.
            'architecture': str,
            'cpu_core': str,
            'confidence': float,
        }
    """
    result = {
        'soc': None,
        'type': None,
        'form_factor': None,
        'architecture': None,
        'cpu_core': None,
        'confidence': 0.0,
    }
    
    info = detect_soc_or_som(text)
    if info:
        result.update({
            'soc': info.soc_name,
            'type': info.type,
            'form_factor': info.form_factor,
            'architecture': info.architecture,
            'cpu_core': info.cpu_core,
            'confidence': info.confidence,
        })
    
    return result
