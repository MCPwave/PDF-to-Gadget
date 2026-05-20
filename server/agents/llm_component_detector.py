"""
LLM-based Component Detector: Uses AI models to detect ALL component types.

Supports:
- Ollama (local)
- OpenAI (cloud)
- Anthropic (cloud)
- Gemini (cloud)
- Groq (cloud)

Falls back to heuristic detection if LLM unavailable.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Dict, Optional, Tuple


def _ollama_list_models(host: str) -> List[str]:
    """Return model names available in Ollama; empty list on any error."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except:
        return []


def _ollama_chat(host: str, model: str, prompt: str) -> str:
    """Call Ollama chat API."""
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def _try_ollama(prompt: str) -> Tuple[Dict, str]:
    """Try to extract components using Ollama."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "")
    
    if not model:
        models = _ollama_list_models(host)
        if not models:
            raise RuntimeError("ollama_unavailable")
        
        # Prefer larger, more capable models
        preferred = ["mistral", "llama2", "neural-chat", "orca"]
        model = next(
            (m for pref in preferred for m in models if pref in m.lower()),
            models[0],
        )
    
    raw = _ollama_chat(host, model, prompt)
    
    # Extract JSON from response
    try:
        # Try direct JSON parse
        return json.loads(raw), model
    except:
        # Try to extract JSON from markdown code blocks
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
        if match:
            return json.loads(match.group(1)), model
        raise ValueError(f"Could not parse LLM response: {raw}")


def _openai_compatible(base_url: str, api_key: str, model: str, prompt: str) -> Dict:
    """Call OpenAI-compatible API (OpenAI, Groq, etc)."""
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return json.loads(data["choices"][0]["message"]["content"])


def _anthropic_api(api_key: str, model: str, prompt: str) -> Dict:
    """Call Anthropic Claude API."""
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
            "system": "You are a hardware engineer. Extract components from datasheets. Always respond with valid JSON.",
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    content = data["content"][0]["text"]
    
    # Extract JSON from response
    try:
        return json.loads(content)
    except:
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Could not parse response: {content}")


def detect_components_with_llm(
    pdf_text: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
) -> Tuple[List[Dict], str]:
    """
    Detect all components using LLM.
    
    Args:
        pdf_text: Extracted text from PDF
        model: Model name (e.g., "gpt-4", "claude-3-sonnet")
        api_key: API key for cloud providers
        provider: Provider name (openai, anthropic, gemini, groq, ollama)
    
    Returns:
        (components_list, model_used)
    """
    
    prompt = f"""You are a hardware component detection expert analyzing a SoM/SoC/board datasheet.

TASK: Extract EVERY component, IC, module, and peripheral visible in this datasheet.
Include: processors, accelerators, interfaces, sensors, connectors, power management, security, audio, video, and system components.

Datasheet excerpt:
{pdf_text[:5000]}

===== COMPREHENSIVE COMPONENT CATEGORIES TO SEARCH FOR =====

1. PROCESSORS & ACCELERATORS (Priority HIGH)
   - CPUs: ARM Cortex (A78, A76, A72, A53, M4, M7), Intel (Core, Atom, Xeon), AMD (Ryzen)
   - GPUs: NVIDIA (GeForce, Tegra, Maxwell, Pascal, Turing, Ada), AMD Radeon, Intel (Iris Xe, Arc), ARM Mali (G77, G78, G710), Qualcomm Adreno, Imagination PowerVR, Vivante
   - NPUs: Qualcomm Hexagon, NVIDIA NVDLA, Google Coral, Mediatek APU, Kirin NPU
   - TPUs: Google TPU (v2, v3, v4, v5), Edge TPU
   - DSPs: Qualcomm Hexagon, TI C66x, C67x, Cadence Tensilica

2. MEMORY INTERFACES & STORAGE (Priority HIGH)
   - DRAM: DDR3, DDR4, DDR5, LPDDR4, LPDDR5, HBM2
   - Flash: eMMC (size), NOR Flash, NAND Flash, UFS, SD Card Interface
   - Cache: L2, L3 sizes and types

