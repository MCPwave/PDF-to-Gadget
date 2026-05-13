#!/usr/bin/env python3
"""
Connector Parser - Usage Examples
"""

from connector_parser import parse_connector_pins

# Example 1: MIPI CSI Connector
print("=" * 70)
print("Example 1: MIPI CSI Camera Connector")
print("=" * 70)

mipi_text = """
MIPI CSI Connector Interface
Connector Type: 30-pin FPC connector
Operating Voltage: 1.8V IO, 3.3V Core

Pin Map
Pin 1: GND (Ground)
Pin 2: CSI_D0 (Data Lane 0)
Pin 3: CSI_D1 (Data Lane 1)
Pin 4: GND (Ground)
Pin 5: CSI_CLK (Clock)
Pin 6: CSI_HS (Horizontal Sync)
Pin 7: CSI_VS (Vertical Sync)
"""

result = parse_connector_pins(mipi_text)
print(f"Bus Type:      {result['bus_type']}")
print(f"Pins:          {', '.join(result['pins'])}")
print(f"Connector:     {result['connector_type']}")
print(f"Voltage:       {result['voltage']}")
print(f"Confidence:    {result['confidence']:.1%}")

# Example 2: I2C Interface
print("\n" + "=" * 70)
print("Example 2: I2C Interface Header")
print("=" * 70)

i2c_text = """
I2C Control Interface
Pin Configuration: 4-pin standard header (0.1 inch pitch)
Operating Voltage: 3.3V

Pin 1: VCC (Power)
Pin 2: GND (Ground)
Pin 3: SDA (Serial Data)
Pin 4: SCL (Serial Clock)

Optional: INT pin for interrupts
"""

result = parse_connector_pins(i2c_text)
print(f"Bus Type:      {result['bus_type']}")
print(f"Pins:          {', '.join(result['pins'])}")
print(f"Connector:     {result['connector_type']}")
print(f"Voltage:       {result['voltage']}")
print(f"Confidence:    {result['confidence']:.1%}")

# Example 3: USB Type-C
print("\n" + "=" * 70)
print("Example 3: USB Type-C Connector")
print("=" * 70)

usb_text = """
USB Type-C Connector Pinout
Standard: USB 3.1 Gen 1 with Power Delivery
Operating Voltage: 5V/3A (standard), 20V/5A (PD)

Pin Configuration:
GND, TX1_P, TX1_N, VBUS, RX2_N, RX2_P, GND, D+, D-, SBU2
VBUS, RX1_N, RX1_P, GND, TX2_P, TX2_N, GND
"""

result = parse_connector_pins(usb_text)
print(f"Bus Type:      {result['bus_type']}")
print(f"Pins:          {', '.join(result['pins'][:5])}...")
print(f"Connector:     {result['connector_type']}")
print(f"Voltage:       {result['voltage']}")
print(f"Confidence:    {result['confidence']:.1%}")

# Example 4: UART Serial
print("\n" + "=" * 70)
print("Example 4: UART Serial Interface")
print("=" * 70)

uart_text = """
Debug UART Serial Interface
Type: 6-pin standard header
Voltage: 3.3V TTL

Pin Mapping:
1: VCC (3.3V)
2: GND (Ground)
3: TX (Transmit)
4: RX (Receive)
5: RTS (Request to Send)
6: CTS (Clear to Send)
"""

result = parse_connector_pins(uart_text)
print(f"Bus Type:      {result['bus_type']}")
print(f"Pins:          {', '.join(result['pins'])}")
print(f"Connector:     {result['connector_type']}")
print(f"Voltage:       {result['voltage']}")
print(f"Confidence:    {result['confidence']:.1%}")

# Example 5: Mixed/Unknown
print("\n" + "=" * 70)
print("Example 5: Unknown Connector (No Clear Bus Type)")
print("=" * 70)

unknown_text = """
Generic Proprietary Connector
Pin 1: Signal A
Pin 2: Signal B
Pin 3: Signal C
Pin 4: GND
"""

result = parse_connector_pins(unknown_text)
print(f"Bus Type:      {result['bus_type']}")
print(f"Pins:          {', '.join(result['pins'])}")
print(f"Connector:     {result['connector_type']}")
print(f"Voltage:       {result['voltage']}")
print(f"Confidence:    {result['confidence']:.1%}")

print("\n" + "=" * 70)
print("Demo Complete")
print("=" * 70)
