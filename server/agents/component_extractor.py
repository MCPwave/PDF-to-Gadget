"""
Component Keyword Detector for PDFs.

Scans PDF text for component-related keywords and section markers,
extracting surrounding context for downstream processing.
"""

import re
from typing import List, Dict, Optional


# ── Component Keywords ─────────────────────────────────────────────────────

COMPONENT_KEYWORDS = {
    "camera", "sensor", "display", "touchscreen", "audio", "wifi",
    "bluetooth", "modem", "nfc", "gps", "accelerometer", "gyro",
    "compass", "temperature", "light", "pressure", "adc", "pwm",
    "rtc", "watchdog"
}

# ── Section Markers ────────────────────────────────────────────────────────

SECTION_KEYWORDS = {
    "connector", "interface", "pinout", "pin map", "pin configuration",
    "pin description", "pin assignment", "connector pin"
}


def preprocess_pdf_text(pdf_text: str) -> str:
    """
    Normalize and clean PDF text.
    
    - Remove common page headers/footers
    - Normalize whitespace
    - Preserve line numbers for reference
    """
    lines = pdf_text.split('\n')
    
    # Remove page numbers and common headers/footers
    cleaned_lines = []
    for line in lines:
        # Skip page numbers and page headers
        if re.match(r'^\s*[\d]+\s*$', line):  # bare page number
            continue
        if re.match(r'^.*?page\s+\d+.*?$', line, re.IGNORECASE):
            continue
        if re.match(r'^.*?-\s*\d+\s*-.*?$', line):  # centered page number
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Normalize whitespace (preserve line breaks)
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text


def detect_component_keywords(pdf_text: str) -> List[Dict]:
    """
    Detect component keywords and section markers in PDF text.
    
    Args:
        pdf_text: Text extracted from PDF
        
    Returns:
        List of dicts with keys:
        - keyword: matched keyword
        - context: 100 chars before/after match
        - section_type: "component" or "section"
        - line_number: line where match was found
        - full_line: the full line containing the match
    """
    pdf_text = preprocess_pdf_text(pdf_text)
    lines = pdf_text.split('\n')
    matches = []
    
    # Build regex pattern with word boundaries
    component_pattern = r'\b(' + '|'.join(re.escape(kw) for kw in COMPONENT_KEYWORDS) + r')\b'
    section_pattern = r'\b(' + '|'.join(re.escape(kw) for kw in SECTION_KEYWORDS) + r')\b'
    
    for line_num, line in enumerate(lines, 1):
        line_lower = line.lower()
        
        # Check for component keywords
        for match in re.finditer(component_pattern, line_lower, re.IGNORECASE):
            keyword = match.group(1)
            start, end = match.span()
            
            # Extract context (100 chars before/after)
            context_start = max(0, start - 100)
            context_end = min(len(line), end + 100)
            context = line[context_start:context_end]
            
            matches.append({
                'keyword': keyword,
                'context': context.strip(),
                'section_type': 'component',
                'line_number': line_num,
                'full_line': line.strip()
            })
        
        # Check for section keywords
        for match in re.finditer(section_pattern, line_lower, re.IGNORECASE):
            keyword = match.group(1)
            start, end = match.span()
            
            # Extract context (100 chars before/after)
            context_start = max(0, start - 100)
            context_end = min(len(line), end + 100)
            context = line[context_start:context_end]
            
            matches.append({
                'keyword': keyword,
                'context': context.strip(),
                'section_type': 'section',
                'line_number': line_num,
                'full_line': line.strip()
            })
    
    return matches


def extract_section_text(pdf_text: str, section_keyword: str, context_lines: int = 20) -> str:
    """
    Extract text block starting from a section header.
    
    Args:
        pdf_text: Full PDF text
        section_keyword: Section header keyword to search for (e.g., "Pin Map")
        context_lines: Number of lines to extract after section header
        
    Returns:
        Extracted text block or empty string if not found
    """
    pdf_text = preprocess_pdf_text(pdf_text)
    lines = pdf_text.split('\n')
    
    # Find the section header
    section_keyword_lower = section_keyword.lower()
    section_start_idx = None
    
    for idx, line in enumerate(lines):
        if section_keyword_lower in line.lower():
            section_start_idx = idx
            break
    
    if section_start_idx is None:
        return ""
    
    # Extract context_lines after header
    end_idx = min(section_start_idx + context_lines + 1, len(lines))
    extracted_lines = lines[section_start_idx:end_idx]
    
    return '\n'.join(extracted_lines)


def categorize_keywords(matches: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Categorize keyword matches by type.
    
    Args:
        matches: List of matches from detect_component_keywords
        
    Returns:
        Dict with "component" and "section" keys
    """
    categorized = {
        'component': [],
        'section': []
    }
    
    for match in matches:
        section_type = match['section_type']
        categorized[section_type].append(match)
    
    return categorized


def get_unique_keywords(matches: List[Dict]) -> Dict[str, int]:
    """
    Get count of unique keywords found.
    
    Args:
        matches: List of matches
        
    Returns:
        Dict mapping keyword -> count
    """
    keyword_counts = {}
    for match in matches:
        kw = match['keyword']
        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    
    return keyword_counts
