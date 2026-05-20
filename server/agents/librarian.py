"""
@librarian — Hardware Librarian Agent
Extracts SoC details, peripherals, pinmux, and power rails from datasheet text.
Supports internet enrichment via Wikipedia API and a built-in SoC knowledge base.

LLM priority order:
  1. Ollama  (local)       — OLLAMA_HOST (default: http://localhost:11434)
  2. LM Studio (local)     — LM_STUDIO_HOST (default: http://localhost:1234)
  3. Cloud providers       — OpenAI / Anthropic / Gemini / Groq / Mistral / OpenRouter
  4. Heuristic regex       — always available, no key needed
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

# Import extraction modules for component detection
try:
    from component_extractor import detect_component_keywords
except ImportError:
    detect_component_keywords = None

try:
    from ic_matcher import match_component_ics
except ImportError:
    match_component_ics = None

try:
    from connector_parser import parse_connector_pins
except ImportError:
    parse_connector_pins = None

try:
    from soc_analyzer import classify_device
except ImportError:
    classify_device = None

try:
    from llm_component_detector import detect_components_with_llm, format_components_for_pipeline
except ImportError:
    detect_components_with_llm = None
    format_components_for_pipeline = None

# ── Shared prompt builder ──────────────────────────────────────────────────────

_PERIPHERAL_TYPES = (
    "i2c|spi|uart|usart|gpio|pwm|usb|ethernet|can|can_fd|hdmi|displayport|"
    "mipi_dsi|mipi_csi|camera|lvds|pcie|sata|emmc|sd|sdio|i2s|sai|audio|"
    "adc|dac|jtag|swd|rtc|watchdog|qspi|flexcan|flexspi|lpspi|lpi2c|lpuart|"
    "rgb|parallel_lcd|touch|nand|nor_flash|hyperflash|other"
)

# ── Component connection types and validation ──────────────────────────────────
_VALID_CONNECTION_TYPES = {
    "mipi_csi", "mipi_dsi", "i2c", "spi", "usb", "uart", "gpio",
    "hdmi", "displayport", "lvds", "pcie", "sata", "eth", "can",
    "i2s", "audio", "usart", "qspi", "touchscreen_i2c", "touchscreen_spi"
}

_COMPONENT_IC_TYPES = {
    "camera_sensor", "display", "touchscreen", "audio_codec", "amplifier",
    "accelerometer", "gyroscope", "magnetometer", "temperature_sensor",
    "humidity_sensor", "pressure_sensor", "proximity_sensor", "light_sensor",
    "motion_sensor", "humidity_sensor", "compass", "gps", "modem", "nfc",
    "bluetooth", "wifi", "microphone", "speaker", "regulator", "pmic"
}

# ── Section type classifier ────────────────────────────────────────────────────

_SECTION_SIGNALS: dict[str, list[str]] = {
    "overview":   ["feature", "highlight", "overview", "introduction", "block diagram",
                   "processor", "architecture", "soc ", "cpu ", "description", "application"],
    "peripheral": ["uart", "usart", "spi", "i2c", "i2s", "usb", "ethernet", "emac", "can",
                   "hdmi", "dsi", "csi", "pcie", "sata", "emmc", "sdio", "gpio", "adc", "dac",
                   "pwm", "interface", "controller", "peripheral", "qspi", "flexspi"],
    "pinmux":     ["pin ", "gpio", "mux", "alt function", "pullup", "pulldown", "pad",
                   "iomux", "pinctrl", "signal name", "ball ", "pin number"],
    "register":   ["register", "0x", " rw ", " ro ", " wo ", "bit field", "offset",
                   "base address", "memory map", "address map"],
    "power":      ["voltage", " mv", " ma", "ldo", "pmic", "power rail", "vcc", "vdd",
                   "regulator", "buck", "power supply", "sequencing"],
}

def _classify_section(text: str) -> str:
    t = text.lower()
    scores = {stype: sum(t.count(kw) for kw in kws)
              for stype, kws in _SECTION_SIGNALS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "general"


# ── Prompt builders ────────────────────────────────────────────────────────────

def _overview_prompt(text: str) -> str:
    excerpt = text[:6000]
    return f"""You are @librarian, a hardware engineer. This is the OVERVIEW/FEATURES section of a datasheet.

Extract board identity and list ALL interfaces/peripherals mentioned.
Return ONLY valid JSON:
{{
  "board": "<Full product name, e.g. 'Raspberry Pi 4 Model B'. null if not clear>",
  "soc": "<Exact SoC part number e.g. 'BCM2711', 'RK3588S', 'i.MX 8M Plus'>",
  "arch": "<arm64 | armhf | amd64 | riscv64 | mips>",
  "cpu_core": "<e.g. 'Cortex-A72'. null if unknown>",
  "cpu_count": <integer or null>,
  "cpu_freq_mhz": <integer MHz or null>,
  "ram_mb": <integer MB or null>,
  "peripherals": [
    {{"id":"<snake_case>","name":"<name>","type":"<{_PERIPHERAL_TYPES}>",
      "bus":"<bus label>","address":null,"irq":null,
      "description":"<one line>","voltage":"3.3V","regulator":"vcc-3v3"}}
  ],
  "power_rails": []
}}

Rules: list every interface found; return ONLY JSON; no markdown.

Section:
{excerpt}"""


def _peripheral_prompt(text: str, heading: str) -> str:
    excerpt = text[:6000]
    return f"""You are @librarian. This is the "{heading}" section of a hardware datasheet.

Extract EVERY hardware interface or peripheral described. Include ALL numbered instances.
Return ONLY valid JSON:
{{
  "peripherals": [
    {{"id":"<snake_case>","name":"<name>","type":"<{_PERIPHERAL_TYPES}>",
      "bus":"<bus label e.g. I2C0, SPI1, UART3>","address":"<0x... or null>","irq":null,
      "description":"<one line>","voltage":"3.3V","regulator":"vcc-3v3"}}
  ]
}}

Look for: UARTs, SPIs, I2Cs, USBs, Ethernet ports, CAN buses, HDMI, DSI, CSI cameras,
PCIe, SATA, eMMC, SD/SDIO, I2S/audio, ADC/DAC channels, PWM outputs, GPIO banks, JTAG/SWD.
Return ONLY JSON, no text outside the object.

Section:
{excerpt}"""


def _register_prompt(text: str, heading: str) -> str:
    excerpt = text[:6000]
    return f"""You are @librarian. This is the "{heading}" memory map / register section.

Extract peripheral base addresses. Return ONLY valid JSON:
{{
  "peripherals": [
    {{"id":"<snake_case>","name":"<name>","type":"<{_PERIPHERAL_TYPES}>",
      "bus":"","address":"<0x...>","irq":null,
      "description":"<one line>","voltage":"3.3V","regulator":"vcc-3v3"}}
  ]
}}

Only include entries with a hex base address (0x...). Return ONLY JSON.

Section:
{excerpt}"""


def _power_prompt(text: str) -> str:
    excerpt = text[:6000]
    return f"""You are @librarian. This is the power management section of a hardware datasheet.

Extract ALL power rails/regulators. Return ONLY valid JSON:
{{
  "power_rails": [
    {{"name":"<rail name e.g. vcc-3v3>","voltage":"<e.g. 3.3V>",
      "current_ma":null,"supplies":[]}}
  ]
}}

Return ONLY JSON, no markdown, no text outside the object.

Section:
{excerpt}"""


def _pinmux_prompt(text: str, heading: str) -> str:
    excerpt = text[:6000]
    return f"""You are @librarian. This is the "{heading}" pin/signal description section.

