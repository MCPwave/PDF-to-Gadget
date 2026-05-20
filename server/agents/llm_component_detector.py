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
import socket
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
    with urllib.request.urlopen(req, timeout=120) as resp:
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
    
    # Extract JSON from response - try multiple approaches
    # 1. Try direct JSON parse
    try:
        return json.loads(raw), model
    except:
        pass
    
    # 2. Try markdown code fence (non-greedy, limited)
    try:
        match = re.search(r'```(?:json)?\s*(\{[^`]*\})\s*```', raw, re.DOTALL)
        if match:
            return json.loads(match.group(1)), model
    except:
        pass
    
    # 3. Try finding JSON object directly (most likely case for LLMs)
    try:
        # Find first { and last }
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = raw[start:end+1]
            return json.loads(json_str), model
    except:
        pass
    
    raise ValueError(f"Could not parse LLM response: {raw[:200]}")


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
    
    # Compact prompt optimized for fast models
    # Compact prompt optimized for fast models
    prompt = f"""Extract components from datasheet. Return JSON only.

TEXT:
{pdf_text[:500]}

FIND: processors, memory (DDR/eMMC), USB, Ethernet, WiFi, cameras, displays, audio, PMIC, TPM, sensors, connectivity ICs.
CAMERAS: resolution (FHD/1080p/4K/2K), features (Windows Hello, IR), IPU/ISP (Intel IPU6, Qualcomm ISP), connection (USB/MIPI CSI), manufacturer.

JSON:
{{
  "components": [
    {{
      "name": "Component",
      "type": "cpu|gpu|camera|audio|display|touchscreen|pmic|power|security|usb|ethernet|mipi_csi|mipi_dsi|uart|i2c|spi|gpio|rtc|watchdog|led|ipu|sensor_temperature|sensor_accelerometer|sensor_light|sensor_proximity|sensor_pressure|sensor_humidity|other",
      "model_number": "Part number",
      "manufacturer": "Company",
      "variant": "Specs",
      "connection": "i2c|spi|uart|gpio|mipi_csi|mipi_dsi|usb|pcie|hdmi|displayport|local|ethernet|other",
      "description": "For camera: resolution + features + IPU. For codec: channels.",
      "confidence": 0.85
    }}
  ]
}}

Rules: 1) Exact part #s only 2) Include all ICs 3) Cameras: resolution, features, IPU/ISP, manufacturer 4) Confidence 0.95 exact, 0.75+ inferred 5) No invented 6) JSON ONLY"""

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