3. COMMUNICATION INTERFACES (Priority HIGH)
   - USB: versions (2.0, 3.0, 3.1, 3.2, USB-C with power delivery), host/device/OTG modes, hub chips
   - Ethernet: speeds (10/100/1000/2.5G/5G/10G), PHY chips (Realtek RTL8211, Broadcom, TI)
   - WiFi/BLE: 802.11a/b/g/n/ac/ax, Bluetooth versions, antenna designs, RF chips (Qualcomm WCN, Broadcom, Realtek)
   - Serial: UART, RS232, RS485 count and voltages
   - I2C/SPI: bus width, speed, multiplexing options
   - CAN: version, transceiver chips
   - RS-485: driver ICs
   - GPIO: count, voltage domains, expander ICs

4. CAMERA & VIDEO INTERFACES (Priority HIGH)
   - CSI: MIPI CSI-2 (versions 6, 7, 8, 9), lanes (2/4), speeds
   - Sensor ICs: Sony IMX (IMX477, IMX219, IMX477R, IMX500), OmniVision OV (OV5640, OV8856), Arducam, GalaxyCore GC
   - Webcam: FHD (1080p), 4K, 2K resolutions, USB webcams, Windows Hello compatibility
   - Image Processing: Intel IPU (IPU6, IPU5), Qualcomm ISP, image signal processors
   - Features: Auto-focus, face detection, depth sensing, IR sensors
   - Connectors: Flex cable, ribbon connectors, BNC for CVBS, USB for webcams

5. DISPLAY & TOUCHSCREEN (Priority HIGH)
   - DSI: MIPI DSI versions, lane count, dual DSI
   - Display Panels: LCD, OLED, eInk, TFT, IPS technologies
   - HDMI: versions (1.4, 2.0, 2.1), CEC, audio support
   - DisplayPort: versions (1.2, 1.3, 1.4, 2.0)
   - LVDS: dual/quad LVDS, differential pairs
   - RGB/Parallel: 18-bit, 24-bit, timing
   - Touchscreen Controllers: FocalTech FT5426, Goodix GT911/GT928, Synaptics DSX/RMI, Ilitek ILI2511, Elantech
   - Touch Interfaces: Capacitive, resistive, multi-touch, I2C/SPI connected

6. AUDIO COMPONENTS (Priority HIGH)
   - Audio Codecs: Realtek ALC (ALC5640, ALC5651, ALC892), Cirrus Logic (CS4341, CS4370), Qualcomm Qdsp, Wolfson, Analog Devices
   - Audio Amplifiers: Class D, Class AB, TPA, NXP, Infineon
   - Microphone: Digital (PDM), analog, array microphones
   - Speaker Drivers: mono, stereo, 2.1, 5.1, count and power
   - Audio Jacks: 3.5mm combo (headphone+mic), SPDIF, optical

7. POWER MANAGEMENT (Priority HIGH)
   - PMICs: Axp (AXP803, AXP809), TPS (TPS65217, TPS6598), Maxim (MAX77686), BD (BD71847), NXP (PF8100)
   - Voltage Regulators: buck, boost, LDO, count and output rails
   - Battery Management: charger ICs, fuel gauges, BMS controllers
   - USB Power Delivery: Controller ICs, USB PD version support, max power watts
   - AC Adapters: Input voltage, output voltage, current rating
   - Power Distribution: Barrel jack, USB-C power, proprietary connectors

8. SECURITY & CRYPTOGRAPHY (Priority HIGH)
   - TPM: TPM 1.2, TPM 2.0, manufacturers (Infineon SLB9670, ST ST33, Nuvoton)
   - Secure Elements: NXP SE050, NXP A7005, others
   - Crypto Accelerators: dedicated crypto engines, secure boot support
   - RNG: Random Number Generator modules
   - Secure Enclave: Apple Secure Enclave equivalent on other platforms