Extract GPIO banks and named signal groups as peripherals. Return ONLY valid JSON:
{{
  "peripherals": [
    {{"id":"<snake_case>","name":"<name>","type":"gpio",
      "bus":"<GPIO bank e.g. GPIOA>","address":null,"irq":null,
      "description":"<what signals>","voltage":"3.3V","regulator":"vcc-3v3"}}
  ]
}}

Return ONLY JSON.

Section:
{excerpt}"""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


# ── Component validation ───────────────────────────────────────────────────────

def _validate_component(peripheral: dict, board_buses: set) -> tuple[bool, list[str]]:
    """
    Validate a component peripheral entry.
    Returns (is_valid, errors) tuple.
    """
    errors = []
    
    if not peripheral.get("is_component"):
        return True, []
    
    # Components must have connection_type
    conn_type = peripheral.get("connection_type", "").strip()
    if not conn_type:
        errors.append(f"Component {peripheral.get('id', '?')}: missing connection_type")
    elif conn_type not in _VALID_CONNECTION_TYPES:
        errors.append(
            f"Component {peripheral.get('id', '?')}: unknown connection_type '{conn_type}' "
            f"(valid: {', '.join(sorted(_VALID_CONNECTION_TYPES))})"
        )
    
    # Components must have connector info
    connector = peripheral.get("connector", {})
    if not connector:
        errors.append(f"Component {peripheral.get('id', '?')}: missing connector info")
    else:
        if "voltage" not in connector:
            errors.append(f"Component {peripheral.get('id', '?')}: connector missing voltage")
        
        required_iface = connector.get("required_board_interface") or ""
        required_iface = required_iface.strip() if required_iface else ""
        if required_iface and required_iface not in board_buses:
            errors.append(
                f"Component {peripheral.get('id', '?')}: required board interface '{required_iface}' "
                f"not found on board (available: {', '.join(sorted(board_buses))})"
            )
    
    # Components should have component_ic info
    component_ic = peripheral.get("component_ic", {})
    if not component_ic:
        errors.append(f"Component {peripheral.get('id', '?')}: missing component_ic info")
    else:
        ic_type = component_ic.get("type", "").strip()
        if ic_type and ic_type not in _COMPONENT_IC_TYPES:
            errors.append(
                f"Component {peripheral.get('id', '?')}: unknown IC type '{ic_type}' "
                f"(valid: {', '.join(sorted(_COMPONENT_IC_TYPES))})"
            )
    
    return len(errors) == 0, errors


def _separate_components(peripherals: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Separate board peripherals from components.
    Returns (board_peripherals, components).
    """
    board_perips = []
    components = []
    
    for p in peripherals:
        if isinstance(p, dict) and p.get("is_component", False):
            components.append(p)
        else:
            board_perips.append(p)
    
    return board_perips, components


def _merge_hw_maps(base: dict, extra: dict) -> dict:
    """Merge two hw_maps: prefer non-null scalars from extra, union peripherals/rails."""
    result = dict(base)
    for key in ("board", "soc", "arch", "cpu_core", "cpu_count", "cpu_freq_mhz", "ram_mb"):
        if not result.get(key) and extra.get(key):
            result[key] = extra[key]
    existing_ids = {p["id"] for p in result.get("peripherals", []) if "id" in p}
    for p in extra.get("peripherals", []):
        pid = p.get("id", "")
        if pid and pid not in existing_ids:
            result.setdefault("peripherals", []).append(p)
            existing_ids.add(pid)
        elif pid in existing_ids:
            # enrich existing with address if we now have one
            if p.get("address"):
                for ep in result["peripherals"]:
                    if ep.get("id") == pid and not ep.get("address"):
                        ep["address"] = p["address"]
    existing_rails = {r["name"] for r in result.get("power_rails", []) if "name" in r}
    for r in extra.get("power_rails", []):
        if r.get("name") and r["name"] not in existing_rails:
            result.setdefault("power_rails", []).append(r)
            existing_rails.add(r["name"])
    return result


# ── Component Extraction ──────────────────────────────────────────────────────────

