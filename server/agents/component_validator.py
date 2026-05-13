"""
Component Connection Validator — validates component connections against board capabilities.

Checks:
  1. Required board interface exists in board peripherals
  2. Voltage matching between component connector and board interface
  3. Component IC driver availability
  4. Board interface driver availability
  
Returns detailed validation report with alternatives for issues.
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


def _parse_voltage(voltage_str: str) -> Optional[float]:
    """
    Parse voltage string to float value (in volts).
    Examples: "3.3V" → 3.3, "1.8V" → 1.8, "5V" → 5.0
    """
    if not voltage_str:
        return None
    # Extract numeric part and 'V' suffix
    match = re.match(r"([\d.]+)\s*V", str(voltage_str), re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _voltages_compatible(component_voltage: str, board_voltage: str, tolerance: float = 0.1) -> bool:
    """
    Check if component and board voltages are compatible (within tolerance).
    
    Args:
        component_voltage: Component connector voltage (e.g., "1.8V")
        board_voltage: Board interface voltage (e.g., "1.8V")
        tolerance: Voltage tolerance in volts (default 0.1V = ±100mV)
    
    Returns:
        True if voltages match within tolerance, False otherwise
    """
    comp_v = _parse_voltage(component_voltage)
    board_v = _parse_voltage(board_voltage)
    
    if comp_v is None or board_v is None:
        return False
    
    return abs(comp_v - board_v) <= tolerance


def _find_board_interface(board_map: dict, required_interface: str) -> Optional[dict]:
    """
    Find board peripheral matching the required interface.
    
    Args:
        board_map: Board hardware map with 'peripherals' key
        required_interface: Required interface name (e.g., "MIPI_CSI0")
    
    Returns:
        Peripheral dict matching the interface, or None if not found
    """
    peripherals = board_map.get("peripherals", [])
    for peripheral in peripherals:
        if not isinstance(peripheral, dict):
            continue
        # Match by bus name or id
        if (peripheral.get("bus") == required_interface or 
            peripheral.get("id") == required_interface):
            return peripheral
    return None


def _get_interface_type(interface_name: str) -> str:
    """
    Extract interface type from interface name.
    Examples: "MIPI_CSI0" → "mipi_csi", "I2C0" → "i2c", "SPI1" → "spi"
    """
    if not interface_name:
        return "unknown"
    # Extract alphabetic and underscore parts (stop at digits)
    match = re.match(r"([A-Z_0-9]+)(?:\d+)?", interface_name.upper())
    if match:
        # Remove trailing digits to get the base interface type
        base = match.group(1)
        # Remove all digits from the end
        base = re.sub(r"\d+$", "", base)
        return base.lower()
    return "unknown"


def validate_component_connections(
    board_map: dict,
    components_list: List[dict],
) -> dict:
    """
    Validate component connections against board capabilities.
    
    Args:
        board_map: Board hardware map containing:
            - soc: SoC name for driver lookup
            - peripherals: List of board peripherals with bus, voltage, etc.
        components_list: List of component peripheral objects, each containing:
            - id, name, type
            - connector.required_board_interface: Required board interface (e.g., "MIPI_CSI0")
            - connector.voltage: Component connector voltage (e.g., "1.8V")
            - component_ic.name: IC name for driver lookup (e.g., "OV5647")
            - component_ic.type: IC type for driver lookup (e.g., "camera_sensor")
    
    Returns:
        {
          "valid": True,  # always true (warn mode)
          "component_status": [
            {
              "component_id": "camera_ov5647",
              "component_name": "OV5647 Camera",
              "required_interface": "MIPI_CSI0",
              "status": "OK" | "MISMATCH" | "NO_DRIVER" | "NO_INTERFACE",
              "message": "...",
              "drivers": {
                "ic_driver": {name: "ov5647", status: "mainline"},
                "interface_driver": {name: "bcm2835-unicam", status: "mainline"}
              },
              "alternatives": [  # if MISMATCH or NO_DRIVER
                {
                  "connection_type": "usb",
                  "driver_status": "backport",
                  "effort": "medium"
                }
              ]
            }
          ],
          "summary": {
            "total_components": 3,
            "ok": 2,
            "warnings": 1,
            "blocking": 0
          }
        }
    """
    soc = board_map.get("soc", "")
    component_status = []
    
    summary = {
        "total_components": len(components_list),
        "ok": 0,
        "warnings": 0,
        "blocking": 0
    }
    
    for component in components_list:
        if not isinstance(component, dict):
            continue
        
        comp_id = component.get("id", "unknown")
        comp_name = component.get("name", comp_id)
        comp_type = component.get("type", "unknown").lower()
        
        # Extract connector and IC info
        connector = component.get("connector", {})
        component_ic = component.get("component_ic", {})
        
        required_interface = connector.get("required_board_interface")
        connector_voltage = connector.get("voltage")
        ic_name = component_ic.get("name")
        ic_type = component_ic.get("type")
        
        # Initialize result entry
        result = {
            "component_id": comp_id,
            "component_name": comp_name,
            "required_interface": required_interface or "unknown",
            "status": "OK",
            "message": "",
            "drivers": {
                "ic_driver": {"name": "unknown", "status": "unknown"},
                "interface_driver": {"name": "unknown", "status": "unknown"}
            },
            "alternatives": []
        }
        
        # ─── Check 1: Interface exists ────────────────────────────────────────
        if not required_interface:
            result["status"] = "MISMATCH"
            result["message"] = "Component missing required_board_interface"
            summary["warnings"] += 1
            component_status.append(result)
            continue
        
        board_interface = _find_board_interface(board_map, required_interface)
        if not board_interface:
            result["status"] = "NO_INTERFACE"
            result["message"] = f"Board does not have required interface '{required_interface}'"
            # Get alternatives
            result["alternatives"] = _get_connection_alternatives(comp_type, soc)
            summary["warnings"] += 1
            component_status.append(result)
            continue
        
        # ─── Check 2: Voltage matching ────────────────────────────────────────
        board_voltage = board_interface.get("voltage")
        if connector_voltage and board_voltage:
            if not _voltages_compatible(connector_voltage, board_voltage):
                result["status"] = "MISMATCH"
                result["message"] = (
                    f"Voltage mismatch: component needs {connector_voltage}, "
                    f"board interface provides {board_voltage}"
                )
                result["alternatives"] = _get_connection_alternatives(comp_type, soc)
                summary["warnings"] += 1
                component_status.append(result)
                continue
        
        # ─── Check 3: Component IC driver ────────────────────────────────────
        ic_driver_status = "unknown"
        ic_driver_module = "unknown"
        
        # Try lookup by IC type first (more reliable)
        if ic_type:
            ic_driver_info = _lookup_db(soc, ic_type)
            if ic_driver_info:
                ic_driver_status = ic_driver_info.get("status", "unknown")
                ic_driver_module = ic_driver_info.get("module", "unknown")
        
        # Fallback: try by component type
        if ic_driver_status == "unknown" and comp_type != "unknown":
            comp_driver_info = _lookup_db(soc, comp_type)
            if comp_driver_info:
                ic_driver_status = comp_driver_info.get("status", "unknown")
                ic_driver_module = comp_driver_info.get("module", "unknown")
        
        result["drivers"]["ic_driver"]["name"] = ic_name or ic_driver_module
        result["drivers"]["ic_driver"]["status"] = ic_driver_status
        
        if ic_driver_status == "unknown":
            result["status"] = "NO_DRIVER"
            result["message"] = f"No driver found for IC type '{ic_type or comp_type}'"
            result["alternatives"] = _get_connection_alternatives(comp_type, soc)
            summary["warnings"] += 1
            component_status.append(result)
            continue
        
        # ─── Check 4: Board interface driver ──────────────────────────────────
        interface_type = _get_interface_type(required_interface)
        interface_driver_info = _lookup_db(soc, interface_type)
        
        interface_driver_status = "unknown"
        interface_driver_module = "unknown"
        
        if interface_driver_info:
            interface_driver_status = interface_driver_info.get("status", "unknown")
            interface_driver_module = interface_driver_info.get("module", "unknown")
        
        result["drivers"]["interface_driver"]["name"] = interface_driver_module
        result["drivers"]["interface_driver"]["status"] = interface_driver_status
        
        if interface_driver_status == "unknown":
            result["status"] = "NO_DRIVER"
            result["message"] = f"No driver found for board interface '{interface_type}'"
            result["alternatives"] = _get_connection_alternatives(comp_type, soc)
            summary["warnings"] += 1
            component_status.append(result)
            continue
        
        # ─── All checks passed ────────────────────────────────────────────────
        result["status"] = "OK"
        result["message"] = f"Compatible: IC driver ({ic_driver_module}) + interface driver ({interface_driver_module})"
        summary["ok"] += 1
        component_status.append(result)
    
    return {
        "valid": True,  # Always true (warn mode, don't halt)
        "component_status": component_status,
        "summary": summary
    }


def _get_connection_alternatives(peripheral_type: str, soc: str) -> List[Dict[str, Any]]:
    """
    Get alternative connection types and their driver statuses.
    
    Args:
        peripheral_type: Type of peripheral (e.g., "camera", "display")
        soc: SoC name for driver lookups
    
    Returns:
        List of alternative connection dicts with driver info
    """
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
        
        effort = "medium"
        if alt_status == "mainline":
            effort = "low"
        elif alt_status == "vendor" or alt_status == "unknown":
            effort = "high"
        
        result.append({
            "connection_type": alt_connection_type,
            "driver_status": alt_status,
            "effort": effort
        })
    
    return result