9. SENSORS (Priority MEDIUM)
   - Temperature: TMP36, BMP280, BME280, MCP9808, TI TMP sensors
   - Accelerometer/Gyro/IMU: MPU-6050, LSM6DSM, ICM-20948, 6-axis, 9-axis
   - Light: BH1750, APDS-9960, TCS34725
   - Proximity: VL53L0X, VL53L1X, APDS-9960 (dual-function)
   - Barometer: BMP280, BME680
   - Humidity: DHT22, BME680, SHT31
   - Gas/Air Quality: BME680, CCS811
   - Compass/Magnetometer: HMC5883L, AK8963

10. SYSTEM MANAGEMENT (Priority MEDIUM)
    - RTC: DS1307, PCF8563, iMX6 internal RTC
    - Watchdog: Dedicated chips or SoC internal
    - ACPI: BIOS/UEFI/firmware support indicators
    - Fan Control: Temperature sensors + fan drivers
    - System Monitor: Voltage/current monitors, health sensors

11. CONNECTORS & PHYSICAL INTERFACES (Priority MEDIUM)
    - Standard: USB-A, USB-C, Micro-USB, HDMI, Ethernet RJ45
    - Custom: Hirose, DF40, proprietary board-to-board connectors
    - Debug: JTAG, SWD, UART headers, test points
    - Power: DC barrel jack, USB-C PD, internal power rails

12. MEMORY & STORAGE ICs (Priority MEDIUM)
    - DDR Controllers: count, channels, error correction (ECC)
    - Storage Controllers: eMMC, NVMe, SATA, QSPI/Octal-SPI
    - Cache RAM: amount, speed
    - EEPROM: size, purpose (MAC address, calibration)

13. IMAGE PROCESSING (Priority HIGH - Often Missed!)
    - IPU: Intel IPU (IPU6, IPU5, IPU4), Qualcomm ISP, MediaTek, ARM
    - ISP: Image Signal Processors with specific versions
    - Camera Features: FHD/4K resolution support, video encoding (H.264, H.265, VP9)
    - Biometric: Depth sensors, IR for face detection, Windows Hello/Hello IR support
    - AI Accelerators for Camera: On-die or separate AI engines for image processing
    - Webcam Features: USB webcams with specific resolution (1080p/2K/4K), audio (built-in mic)

===== COMPONENT REFERENCE EXAMPLES =====

Image Processing Units:
  Intel: IPU6, IPU5, IPU4 (with specific camera pipeline capabilities)
  Qualcomm: ISP with Snapdragon variants
  MediaTek: ISP in MT series SoCs
  ARM: ISP in Mali/Cortex variants

Audio Codecs by Manufacturer:
  Realtek: ALC5640, ALC5651, ALC892, ALC1220
  Cirrus Logic: CS4341, CS4370, CS4272, CS4382
  Qualcomm: Qdsp6, Hexagon
  Wolfson: WM8960, WM8994
  Analog Devices: ADAU1361, ADAU1701

Touchscreen Controllers:
  FocalTech: FT5426, FT6236, FT5216
  Goodix: GT911, GT928, GT917S
  Synaptics: RMI4, DSX series
  Ilitek: ILI2511, ILI2512
  Elantech: ET7XX series

Audio Amplifiers:
  Texas Instruments: TPA2013, TPA3138
  NXP: JQ6500, TEA5767
  Infineon: MA12070

Security ICs:
  Infineon: SLB9670 (TPM 2.0), SLB9645 (TPM 1.2)
  ST Microelectronics: ST33 TPM
  NXP: SE050, SE051

Power Management ICs:
  Axpower: AXP803, AXP809
  TI: TPS65217, TPS6598
  Maxim: MAX77686, MAX20086
  NXP: PF8100, PCA9420

===== JSON RESPONSE FORMAT =====

Return ONLY valid JSON (no markdown, no code fences). Use this structure:

