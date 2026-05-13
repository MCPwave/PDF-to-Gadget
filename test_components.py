import sys
import pdfplumber
sys.path.insert(0, '/home/capo02/work/cop1/server')

from agents.component_extractor import detect_component_keywords
from agents.ic_matcher import match_known_ics
from agents.connector_parser import parse_connectors

pdf_files = [
    ('/home/capo02/work/cop1/tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf', 'Board'),
    ('/home/capo02/work/cop1/tests/AR2020.pdf', 'Camera')
]

print("\n" + "=" * 80)
print("HEURISTIC-BASED EXTRACTION")
print("=" * 80 + "\n")

for pdf_path, label in pdf_files:
    filename = pdf_path.split('/')[-1]
    print(f"📄 {label}: {filename}")
    print("-" * 80)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page_num, page in enumerate(pdf.pages[:10], 1):  # First 10 pages
                full_text += (page.extract_text() or "") + "\n"
        
        print(f"✓ Extracted {len(full_text):,} chars from {len(pdf.pages)} pages")
        
        # Component keywords
        keywords = detect_component_keywords(full_text)
        if keywords:
            print(f"\n✅ Keywords detected ({len(keywords)}):")
            for kw in keywords[:5]:
                print(f"  • {kw.get('keyword', 'unknown')}: {kw.get('context', '')[:50]}")
        
        # Known ICs
        ics = match_known_ics(full_text)
        if ics:
            print(f"\n✅ Known ICs found ({len(ics)}):")
            for ic in ics[:5]:
                print(f"  • {ic.get('ic_name', 'unknown')} ({ic.get('category', 'unknown')})")
                print(f"    Confidence: {ic.get('confidence', 0):.0%}")
        
        # Connectors
        connectors = parse_connectors(full_text)
        if connectors:
            print(f"\n✅ Connectors detected ({len(connectors)}):")
            for conn in connectors[:3]:
                print(f"  • {conn.get('bus_type', 'unknown')}")
                if conn.get('pins'):
                    print(f"    Pins: {conn.get('pins', [])[:3]}...")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print()