def extract_components_from_pdf(pdf_text: str) -> list[dict]:
    """
    Extract components (ICs, sensors, peripherals) from PDF text.
    
    Extraction priority (tries in order):
    1. LLM detection (if available) — most comprehensive
    2. IC matching (ic_matcher.match_component_ics) — known ICs
    3. Generic extraction (generic_ic_extractor) — unknown ICs
    4. Keyword detection (fallback)
    
    Merges results with deduplication by IC name.
    
    Args:
        pdf_text: Extracted text from PDF
        
    Returns:
        List of component dicts with schema:
        {
            "id": "camera_ov5647_0",
            "name": "OV5647 Camera Module",
            "type": "camera",
            "is_component": True,
            "component_ic": {
                "name": "OV5647",
                "vendor": "OmniVision",
                "type": "camera_sensor"
            },
            "connection_type": "mipi_csi",
            "source": "llm|ic_match|generic|keyword",
            "confidence": 0.9
        }
    """
    if not pdf_text or not pdf_text.strip():
        return []
    
    components_by_ic = {}  # ic_name -> component dict
    
    # ===== TRY 1: LLM Detection (most comprehensive) =====
    if detect_components_with_llm:
        try:
            llm_components, model_used = detect_components_with_llm(pdf_text)
            if llm_components and format_components_for_pipeline:
                formatted = format_components_for_pipeline(llm_components)
                for comp in formatted:
                    ic_name = comp.get("component_ic", {}).get("name", "").lower()
                    if ic_name:
                        components_by_ic[ic_name] = comp
                    else:
                        # Use name as ID if no IC model
                        comp_id = f"component_{comp.get('name', 'unknown').lower().replace(' ', '_')}_{len(components_by_ic)}"
                        comp["id"] = comp_id
                        components_by_ic[comp_id] = comp
        except Exception as e:
            pass  # Fall through to heuristic methods
    
    # ===== TRY 2: IC Matching (known ICs database) =====
    if match_component_ics:
        try:
            ic_matches = match_component_ics(pdf_text)
            for ic_match in ic_matches:
                # Convert ICMatch object to dict if needed
                if hasattr(ic_match, 'to_dict'):
                    match_dict = ic_match.to_dict()
                else:
                    match_dict = ic_match if isinstance(ic_match, dict) else ic_match.__dict__
                
                ic_name = match_dict.get("ic_name", "").lower()
                if not ic_name:
                    continue
                
                # Generate component ID from IC name
                comp_id = f"component_{ic_name}_{len(components_by_ic)}"
                
                # Extract vendor from known ICs
                vendor_map = {
                    "ov5647": "OmniVision",
                    "imx219": "Sony",
                    "imx477": "Sony",
                    "ar0521": "ON Semiconductor",
                    "ili9341": "Ilitek",
                    "st7789": "Sitronix",
                    "st7735": "Sitronix",
                    "ft5406": "Focaltech",
                    "bmp280": "Bosch",
                    "tmp36": "Analog Devices",
                    "mpu6050": "InvenSense",
                    "ads1015": "Texas Instruments",
                    "ads1115": "Texas Instruments",
                }
                vendor = vendor_map.get(ic_name, "Unknown")
                
                component = {
                    "id": comp_id,
                    "name": f"{ic_name.upper()} Component",
                    "type": match_dict.get("component_type", "sensor"),
                    "is_component": True,
                    "component_ic": {
                        "name": ic_name.upper(),
                        "vendor": vendor,
                        "type": match_dict.get("component_type", "unknown")
                    },
                    "connection_type": match_dict.get("connection_type", "unknown"),
                    "connector": {
                        "pins": [],
                        "voltage": "3.3V",
                        "required_board_interface": None
                    },
                    "source": "ic_match",
                    "confidence": match_dict.get("confidence", 0.5),
                    "context": match_dict.get("context", "")
                }
                
                # Store by IC name for deduplication
                if ic_name not in components_by_ic:
                    components_by_ic[ic_name] = component
                else:
                    # Prefer higher confidence match
                    if match_dict.get("confidence", 0) > components_by_ic[ic_name].get("confidence", 0):
                        components_by_ic[ic_name] = component
        except Exception as e:
            print(f"[extract_components_from_pdf] IC matching error: {e}")
    
    # 2. Keyword Detection (for additional context, only as fallback)
    if detect_component_keywords:
        try:
            keyword_matches = detect_component_keywords(pdf_text)
            
            # Track component types we already have from IC matches
            # Map keywords to full component types
            type_mapping = {
                "camera": ["camera_sensor", "camera"],
                "sensor": ["camera_sensor", "sensor_temperature", "sensor_accelerometer", "sensor_proximity", "sensor_light"],
                "display": ["display"],
                "touchscreen": ["touchscreen"],
                "audio": ["audio_codec", "amplifier", "microphone", "speaker"],
                "wifi": ["wifi"],
                "bluetooth": ["bluetooth"],
                "nfc": ["nfc"],
                "modem": ["modem"],
                "gps": ["gps"],
                "temperature": ["sensor_temperature"],
                "accelerometer": ["sensor_accelerometer"],
                "gyro": ["sensor_accelerometer"],
                "compass": ["magnetometer"],
                "pressure": ["sensor_temperature"],
                "light": ["sensor_light"],
            }
            
            existing_types = {
                comp.get("component_ic", {}).get("type", "").lower()
                for comp in components_by_ic.values()
            }
            
            for match in keyword_matches:
                keyword = match.get("keyword", "").lower()
                if not keyword or keyword == "other":
                    continue
                
                # Only use keyword if it's marked as component type
                if match.get("section_type") != "component":
                    continue
                
                # Skip if we already have a component that matches this keyword type
                mapped_types = type_mapping.get(keyword, [keyword])
                if any(t in existing_types for t in mapped_types):
                    continue
                
                # Use keyword to create component if not already found
                comp_id = f"component_{keyword}_{len(components_by_ic)}"
                if keyword not in components_by_ic:
                    component = {
                        "id": comp_id,
                        "name": f"{keyword.title()} Component",
                        "type": keyword,
                        "is_component": True,
                        "component_ic": {
                            "name": keyword.upper(),
                            "vendor": "Unknown",
                            "type": keyword
                        },
                        "connection_type": "unknown",
                        "connector": {
                            "pins": [],
                            "voltage": "3.3V",
                            "required_board_interface": None
                        },
                        "source": "keyword_detection",
                        "confidence": 0.4,
                        "context": match.get("context", "")
                    }
                    components_by_ic[keyword] = component
        except Exception as e:
            print(f"[extract_components_from_pdf] Keyword detection error: {e}")
    
    # 3. Connector Parsing (if available)
    if parse_connector_pins:
        try:
            # Try to extract connector sections and parse pins
            connector_sections = re.findall(
                r"(connector|pinout|pin map|pin configuration)[\s\S]{0,1000}?(?=\n\n|\Z)",
                pdf_text,
                re.IGNORECASE
            )
            for section in connector_sections:
                try:
                    pins = parse_connector_pins(section)
                    if pins and len(components_by_ic) > 0:
                        # Apply pins to most recently added component
                        last_comp = list(components_by_ic.values())[-1]
                        if last_comp.get("connector"):
                            last_comp["connector"]["pins"] = pins
                except Exception:
                    pass
        except Exception as e:
            print(f"[extract_components_from_pdf] Connector parsing error: {e}")
    
    # Convert dict values to list and remove internal fields
    components = []
    for comp in components_by_ic.values():
        # Remove internal 'context' field
        if "context" in comp:
            del comp["context"]
        components.append(comp)
    
    return components