```
{{
  "components": [
    {{
      "name": "Exact component name or model",
      "type": "cpu|gpu|npu|tpu|dsp|camera|display|touchscreen|audio|sensor_temperature|sensor_accelerometer|sensor_light|sensor_proximity|sensor_pressure|sensor_humidity|pmic|power|security|uart|i2c|spi|usb|ethernet|mipi_csi|mipi_dsi|gpio|rtc|watchdog|led|ipu|other",
      "model_number": "Exact IC/part number (e.g., RTL8211E, ALC5640, IPU6, IMX477)",
      "manufacturer": "Company name (Intel, Sony, OmniVision, Realtek, etc.)",
      "version": "Generation/revision (e.g., v2.0, Gen 4, CSI-2 v1.3, IPU6 Gen 2)",
      "variant": "Specific model variant with specs (e.g., FHD Webcam, 1080p, RTL8211E-VB, MIPI CSI-2)",
      "connection": "How it connects to main SoC: i2c|spi|uart|gpio|mipi_csi|mipi_dsi|usb|pcie|hdmi|displayport|local|ethernet|other",
      "connection_version": "Protocol version (e.g., I2C 7.0, USB 3.1, MIPI CSI-2 v1.3, USB Video Class 1.5)",
      "voltage": "Operating voltage (3.3V, 1.8V, 1.2V)",
      "description": "Detailed description including key specifications: For CAMERAS - resolution (FHD/1080p/4K), type (webcam/sensor), features (Windows Hello, IR, face detection, IPU details). For AUDIO - codec type, channels, sample rate. For DISPLAYS - panel tech, resolution. For SECURITY - TPM version, type.",
      "confidence": 0.85-0.95
    }}
  ]
}}
```

===== CAMERA COMPONENT EXTRACTION RULES (Critical!) =====

When you find ANY camera, webcam, or image processing mention, EXTRACT:
1. Resolution: FHD (1080p), 4K, 2K, QVGA, VGA - put in "variant" field
2. Type: Webcam, CSI Sensor, MIPI connector, USB - clarify in description
3. Features: Windows Hello, Express Sign-In, IR (infrared), face detection, biometric - include in description
4. IPU/ISP Details: Intel IPU6, IPU5, Qualcomm ISP, image processor - MUST be in model_number or variant
5. Connection: USB (for webcams), MIPI CSI (for sensors), parallel RGB - specify in connection field
6. Manufacturer: Intel (IPU), Sony (IMX sensors), OmniVision (OV sensors), etc.

EXAMPLES:
- "CAMERA FHD (1080p) webcam Windows Hello compliant, Express Sign-In, Intel IPU6"
  → name: "FHD Webcam with IPU6"
     type: "camera"
     model_number: "IPU6"
     manufacturer: "Intel"
     version: "IPU6 Gen 2" (if mentioned)
     variant: "FHD 1080p Webcam with Windows Hello IR"
     connection: "usb"
     description: "FHD (1080p) USB webcam with Windows Hello biometric support (infrared), Express Sign-In compatible, integrated Intel IPU6 image processor"

===== EXTRACTION RULES =====

1. COMPLETENESS: Include EVERY component visible in datasheet, even small passive ICs if named
2. ACCURACY: Use exact model numbers from datasheet, not generic names
3. MANUFACTURER: Always specify - crucial for compatibility and sourcing
4. VERSIONS: Always include MIPI/USB/protocol versions when present
5. CONNECTIONS: Specify HOW it connects (bus, protocol, direct pin)
6. CONFIDENCE: 0.95+ for exact ICs found with model numbers, 0.75-0.85 for inferred types
7. AVOID GENERICS: Don't add hypothetical components not mentioned in datasheet

===== DUPLICATE HANDLING =====

If same component appears multiple times (e.g., 2 identical USB ports):
- Include ALL instances separately (they consume separate pins/address space)
- Set instance count in description if applicable

===== CRITICAL COMPLETENESS CHECKLIST =====

