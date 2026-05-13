"""
Bus Validator — Connection validation for multi-PDF component merging.
Validates I2C/SPI/UART bus consistency, power rail compatibility, and driver availability.
Returns warnings but does not halt processing.
"""
import re
from typing import List, Optional, Dict, Any

try:
    from kernel_scout import _lookup_db
except ImportError:
    from .kernel_scout import _lookup_db

try:
    from alternative_connections import get_alternatives
except ImportError:
    from .alternative_connections import get_alternatives


# ─── Common bus pin patterns ────────────────────────────────────────────────

_BUS_PIN_PATTERNS = {
    "I2C": [
        r"\bI2C_?SDA\b", r"\bI2C_?SCL\b", r"\bDATA\b", r"\bCLOCK\b",
        r"\bSDA\d*\b", r"\bSCL\d*\b"
    ],
    "SPI": [
        r"\bSPI_?MOSI\b", r"\bSPI_?MISO\b", r"\bSPI_?CLK\b", r"\bSPI_?CS\b",
        r"\bDI\b", r"\bDO\b", r"\bSCLK\b", r"\bCS\d*\b", r"\bCHIP_?SELECT\b",
        r"\bMOSI\d*\b", r"\bMISO\d*\b", r"\bCLK\d*\b"
    ],
    "UART": [
        r"\bUART_?RX\b", r"\bUART_?TX\b", r"\bUART_?RTS\b", r"\bUART_?CTS\b",
        r"\bRXD\b", r"\bTXD\b", r"\bRX\d*\b", r"\bTX\d*\b", r"\bRXD\d*\b", r"\bTXD\d*\b"
    ],
}


def _extract_pins_from_peripheral(peripheral: dict) -> List[str]:
    """
    Extract pin names from a peripheral definition.
    Looks for pin_names, pins, pin_list, and other common patterns.
    Excludes the bus name itself.
    """
    pins = set()
    bus_name = peripheral.get("bus", "")  # Exclude bus name from pin detection
    
    # Check explicit pin fields
    for key in ["pins", "pin_names", "pin_list", "pin_map"]:
        if key not in peripheral:
            continue
        value = peripheral[key]
        if isinstance(value, str):
            # Extract uppercase tokens that look like pin names
            tokens = re.findall(r"\b[A-Z_][A-Z0-9_]*\b", value)
            pins.update(tokens)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    tokens = re.findall(r"\b[A-Z_][A-Z0-9_]*\b", item)
                    pins.update(tokens)
    
    # Look for specific bus patterns in description
    if "description" in peripheral:
        desc = peripheral["description"]
        if isinstance(desc, str):
            # First, look for specific bus patterns across all bus types
            all_patterns = []
            for bus_type_patterns in _BUS_PIN_PATTERNS.values():
                all_patterns.extend(bus_type_patterns)
            
            for pattern in all_patterns:
                matches = re.findall(pattern, desc, re.IGNORECASE)
                pins.update(m.upper() for m in matches)
            
            # Also extract general uppercase tokens that look like pin names (2+ chars, letters/digits/underscore)
            # Filter to likely pin names (known patterns + reasonable control pins)
            tokens = re.findall(r"\b[A-Z_][A-Z0-9_]{1,}\b", desc)
            likely_pins = set()
            common_control = {"RESET", "ENABLE", "INTERRUPT", "INT", "ALERT", "IRQ", 
                             "STROBE", "SELECT", "LATCH", "OE", "WE", "RE", "CE", 
                             "CHIP_SELECT", "CHIP_EN", "OUTPUT_ENABLE", "WRITE_ENABLE"}
            for token in tokens:
                # Include token if it's a known pin, a control pin, or looks like a numbered pin (e.g., SDA0)
                if (token in pins or token in common_control or 
                    re.match(r"[A-Z]+\d+", token)):  # numbered pins like SDA0, RX1
                    likely_pins.add(token)
            pins.update(likely_pins)
    
    # Remove bus name if it was mistakenly included
    pins.discard(bus_name)
    
    return sorted(list(pins))


def _infer_bus_type(bus_name: str) -> str:
    """Infer bus type from bus name (I2C0 → I2C, SPI1 → SPI, etc.)"""
    if not bus_name:
        return "UNKNOWN"
    match = re.match(r"([A-Z]+)", bus_name.upper())
    if match:
        return match.group(1)
    return "UNKNOWN"