def merge_hardware_maps(maps_list: list[dict]) -> dict:
    """
    Merge multiple hardware_map dicts from different PDFs.
    
    Deduplicates:
      - Buses with matching name and type (considered the same physical bus)
      - Power rails by name (merging their supplies lists)
    
    Adds source_pdf tracking to each peripheral to show which PDF it came from.
    Validates merged map has each regulator present in power_rails.
    
    Args:
        maps_list: List of hardware_map dicts, one per PDF
    
    Returns:
        Merged hardware_map dict with source_pdf field on all peripherals
    
    Logs warnings for:
      - Empty maps (skipped)
      - Conflicting addresses (includes both with warning)
      - Conflicting voltages for same rail (uses first, logs warning)
    """
    if not maps_list:
        return {
            "board": None,
            "soc": "Unknown",
            "arch": "arm64",
            "cpu_core": None,
            "cpu_count": None,
            "cpu_freq_mhz": None,
            "ram_mb": None,
            "peripherals": [],
            "power_rails": [],
        }
    
    warnings = []
    
    # Filter out empty maps
    valid_maps = []
    for idx, hw_map in enumerate(maps_list):
        if not hw_map or not isinstance(hw_map, dict):
            warnings.append(f"PDF {idx+1}: skipped empty/invalid map")
            continue
        if not hw_map.get("peripherals"):
            warnings.append(f"PDF {idx+1}: skipped map with no peripherals")
            continue
        valid_maps.append((idx+1, hw_map))
    
    if not valid_maps:
        warnings.append("All maps are empty, returning default structure")
        for warning in warnings:
            print(f"[merge_hardware_maps] WARNING: {warning}")
        return {
            "board": None,
            "soc": "Unknown",
            "arch": "arm64",
            "cpu_core": None,
            "cpu_count": None,
            "cpu_freq_mhz": None,
            "ram_mb": None,
            "peripherals": [],
            "power_rails": [],
        }
    
    # Initialize result with metadata from first valid map
    result = {
        "board": valid_maps[0][1].get("board"),
        "soc": valid_maps[0][1].get("soc", "Unknown"),
        "arch": valid_maps[0][1].get("arch", "arm64"),
        "cpu_core": valid_maps[0][1].get("cpu_core"),
        "cpu_count": valid_maps[0][1].get("cpu_count"),
        "cpu_freq_mhz": valid_maps[0][1].get("cpu_freq_mhz"),
        "ram_mb": valid_maps[0][1].get("ram_mb"),
        "peripherals": [],
        "power_rails": [],
    }
    
    # Fill in missing metadata from other maps
    for key in ("board", "soc", "arch", "cpu_core", "cpu_count", "cpu_freq_mhz", "ram_mb"):
        if not result.get(key):
            for _, hw_map in valid_maps[1:]:
                if hw_map.get(key):
                    result[key] = hw_map[key]
                    break
    
    # Normalize all peripherals: add source_pdf field
    for pdf_id, hw_map in valid_maps:
        for p in hw_map.get("peripherals", []):
            if isinstance(p, dict):
                if "source_pdf" not in p:
                    p["source_pdf"] = f"pdf_{pdf_id}"
    
    # Separate components from board peripherals before deduplication
    board_peripherals_list = []
    components_list = []
    
    for pdf_id, hw_map in valid_maps:
        board_perips, components = _separate_components(hw_map.get("peripherals", []))
        board_peripherals_list.append((pdf_id, board_perips))
        components_list.append((pdf_id, components))
    
    # Deduplicate board peripherals by (bus, type) pair
    seen_buses = {}  # (bus_name, type) -> peripheral entry
    
    for pdf_id, peripherals in board_peripherals_list:
        for p in peripherals:
            if not isinstance(p, dict):
                continue
            bus_name = p.get("bus", "").strip()
            ptype = p.get("type", "").strip()
            
            if not bus_name or not ptype:
                result["peripherals"].append(p)
                continue
            
            bus_key = (bus_name, ptype)
            
            if bus_key not in seen_buses:
                seen_buses[bus_key] = p
                result["peripherals"].append(p)
            else:
                # Duplicate bus found - existing already in result
                existing = seen_buses[bus_key]
                
                # Check for conflicting addresses
                if p.get("address") and existing.get("address"):
                    if p["address"] != existing["address"]:
                        warnings.append(
                            f"Address conflict for {bus_name}: {existing['address']} "
                            f"({existing.get('source_pdf', 'unknown')}) vs {p['address']} "
                            f"({p.get('source_pdf', 'unknown')}), keeping both"
                        )
                        result["peripherals"].append(p)
                        continue
                elif p.get("address") and not existing.get("address"):
                    existing["address"] = p["address"]
                
                # Check for conflicting voltages
                if p.get("voltage") and existing.get("voltage"):
                    if p["voltage"] != existing["voltage"]:
                        warnings.append(
                            f"Voltage conflict for {bus_name}: "
                            f"{existing['voltage']} (first), {p['voltage']} ({p.get('source_pdf', 'unknown')}), "
                            f"using first"
                        )
                elif p.get("voltage") and not existing.get("voltage"):
                    existing["voltage"] = p["voltage"]
                
                # Merge regulator info
                if not existing.get("regulator") and p.get("regulator"):
                    existing["regulator"] = p["regulator"]
    
    # Add deduplicated board peripherals (if not already added above)
    # and merge components
    seen_component_ids = set()
    for pdf_id, components in components_list:
        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_id = comp.get("id", "")
            if comp_id and comp_id not in seen_component_ids:
                result["peripherals"].append(comp)
                seen_component_ids.add(comp_id)
            elif comp_id in seen_component_ids:
                # Duplicate component - merge connector info if necessary
                warnings.append(
                    f"Component {comp_id} appears in multiple PDFs, using first occurrence"
                )
    
    # Deduplicate power rails by name, merge supplies lists
    seen_rails = {}
    for pdf_id, hw_map in valid_maps:
        for rail in hw_map.get("power_rails", []):
            if not isinstance(rail, dict):
                continue
            rail_name = rail.get("name", "").strip()
            if not rail_name:
                continue
            
            if rail_name not in seen_rails:
                # Create a new rail entry (not referencing the original)
                new_rail = {
                    "name": rail_name,
                    "voltage": rail.get("voltage"),
                    "current_ma": rail.get("current_ma"),
                    "supplies": list(rail.get("supplies", [])),
                }
                seen_rails[rail_name] = new_rail
                result["power_rails"].append(new_rail)
            else:
                existing_rail = seen_rails[rail_name]
                
                # Check for voltage conflict
                if rail.get("voltage") and existing_rail.get("voltage"):
                    if rail["voltage"] != existing_rail["voltage"]:
                        warnings.append(
                            f"Voltage conflict for rail {rail_name}: "
                            f"{existing_rail['voltage']} (first), {rail['voltage']} (pdf_{pdf_id}), "
                            f"using first"
                        )
                elif rail.get("voltage") and not existing_rail.get("voltage"):
                    existing_rail["voltage"] = rail["voltage"]
                
                # Merge supplies lists
                if rail.get("supplies"):
                    for supply in rail["supplies"]:
                        if supply not in existing_rail["supplies"]:
                            existing_rail["supplies"].append(supply)
    
    # Validate: each peripheral's regulator must exist in power_rails
    rail_names = {r.get("name", "") for r in result.get("power_rails", []) if r.get("name")}
    for p in result.get("peripherals", []):
        regulator = p.get("regulator", "")
        if isinstance(regulator, str):
            regulator = regulator.strip()
        else:
            regulator = ""
        if regulator and regulator not in rail_names:
            warnings.append(
                f"Peripheral {p.get('id', '?')} references unknown regulator '{regulator}'"
            )
    
    # Log all warnings
    for warning in warnings:
        print(f"[merge_hardware_maps] WARNING: {warning}")
    
    return result



# ── Ollama ─────────────────────────────────────────────────────────────────────