Before finalizing, verify you found:
- Main SoC/CPU (and its peripheral features)
- All memory types (DRAM channel config, flash storage)
- All communication buses (USB, Ethernet, WiFi, serial)
- All sensors and peripherals
- All power components (PMIC, regulators, connectors)
- All security modules (TPM, secure elements)
- All display/touchscreen controllers
- All audio components (codec, amp, connectors)
- System management (RTC, watchdog, ACPI indicators)
- Debug interfaces (JTAG, SWD, UART headers)

Return ONLY the JSON object. No explanations, no markdown backticks."""

    # Try providers in order
    result = None
    model_used = "unknown"
    
    # 1. Try Ollama (local first)
    if not provider or provider == "ollama":
        try:
            result, model_used = _try_ollama(prompt)
            return result.get("components", []), f"ollama/{model_used}"
        except Exception as e:
            if provider == "ollama":
                raise
    
    # 2. Try OpenAI
    if not provider or provider == "openai":
        if api_key or os.getenv("OPENAI_API_KEY"):
            try:
                key = api_key or os.getenv("OPENAI_API_KEY")
                model_name = model or "gpt-4-turbo-preview"
                result = _openai_compatible(
                    "https://api.openai.com/v1",
                    key,
                    model_name,
                    prompt
                )
                return result.get("components", []), f"openai/{model_name}"
            except Exception as e:
                if provider == "openai":
                    raise
    
    # 3. Try Anthropic
    if not provider or provider == "anthropic":
        if api_key or os.getenv("ANTHROPIC_API_KEY"):
            try:
                key = api_key or os.getenv("ANTHROPIC_API_KEY")
                model_name = model or "claude-3-sonnet-20240229"
                result = _anthropic_api(key, model_name, prompt)
                return result.get("components", []), f"anthropic/{model_name}"
            except Exception as e:
                if provider == "anthropic":
                    raise
    
    # 4. Try Groq
    if not provider or provider == "groq":
        if api_key or os.getenv("GROQ_API_KEY"):
            try:
                key = api_key or os.getenv("GROQ_API_KEY")
                model_name = model or "mixtral-8x7b-32768"
                result = _openai_compatible(
                    "https://api.groq.com/openai/v1",
                    key,
                    model_name,
                    prompt
                )
                return result.get("components", []), f"groq/{model_name}"
            except Exception as e:
                if provider == "groq":
                    raise
    
    raise RuntimeError("No LLM provider available (set OLLAMA_HOST, OPENAI_API_KEY, etc)")


def format_components_for_pipeline(llm_components: List[Dict]) -> List[Dict]:
    """Convert LLM component format to pipeline format."""
    formatted = []
    
    for comp in llm_components:
        # Build display name with manufacturer and version
        name_parts = [comp.get("name", "Unknown")]
        
        # Add manufacturer if available
        manufacturer = comp.get("manufacturer", "").strip()
        if manufacturer:
            name_parts.append(f"({manufacturer})")
        
        # Add variant if available
        variant = comp.get("variant", "").strip()
        if variant:
            name_parts.append(variant)
        
        # Add version if available
        version = comp.get("version", "").strip()
        if version:
            name_parts.append(f"v{version}" if not version.startswith("v") else version)
        
        display_name = " ".join(name_parts)
        
        formatted.append({
            "id": f"component_{comp.get('model_number', comp.get('name', 'unknown')).lower().replace(' ', '_')}",
            "name": display_name,
            "type": comp.get("type", "other"),
            "component_ic": {
                "name": comp.get("model_number", ""),
                "vendor": manufacturer,
                "type": comp.get("type", "unknown"),
            },
            "connection_type": comp.get("connection", "unknown"),
            "connection_version": comp.get("connection_version", ""),
            "voltage": comp.get("voltage", ""),
            "description": comp.get("description", ""),
            "manufacturer": manufacturer,
            "version": version,
            "variant": variant,
            "source": "llm_detection",
            "confidence": comp.get("confidence", 0.8),
            "is_component": True,
        })
    
    return formatted