def _get_pins_for_bus_type(bus_type: str) -> List[str]:
    """Return expected pin names for a given bus type."""
    bus_type_upper = bus_type.upper()
    patterns = _BUS_PIN_PATTERNS.get(bus_type_upper, [])
    
    # Compile and test patterns against common pin names
    expected_pins = set()
    common_pins = [
        "SDA", "SCL", "MOSI", "MISO", "CLK", "CS", "RX", "TX", "RTS", "CTS",
        "DATA", "CLOCK", "DI", "DO", "SCLK", "RXD", "TXD", "ALERT", "INT",
        "CHIP_SELECT", "ENABLE", "RESET"
    ]
    
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for pin in common_pins:
            if regex.match(pin):
                expected_pins.add(pin)
    
    return sorted(list(expected_pins))


def _get_driver_alternatives(
    peripheral_type: str,
    driver_status: str,
    soc: str,
) -> List[Dict[str, Any]]:
    """
    Get alternative connection types and their driver statuses.
    
    Args:
        peripheral_type: Type of peripheral (e.g., "camera", "display")
        driver_status: Current driver status (mainline/backport/vendor/unknown)
        soc: SoC name for lookups
    
    Returns:
        List of alternative connection dicts with driver info
    """
    if driver_status == "mainline":
        return []  # No alternatives needed if driver is mainline
    
    alternatives_list = get_alternatives(peripheral_type)
    if not alternatives_list:
        return []
    
    result = []
    for alt_connection_type in alternatives_list:
        # Look up driver status for this alternative connection type
        alt_driver_info = _lookup_db(soc, alt_connection_type)
        
        if alt_driver_info:
            alt_status = alt_driver_info.get("status", "unknown")
        else:
            alt_status = "unknown"
        
        result.append({
            "connection_type": alt_connection_type,
            "driver_status": alt_status,
            "effort": "medium" if alt_status == "unknown" else "low" if alt_status == "mainline" else "high"
        })
    
    return result


def _lookup_driver_with_fallback(soc: str, peripheral_type: str) -> Optional[dict]:
    """
    Look up driver for a peripheral type, with fallback to alternative types.
    
    For generic types like "display", tries specific types like "hdmi", "displayport".
    """
    # Try the exact type first
    driver_info = _lookup_db(soc, peripheral_type)
    if driver_info:
        return driver_info
    
    # Try alternatives (generic fallback)
    alternatives = get_alternatives(peripheral_type)
    for alt_type in alternatives:
        alt_info = _lookup_db(soc, alt_type)
        if alt_info:
            return alt_info
    
    return None