def _ollama_list_models(host: str) -> list[str]:
    """Return model names available in Ollama; empty list on any error."""
    try:
        req  = urllib.request.Request(f"{host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _ollama_chat(host: str, model: str, prompt: str) -> str:
    payload = json.dumps({
        "model":    model,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   False,
        "format":   "json",
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return data["message"]["content"]


def _try_ollama(prompt: str) -> tuple[dict, str]:
    host  = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "")

    if not model:
        models = _ollama_list_models(host)
        if not models:
            raise RuntimeError("ollama_unavailable")
        preferred = ["llama3", "llama3.1", "llama3.2", "mistral", "mixtral",
                     "qwen2", "qwen2.5", "gemma2", "phi3", "phi4", "deepseek"]
        model = next(
            (m for pref in preferred for m in models if pref in m.lower()),
            models[0]
        )

    raw = _ollama_chat(host, model, prompt)
    return json.loads(_strip_fences(raw)), model


# ── LM Studio (OpenAI-compatible) ─────────────────────────────────────────────

def _try_lm_studio(prompt: str) -> dict:
    host = os.getenv("LM_STUDIO_HOST", "http://localhost:1234").rstrip("/")
    payload = json.dumps({
        "messages":        [{"role": "user", "content": prompt}],
        "temperature":     0.1,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return json.loads(_strip_fences(data["choices"][0]["message"]["content"]))


# ── Generic OpenAI-compatible POST (works for OpenAI, Groq, Mistral, OpenRouter) ──

def _openai_compatible(base_url: str, api_key: str, model: str, prompt: str,
                       extra_headers: dict | None = None) -> dict:
    payload = json.dumps({
        "model":    model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }).encode()
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload, method="POST", headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return json.loads(_strip_fences(data["choices"][0]["message"]["content"]))


# ── Anthropic (separate REST format) ──────────────────────────────────────────

def _anthropic_api(api_key: str, model: str, prompt: str) -> dict:
    payload = json.dumps({
        "model":      model,
        "max_tokens": 2048,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, method="POST",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return json.loads(_strip_fences(data["content"][0]["text"]))


# ── Google Gemini ──────────────────────────────────────────────────────────────

def _gemini_api(api_key: str, model: str, prompt: str) -> dict:
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models"
           f"/{model}:generateContent?key={api_key}")
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(_strip_fences(raw))


# ── Static cloud model catalogue ───────────────────────────────────────────────

CLOUD_PROVIDERS: dict[str, dict] = {
    "openai": {
        "label":    "OpenAI",
        "key_name": "OPENAI_API_KEY",
        "key_hint": "sk-...",
        "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        ],
    },
    "anthropic": {
        "label":    "Anthropic",
        "key_name": "ANTHROPIC_API_KEY",
        "key_hint": "sk-ant-...",
        "models": [
            "claude-opus-4-5", "claude-sonnet-4-5",
            "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307",
        ],
    },
    "gemini": {
        "label":    "Google Gemini",
        "key_name": "GOOGLE_API_KEY",
        "key_hint": "AIza...",
        "models": [
            "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
        ],
    },
    "groq": {
        "label":    "Groq",
        "key_name": "GROQ_API_KEY",
        "key_hint": "gsk_...",
        "models": [
            "llama3-70b-8192", "llama3-8b-8192",
            "mixtral-8x7b-32768", "gemma2-9b-it",
        ],
    },
    "mistral": {
        "label":    "Mistral",
        "key_name": "MISTRAL_API_KEY",
        "key_hint": "...",
        "models": [
            "mistral-large-latest", "mistral-small-latest",
            "open-mixtral-8x22b", "open-codestral-mamba",
        ],
    },
    "openrouter": {
        "label":    "OpenRouter",
        "key_name": "OPENROUTER_API_KEY",
        "key_hint": "sk-or-...",
        "models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "microsoft/phi-4:free",
            "google/gemma-3-27b-it:free",
            "openai/gpt-4o-mini",
            "anthropic/claude-3-haiku",
            "mistralai/mistral-7b-instruct:free",
        ],
    },
}

_PROVIDER_BASE_URLS = {
    "openai":      "https://api.openai.com/v1",
    "groq":        "https://api.groq.com/openai/v1",
    "mistral":     "https://api.mistral.ai/v1",
    "openrouter":  "https://openrouter.ai/api/v1",
}


def _validate_hw_map(data: Any) -> dict:
    """Ensure LLM output is a usable hw_map dict. Raises ValueError on failure."""
    if not isinstance(data, dict):
        raise ValueError(f"LLM returned {type(data).__name__}, expected dict")
    for wrapper in ("result", "hardware_map", "output", "data"):
        if wrapper in data and isinstance(data[wrapper], dict):
            data = data[wrapper]
            break
    known = {"soc", "arch", "cpu_core", "peripherals", "power_rails", "board"}
    if not known.intersection(data.keys()):
        raise ValueError(f"No recognised hardware keys: {list(data.keys())[:6]}")
    return data


def _validate_peripheral_only(data: Any) -> dict:
    """Accept {peripherals:[...]} or {power_rails:[...]} partial responses."""
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")
    if "peripherals" in data or "power_rails" in data:
        return data
    raise ValueError(f"No peripherals/power_rails key: {list(data.keys())[:6]}")


# ── Single LLM call (provider-agnostic) ───────────────────────────────────────

def _call_llm(prompt: str, model_str: str, api_key: str) -> str:
    """
    Send prompt to the selected provider. Returns raw response string.
    model_str: "provider:model" or "" for auto-detect.
    Raises RuntimeError if all providers fail.
    """
    errors: list[str] = []

    def _resolve_key(provider: str) -> str:
        if api_key:
            return api_key
        env_var = CLOUD_PROVIDERS.get(provider, {}).get("key_name", "")
        return os.getenv(env_var, "")

    if model_str and ":" in model_str:
        provider, model = model_str.split(":", 1)

        if provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            return _ollama_chat(host, model, prompt)

        if provider == "lm_studio":
            return json.dumps(_try_lm_studio(prompt))

        if provider == "anthropic":
            key = _resolve_key("anthropic")
            if not key:
                raise RuntimeError("anthropic: no API key")
            raw = _anthropic_api(key, model, prompt)
            return json.dumps(raw)

        if provider == "gemini":
            key = _resolve_key("gemini")
            if not key:
                raise RuntimeError("gemini: no API key")
            raw = _gemini_api(key, model, prompt)
            return json.dumps(raw)

        if provider in _PROVIDER_BASE_URLS:
            key = _resolve_key(provider)
            if not key:
                raise RuntimeError(f"{provider}: no API key")
            extra = {"HTTP-Referer": "pdf-to-gadget"} if provider == "openrouter" else None
            raw = _openai_compatible(_PROVIDER_BASE_URLS[provider], key, model, prompt, extra)
            return json.dumps(raw)

        raise RuntimeError(f"Unknown provider: {provider}")

    # ── Auto-detect ───────────────────────────────────────────────────────────
    try:
        hw, model_name = _try_ollama(prompt)
        return json.dumps(hw)
    except Exception as e:
        errors.append(f"ollama:{e}")

    lm_host = os.getenv("LM_STUDIO_HOST", "http://localhost:1234")
    try:
        urllib.request.urlopen(
            urllib.request.Request(lm_host + "/v1/models", method="GET",
                                   headers={"Authorization": "Bearer lm-studio"}),
            timeout=1).close()
        return json.dumps(_try_lm_studio(prompt))
    except Exception as e:
        errors.append(f"lm_studio:{e}")

    cloud_order = [
        ("openai",    CLOUD_PROVIDERS["openai"]["models"][1]),
        ("anthropic", CLOUD_PROVIDERS["anthropic"]["models"][3]),
        ("gemini",    CLOUD_PROVIDERS["gemini"]["models"][1]),
        ("groq",      CLOUD_PROVIDERS["groq"]["models"][0]),
        ("mistral",   CLOUD_PROVIDERS["mistral"]["models"][1]),
    ]
    for prov, default_model in cloud_order:
        env_key = os.getenv(CLOUD_PROVIDERS[prov]["key_name"], "")
        if not env_key:
            continue
        try:
            if prov == "anthropic":
                return json.dumps(_anthropic_api(env_key, default_model, prompt))
            if prov == "gemini":
                return json.dumps(_gemini_api(env_key, default_model, prompt))
            return json.dumps(_openai_compatible(
                _PROVIDER_BASE_URLS[prov], env_key, default_model, prompt))
        except Exception as e:
            errors.append(f"{prov}:{e}")

    raise RuntimeError("no_llm_available: " + " | ".join(errors))


# ── Heuristic parser ────────────────────────────────────────────────────────────

_SOC_PATTERNS = [
    # Broadcom
    (r"BCM2\d{3}[A-Z0-9]*",        "arm64", "Cortex-A72"),
    (r"BCM\d{4}[A-Z0-9]*",         "armhf", "Cortex-A53"),
    # NXP i.MX
    (r"i\.MX\s*8[A-Z][A-Z0-9\s]*", "arm64", "Cortex-A53"),
    (r"i\.MX\s*9[A-Z][A-Z0-9\s]*", "arm64", "Cortex-A55"),
    (r"i\.MX\s*[67][A-Z0-9]*",     "armhf", "Cortex-A7"),
    # NXP Layerscape
    (r"LS\d{4}[A-Z]*",              "arm64", "Cortex-A53"),
    # Rockchip
    (r"RK3588[S]?",                 "arm64", "Cortex-A76"),
    (r"RK3[5-9]\d{2}[A-Z0-9]*",    "arm64", "Cortex-A55"),
    (r"RK3[0-4]\d{2}[A-Z0-9]*",    "armhf", "Cortex-A17"),
    # TI Sitara
    (r"AM6[2-9]\d{2}[A-Z0-9]*",    "arm64", "Cortex-A53"),
    (r"AM57\d{2}[A-Z0-9]*",        "armhf", "Cortex-A15"),
    (r"AM4\d{3}[A-Z0-9]*",         "armhf", "Cortex-A9"),
    (r"AM3\d{3}[A-Z0-9]*",         "armhf", "Cortex-A8"),
    # Allwinner
    (r"Allwinner\s+[AHR]\d+[A-Z0-9]*|[AH]\d{2,3}[A-Z0-9]*(?=\s+SoC|\s+processor)", "arm64", "Cortex-A53"),
    # Amlogic
    (r"S9[0-9]{2}[A-Z0-9]*",       "arm64", "Cortex-A55"),
    (r"A311[D][0-9]?",              "arm64", "Cortex-A73"),
    # MediaTek
    (r"MT\d{4}[A-Z0-9]*",          "arm64", "Cortex-A55"),
    # Qualcomm
    (r"QCS\d{3,4}[A-Z0-9]*",       "arm64", "Kryo"),
    (r"Snapdragon\s+\d+",           "arm64", "Kryo"),
    # Samsung Exynos
    (r"Exynos\s*\d{4}[A-Z0-9]*",   "arm64", "Cortex-A78"),
    # NVIDIA Tegra / Orin
    (r"Tegra\s+X\d|T\d{3}[A-Z]?",  "arm64", "Cortex-A78AE"),
    # Renesas RZ
    (r"R-Car\s+\w+|RZ/[A-Z]\d+",   "arm64", "Cortex-A55"),
    # STM32 MPU
    (r"STM32MP\d+[A-Z0-9]*",       "armhf", "Cortex-A7"),
    # Generic
    (r"AM\d{4}[A-Z0-9]*",          "armhf", "Cortex-A8"),
]

_BUS_PATTERNS = {
    "i2c":  re.compile(r"I2C[-_]?(\d+)\s*[:\s@]?\s*(0x[0-9A-Fa-f]{2,4})", re.I),
    "spi":  re.compile(r"SPI[-_]?(\d+)", re.I),
    "uart": re.compile(r"UART[-_]?(\d+)|SERIAL[-_]?(\d+)", re.I),
    "gpio": re.compile(r"GPIO[-_]?(\d+)|PIN\s*(\d+)", re.I),
    "pwm":      re.compile(r"PWM[-_]?(\d+)", re.I),
    "usb":      re.compile(r"USB[-_]?(\d*)\s*(?:Host|OTG|Device)?", re.I),
    "ethernet": re.compile(r"ETH(?:ERNET)?[-_]?(\d*)|GMAC[-_]?(\d*)|EMAC[-_]?(\d*)", re.I),
    "can":      re.compile(r"CAN(?:FD)?[-_]?(\d+)", re.I),
    "hdmi":     re.compile(r"HDMI[-_]?(\d*)", re.I),
    "mipi_csi": re.compile(r"MIPI[-_]?CSI[-_]?(\d*)|CSI[-_]?(\d+)", re.I),
    "mipi_dsi": re.compile(r"MIPI[-_]?DSI[-_]?(\d*)|DSI[-_]?(\d+)", re.I),
    "pcie":     re.compile(r"PCIe?[-_]?(\d*)|PCI\s+Express", re.I),
    "sata":     re.compile(r"SATA[-_]?(\d*)", re.I),
    "emmc":     re.compile(r"eMMC[-_]?(\d*)|EMMC[-_]?(\d*)", re.I),
    "sd":       re.compile(r"(?:SD|SDIO|SDMMC)[-_]?(\d*)", re.I),
    "i2s":      re.compile(r"I2S[-_]?(\d*)|SAI[-_]?(\d*)", re.I),
    "adc":      re.compile(r"ADC[-_]?(\d+)", re.I),
    "dac":      re.compile(r"DAC[-_]?(\d+)", re.I),
    "qspi":     re.compile(r"QSPI[-_]?(\d*)|OSPI[-_]?(\d*)", re.I),
    "jtag":     re.compile(r"JTAG|SWD", re.I),
    "rtc":      re.compile(r"\bRTC\b", re.I),
    "lvds":     re.compile(r"LVDS[-_]?(\d*)", re.I),
}

_BOARD_PATTERNS = [
    re.compile(r"Raspberry\s+Pi\s+[\w\s]+(?:Model\s+\w+)?", re.I),
    re.compile(r"BeagleBone\s+\w+", re.I),
    re.compile(r"Jetson\s+(?:Nano|Xavier|Orin|TX\d+|AGX\s+\w+)", re.I),
    re.compile(r"Rock\s+Pi\s+[\w\d]+", re.I),
    re.compile(r"Orange\s+Pi\s+[\w\d]+", re.I),
    re.compile(r"Banana\s+Pi\s+[\w\d]+", re.I),
    re.compile(r"PINE\s*(?:64|A64|H64|RK3|Book)\s*[\w\d]*", re.I),
    re.compile(r"NanoPi\s+[\w\d]+", re.I),
    re.compile(r"Odroid[- ][\w\d]+", re.I),
    re.compile(r"Khadas\s+[\w\d]+", re.I),
    re.compile(r"Radxa\s+[\w\d]+", re.I),
    re.compile(r"STM32\w+[-\s](?:Discovery|Nucleo|Eval)\w*", re.I),
    re.compile(r"Arduino\s+\w+", re.I),
    # Generic board/eval/dev-kit patterns
    re.compile(
        r"([A-Z][A-Za-z0-9][-A-Za-z0-9]*)"
        r"\s+(?:Development\s+Board|Evaluation\s+(?:Board|Kit)|Dev(?:eloper)?\s+Kit"
        r"|EVK|SBC|SOM|System[- ]on[- ]Module)",
        re.I,
    ),
    re.compile(r"(?:Board|Platform|Module)\s+Name\s*[:\-]\s*(.+)", re.I),
    re.compile(r"Product\s+Name\s*[:\-]\s*([A-Z][^\n]{3,60})", re.I),
]

_REG_PATTERN = re.compile(r"(vcc[-_]\w+|vdd[-_]\w+|vmmc[-_]\w*|v\d+p\d+)", re.I)
_VOLTAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*V\b", re.I)

# ── PDF type classification ────────────────────────────────────────────────────

_PIN_PATTERNS = {
    "mipi_csi": re.compile(r"CSI[-_]?D[0-3]|CSI[-_]?(?:CLK|HS[PC]|VS)", re.I),
    "i2c":      re.compile(r"\b(?:SDA|SCL|INT|ALERT)\b", re.I),
    "spi":      re.compile(r"\b(?:MOSI|MISO|CLK|CS|SCLK|SDI|SDO)\b", re.I),
    "usb":      re.compile(r"\b(?:DP|DM|VBUS|D[\+\-])\b", re.I),
    "uart":     re.compile(r"\b(?:TX|RX|TXD|RXD|RTS|CTS)\b", re.I),
}


def classify_pdf_type(hardware_map: dict) -> str:
    """
    Classify PDF as 'board' (contains SoC) or 'component' (no SoC).
    
    Args:
        hardware_map: Extracted hardware map dict
        
    Returns:
        'board' if SoC detected, 'component' otherwise
    """
    soc = hardware_map.get("soc", "").strip().lower()
    if soc and soc not in ("unknown", "unknown soc", ""):
        return "board"
    return "component"


def _detect_connection_type_from_pins(pin_names: list[str]) -> str:
    """
    Infer connection type from pin names.
    
    Args:
        pin_names: List of pin signal names (e.g., ['CSI_D0', 'CSI_CLK', 'GND'])
        
    Returns:
        Connection type string or 'generic'
    """
    pins_str = " ".join(pin_names).upper()
    scores = {}
    
    for conn_type, pattern in _PIN_PATTERNS.items():
        matches = len(pattern.findall(pins_str))
        if matches > 0:
            scores[conn_type] = matches
    
    if scores:
        return max(scores, key=scores.get)
    return "generic"


def _extract_connector_pins(peripheral: dict) -> list[str]:
    """
    Extract connector pin names from peripheral description.
    Falls back to bus label if no pins found in description.
    
    Args:
        peripheral: Peripheral dict with id, name, description, bus
        
    Returns:
        List of pin signal names
    """
    # Look for pin names in description
    desc = peripheral.get("description", "").upper()
    
    # Match common pin patterns
    pin_pattern = re.compile(r"\b([A-Z][A-Z0-9]*[-_]?(?:D|CLK|CS|HS[PC]|VS|INT|ALERT|TX|RX|MOSI|MISO|DP|DM|SDA|SCL|VCC|GND))\b")
    pins = pin_pattern.findall(desc)
    
    if pins:
        return list(set(pins))  # unique pins
    
    # Fallback: generate from bus label
    bus = peripheral.get("bus", "").upper()
    if bus:
        return [f"{bus}_PIN"]
    
    return []


def enrich_component_peripheral(peripheral: dict) -> dict:
    """
    Enrich peripheral dict for component (non-board) PDFs.
    Adds component-specific fields and removes board-specific ones.
    
    Args:
        peripheral: Peripheral dict
        
    Returns:
        Enhanced peripheral dict with component fields
    """
    enhanced = dict(peripheral)
    
    # Detect connection type from available pin info
    pins = _extract_connector_pins(peripheral)
    conn_type = _detect_connection_type_from_pins(pins)
    
    # Add component-specific fields
    enhanced["is_component"] = True
    enhanced["connection_type"] = conn_type
    enhanced["connector_pins"] = pins
    
    # Extract voltage from description or rail
    voltage = peripheral.get("voltage", "3.3V")
    enhanced["voltage"] = voltage
    
    # Remove internal bus/register info (components don't have these)
    enhanced.pop("address", None)
    enhanced.pop("irq", None)
    
    # Simplify description for components
    if conn_type != "generic":
        enhanced["description"] = f"{conn_type.upper()} connector: {', '.join(pins[:4])}"
    
    return enhanced


def enrich_hardware_map_for_type(hardware_map: dict, pdf_type: str = None) -> dict:
    """
    Enrich hardware_map based on detected PDF type.
    
    For components (no SoC), enriches peripherals with connection info.
    For boards, leaves peripherals as-is.
    
    Args:
        hardware_map: Extracted hardware map dict
        pdf_type: Optional pre-classified type ('board' or 'component').
                 If None, will auto-detect.
    
    Returns:
        Enriched hardware_map dict
    """
    if pdf_type is None:
        pdf_type = classify_pdf_type(hardware_map)
    
    enhanced = dict(hardware_map)
    enhanced["pdf_type"] = pdf_type
    
    if pdf_type == "component":
        # Enrich all peripherals with component-specific fields
        enriched_peripherals = []
        for peripheral in hardware_map.get("peripherals", []):
            enriched = enrich_component_peripheral(peripheral)
            enriched_peripherals.append(enriched)
        enhanced["peripherals"] = enriched_peripherals
    
    return enhanced


# ── Section-by-section LLM runner ─────────────────────────────────────────────

def _llm_parse(raw_str: str, partial_ok: bool = False) -> dict:
    """Parse LLM string output into a dict, accepting partial {peripherals:...} responses."""
    obj = json.loads(_strip_fences(raw_str))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected dict, got {type(obj).__name__}")
    for wrapper in ("result", "hardware_map", "output", "data"):
        if wrapper in obj and isinstance(obj[wrapper], dict):
            obj = obj[wrapper]
            break
    if partial_ok:
        return obj
    return _validate_hw_map(obj)


def _heuristic_extract(text: str) -> dict:
    hw: dict[str, Any] = {
        "board": None,
        "soc": "Unknown SoC",
        "arch": "arm64",
        "cpu_core": "Unknown",
        "peripherals": [],
        "power_rails": [],
    }

    # detect board name
    for rx in _BOARD_PATTERNS:
        m = re.search(rx, text)
        if m:
            # use first capture group if present, else full match
            hw["board"] = (m.group(1) if m.lastindex else m.group(0)).strip()
            break

    # detect SoC
    for pattern, arch, core in _SOC_PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            hw["soc"]      = m.group(0).strip()
            hw["arch"]     = arch
            hw["cpu_core"] = core
            break

    seen: set[str] = set()
    pid  = 0

    for ptype, rx in _BUS_PATTERNS.items():
        for m in rx.finditer(text):
            # build bus label from first non-None group
            num   = next((g for g in m.groups() if g is not None), "0")
            bus   = f"{ptype.upper()}{num}"
            key   = bus.lower()
            if key in seen:
                continue
            seen.add(key)

            # try to grab nearby name (word before/after the match)
            ctx_start = max(0, m.start() - 60)
            ctx_end   = min(len(text), m.end() + 60)
            context   = text[ctx_start:ctx_end].strip().replace("\n", " ")

            # address
            addr = ""
            am = re.search(r"0x[0-9A-Fa-f]{2,4}", context)
            if am:
                addr = am.group(0)

            # voltage
            voltage = ""
            vm = _VOLTAGE_PATTERN.search(context)
            if vm:
                voltage = vm.group(1) + "V"

            # regulator
            regulator = ""
            rm = _REG_PATTERN.search(context)
            if rm:
                regulator = rm.group(0).lower()

            pid += 1
            hw["peripherals"].append({
                "id":          f"{ptype}_{num or pid}",
                "name":        f"{bus} Controller",
                "type":        ptype,
                "bus":         bus,
                "address":     addr,
                "description": f"{ptype.upper()} peripheral on {bus}",
                "voltage":     voltage or "3.3V",
                "regulator":   regulator or f"vcc-{ptype}",
            })

    # power rails from regex
    for rm in _REG_PATTERN.finditer(text):
        name = rm.group(0).lower()
        if not any(r["name"] == name for r in hw["power_rails"]):
            vm = _VOLTAGE_PATTERN.search(text[rm.start():rm.start()+40])
            hw["power_rails"].append({
                "name":     name,
                "voltage":  vm.group(1) + "V" if vm else "3.3V",
                "supplies": [],
            })

    # ensure at least one power rail
    if not hw["power_rails"]:
        hw["power_rails"].append({"name": "vcc-3v3", "voltage": "3.3V", "supplies": []})

    return hw


# ── Public API ──────────────────────────────────────────────────────────────────

def list_local_models() -> dict:
    """
    Returns local + static cloud models for the UI selector.
    { "ollama": [...], "lm_studio": [...], "cloud": CLOUD_PROVIDERS }
    """
    result: dict = {"ollama": [], "lm_studio": [], "cloud": CLOUD_PROVIDERS}
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    result["ollama"] = _ollama_list_models(ollama_host)

    lm_host = os.getenv("LM_STUDIO_HOST", "http://localhost:1234")
    try:
        req = urllib.request.Request(f"{lm_host}/v1/models", method="GET",
                                     headers={"Authorization": "Bearer lm-studio"})
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read())
        result["lm_studio"] = [m["id"] for m in data.get("data", [])]
    except Exception:
        pass
    return result


def _normalise_hw_map(hw: dict) -> dict:
    """Ensure hw_map has all required fields with sane defaults."""
    if not isinstance(hw, dict):
        hw = {}
    raw_board = hw.get("board") or None
    arch      = hw.get("arch", "arm64")
    hw["board_name"] = (raw_board.strip() if isinstance(raw_board, str) and raw_board else "") \
                       or f"Custom {arch}"
    hw.setdefault("soc",          "Unknown SoC")
    hw.setdefault("arch",         "arm64")
    hw.setdefault("cpu_core",     "")
    hw.setdefault("cpu_count",    None)
    hw.setdefault("cpu_freq_mhz", None)
    hw.setdefault("ram_mb",       None)
    hw.setdefault("peripherals",  [])
    hw.setdefault("power_rails",  [])
    p_defaults = {"id": "", "name": "", "type": "other", "bus": "", "address": "",
                  "irq": None, "description": "", "voltage": "3.3V", "regulator": "vcc-3v3",
                  "is_component": False, "connection_type": "", "source_pdf": ""}
    clean: list[dict] = []
    for p in hw["peripherals"]:
        if not isinstance(p, dict):
            continue
        for k, v in p_defaults.items():
            p.setdefault(k, v)
        if not p["id"]:
            p["id"] = re.sub(r"\W+", "_", p.get("name", "").lower()) or f"periph_{id(p)}"
        clean.append(p)
    hw["peripherals"] = clean
    return hw


def run_sections(
    sections: list[dict],
    model_override: str = "",
    api_key: str = "",
) -> tuple[dict, str, list[str]]:
    """
    Section-by-section extraction. Returns (hw_map, mode, log_lines).
    Called by main.py upload stream.
    """
    # imported here to avoid circular issue with run_sections defined above
    merged_raw, mode, log = _run_sections_internal(sections, model_override, api_key)
    return _normalise_hw_map(merged_raw), mode, log


def _run_sections_internal(sections, model_override, api_key):
    """Internal implementation (before normalisation)."""
    merged: dict = {}
    mode = "heuristic"
    log: list[str] = []
    llm_succeeded = False
    llm_available = True

    # quick LLM probe (1-sec timeout dummy call to detect availability)
    try:
        _call_llm("Return JSON: {}", model_override, api_key)
        # if model_override is blank and ollama absent this will raise
    except RuntimeError as e:
        if "no_llm_available" in str(e) or "no API key" in str(e).lower():
            llm_available = False
    except Exception:
        pass  # parse error etc — LLM is still there

    for i, sec in enumerate(sections):
        text    = sec.get("text", "").strip()
        heading = sec.get("heading", f"Section {i+1}")
        p_start = sec.get("page_start", "?")
        p_end   = sec.get("page_end", "?")
        page_label = f"p{p_start}" if p_start == p_end else f"p{p_start}–{p_end}"

        if not text:
            continue

        stype = _classify_section(text)
        log.append(f"  📄 [{page_label}] \"{heading}\" → {stype}")

        if not llm_available:
            try:
                hw = _heuristic_extract(text)
                merged = _merge_hw_maps(merged, hw) if merged else hw
                n = len(hw.get("peripherals", []))
                if n:
                    log.append(f"       ↳ heuristic: {n} peripherals")
            except Exception as e:
                log.append(f"       ↳ heuristic error: {e}")
            
            # Extract components even when using heuristic
            try:
                components = extract_components_from_pdf(text)
                if components:
                    if not merged:
                        merged = {
                            "board": None,
                            "soc": None,
                            "arch": None,
                            "cpu_core": None,
                            "cpu_count": None,
                            "cpu_freq_mhz": None,
                            "ram_mb": None,
                            "peripherals": [],
                            "power_rails": []
                        }
                    
                    if "peripherals" not in merged:
                        merged["peripherals"] = []
                    
                    existing_component_ics = {
                        p.get("component_ic", {}).get("name", "").lower()
                        for p in merged.get("peripherals", [])
                        if p.get("is_component")
                    }
                    
                    for comp in components:
                        ic_name = comp.get("component_ic", {}).get("name", "").lower()
                        if ic_name and ic_name not in existing_component_ics:
                            merged["peripherals"].append(comp)
                            existing_component_ics.add(ic_name)
                    
                    n_comps = len([c for c in merged.get("peripherals", []) if c.get("is_component")])
                    if n_comps > len([p for p in hw.get("peripherals", []) if p.get("is_component")]):
                        log.append(f"       ↳ components: {len(components)} detected")
            except Exception as e:
                pass
            continue

        # pick appropriate prompt
        if not merged or stype == "overview":
            prompt = _overview_prompt(text)
            partial = False
        elif stype == "register":
            prompt = _register_prompt(text, heading)
            partial = True
        elif stype == "power":
            prompt = _power_prompt(text)
            partial = True
        elif stype == "pinmux":
            prompt = _pinmux_prompt(text, heading)
            partial = True
        else:
            prompt = _peripheral_prompt(text, heading)
            partial = True

        try:
            raw = _call_llm(prompt, model_override, api_key)
            obj = json.loads(_strip_fences(raw))
            if not isinstance(obj, dict):
                raise ValueError("not a dict")
            for wrapper in ("result", "hardware_map", "output", "data"):
                if wrapper in obj and isinstance(obj[wrapper], dict):
                    obj = obj[wrapper]
                    break
            if not partial:
                _validate_hw_map(obj)
            merged = _merge_hw_maps(merged, obj) if merged else obj
            llm_succeeded = True
            if not mode.startswith("llm"):
                mode = model_override or "llm:auto"
            n_p = len(obj.get("peripherals", []))
            n_r = len(obj.get("power_rails", []))
            log.append(f"       ↳ LLM ✓ {n_p} peripherals, {n_r} rails")
        except RuntimeError as e:
            llm_available = False
            log.append(f"       ↳ LLM unavailable ({e}) → heuristic")
            try:
                hw = _heuristic_extract(text)
                merged = _merge_hw_maps(merged, hw) if merged else hw
            except Exception:
                pass
        except Exception as e:
            log.append(f"       ↳ LLM parse error ({e}) → heuristic")
            try:
                hw = _heuristic_extract(text)
                merged = _merge_hw_maps(merged, hw) if merged else hw
            except Exception:
                pass
        
        # Extract components from each section (LLM path)
        try:
            components = extract_components_from_pdf(text)
            if components:
                # Add components to merged hardware map
                if not merged:
                    merged = {
                        "board": None,
                        "soc": None,
                        "arch": None,
                        "cpu_core": None,
                        "cpu_count": None,
                        "cpu_freq_mhz": None,
                        "ram_mb": None,
                        "peripherals": [],
                        "power_rails": []
                    }
                
                # Add components as peripherals with is_component=True
                if "peripherals" not in merged:
                    merged["peripherals"] = []
                
                # Deduplicate components by IC name
                existing_component_ics = {
                    p.get("component_ic", {}).get("name", "").lower()
                    for p in merged.get("peripherals", [])
                    if p.get("is_component")
                }
                
                for comp in components:
                    ic_name = comp.get("component_ic", {}).get("name", "").lower()
                    if ic_name and ic_name not in existing_component_ics:
                        merged["peripherals"].append(comp)
                        existing_component_ics.add(ic_name)
                
                n_c = len([c for c in components if c.get("component_ic", {}).get("name", "").lower() not in existing_component_ics])
                if n_c > 0:
                    log.append(f"       ↳ components: {len(components)} detected")
        except Exception as e:
            # Component extraction errors are non-fatal
            pass

    if llm_succeeded and model_override:
        mode = model_override
    elif llm_succeeded:
        mode = "llm:auto"

    return merged, mode, log


def run(pdf_text: str, model_override: str = "", api_key: str = "") -> tuple[dict, str]:
    """
    Legacy single-text entry point. Wraps run_sections with a single section.
    """
    sections = [{"heading": "Full Document", "text": pdf_text,
                 "page_start": 1, "page_end": 1}]
    hw, mode, _ = run_sections(sections, model_override=model_override, api_key=api_key)
    return hw, mode