def validate_connections(
    maps_list: List[dict],
    soc: Optional[str] = None,
) -> dict:
    """
    Validate bus connections, power rail compatibility, and driver availability.
    
    Args:
        maps_list: List of hardware_map dicts, each containing:
                   - peripherals: list of {id, name, type, bus, voltage, ...}
                   - power_rails: list of {name, voltage, ...}
                   - soc: (optional) SoC name for driver lookup
        soc: (optional) SoC name. If not provided, will try to extract from first map.
    
    Returns:
        {
          "valid": True,  # always true (warn but continue mode)
          "conflicts": [
            {
              "type": "bus_pin_mismatch" | "power_rail_mismatch" | "driver_unavailable",
              "bus_name": "I2C0" | rail name,
              "peripheral_type": "camera" (for driver conflicts),
              "map_a_pins": [...],
              "map_b_pins": [...],
              "severity": "warning",
              "message": "...",
              "alternatives": [  # NEW: for driver conflicts
                {
                  "connection_type": "usb",
                  "driver_status": "mainline",
                  "effort": "low"
                }
              ]
            }
          ],
          "merged_buses": {
            "I2C0": ["SDA", "SCL"],
            "SPI0": ["MOSI", "MISO", "CLK", "CS"]
          },
          "driver_summary": {  # NEW
            "mainline": 5,
            "backport": 2,
            "vendor": 1,
            "unknown": 1
          }
        }
    """
    # Edge case: empty list
    if not maps_list:
        return {
            "valid": True,
            "conflicts": [],
            "merged_buses": {},
            "driver_summary": {}
        }
    
    conflicts = []
    merged_buses = {}
    driver_summary: Dict[str, int] = {
        "mainline": 0,
        "backport": 0,
        "vendor": 0,
        "unknown": 0,
        "wip": 0
    }
    
    # Extract SoC from first map if not provided
    if soc is None and maps_list:
        soc = maps_list[0].get("soc", "")
    
    # ─── Bus pin validation ────────────────────────────────────────────────
    
    # Collect all buses and their pins across maps
    buses_by_name = {}  # bus_name -> list of (map_idx, pins_set)
    
    for map_idx, hw_map in enumerate(maps_list):
        peripherals = hw_map.get("peripherals", [])
        
        for peripheral in peripherals:
            if not isinstance(peripheral, dict):
                continue
            
            bus_name = peripheral.get("bus")
            if not bus_name:
                continue
            
            # Extract pins from this peripheral
            pins = _extract_pins_from_peripheral(peripheral)
            
            # Skip if no pins extracted
            if not pins:
                continue
            
            # Record this bus in this map
            if bus_name not in buses_by_name:
                buses_by_name[bus_name] = []
            buses_by_name[bus_name].append((map_idx, set(pins)))
    
    # Check for conflicts between different maps and populate merged_buses
    for bus_name, map_entries in buses_by_name.items():
        # Only flag conflicts if the bus appears in multiple maps
        if len(map_entries) > 1:
            # Compare pin sets between first and other maps
            first_pins = map_entries[0][1]
            
            for other_idx, other_pins in map_entries[1:]:
                # Check if pin sets differ
                if first_pins != other_pins:
                    conflicts.append({
                        "type": "bus_pin_mismatch",
                        "bus_name": bus_name,
                        "map_a_pins": sorted(list(first_pins)),
                        "map_b_pins": sorted(list(other_pins)),
                        "severity": "warning",
                        "message": (
                            f"{bus_name} pin count differs between components: "
                            f"{len(first_pins)} vs {len(other_pins)} pins"
                        )
                    })
        
        # For merged_buses, take the union of all pins for a bus
        if len(map_entries) > 0:
            all_pins = set()
            for _, pins in map_entries:
                all_pins.update(pins)
            merged_buses[bus_name] = sorted(list(all_pins))
    
    # ─── Power rail validation ────────────────────────────────────────────
    
    # Collect all power rails across maps
    rails_by_name = {}  # rail_name -> list of (map_idx, voltage)
    
    for map_idx, hw_map in enumerate(maps_list):
        power_rails = hw_map.get("power_rails", [])
        
        for rail in power_rails:
            if not isinstance(rail, dict):
                continue
            
            rail_name = rail.get("name")
            voltage = rail.get("voltage")
            
            if not rail_name:
                continue
            
            if rail_name not in rails_by_name:
                rails_by_name[rail_name] = []
            rails_by_name[rail_name].append((map_idx, voltage))
    
    # Check for voltage conflicts on same rail
    for rail_name, map_entries in rails_by_name.items():
        if len(map_entries) > 1:
            # Compare voltages
            first_voltage = map_entries[0][1]
            
            for other_idx, other_voltage in map_entries[1:]:
                # Only flag if both have voltage info and they differ
                if first_voltage and other_voltage and first_voltage != other_voltage:
                    conflicts.append({
                        "type": "power_rail_mismatch",
                        "bus_name": rail_name,
                        "map_a_pins": [first_voltage],
                        "map_b_pins": [other_voltage],
                        "severity": "warning",
                        "message": (
                            f"Power rail '{rail_name}' has conflicting voltages: "
                            f"{first_voltage} vs {other_voltage}"
                        )
                    })
    
    # ─── Driver availability validation ────────────────────────────────────
    
    for map_idx, hw_map in enumerate(maps_list):
        peripherals = hw_map.get("peripherals", [])
        
        for peripheral in peripherals:
            if not isinstance(peripheral, dict):
                continue
            
            peripheral_type = peripheral.get("type", "").lower()
            if not peripheral_type:
                continue
            
            # Look up driver for this peripheral type on this SoC (with fallback to alternatives)
            driver_info = _lookup_driver_with_fallback(soc or "", peripheral_type)
            
            if driver_info is None:
                driver_status = "unknown"
            else:
                driver_status = driver_info.get("status", "unknown")
            
            # Update summary
            if driver_status not in driver_summary:
                driver_summary[driver_status] = 0
            driver_summary[driver_status] += 1
            
            # Log conflict if driver is not mainline
            if driver_status != "mainline":
                bus_name = peripheral.get("bus", "unknown")
                driver_module = (
                    driver_info.get("module", "unknown")
                    if driver_info else "unknown"
                )
                
                # Get alternatives for this peripheral type
                alternatives = _get_driver_alternatives(
                    peripheral_type,
                    driver_status,
                    soc or ""
                )
                
                conflict_entry = {
                    "type": "driver_unavailable",
                    "bus_name": bus_name,
                    "peripheral_type": peripheral_type,
                    "map_a_pins": [driver_module],
                    "map_b_pins": [driver_status],
                    "severity": "warning",
                    "message": (
                        f"{peripheral_type.capitalize()} via {bus_name} "
                        f"has driver status: {driver_status}"
                    )
                }
                
                if alternatives:
                    conflict_entry["alternatives"] = alternatives
                
                conflicts.append(conflict_entry)
    
    return {
        "valid": True,  # Always true: warn but don't halt
        "conflicts": conflicts,
        "merged_buses": merged_buses,
        "driver_summary": driver_summary
    }
