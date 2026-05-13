import sys
import pdfplumber
sys.path.insert(0, '/home/capo02/work/cop1/server')

from agents.component_extractor import extract_components_from_text
from agents.ic_matcher import match_known_ics
from agents.connector_parser import parse_connectors

pdf_files = [
    '/home/capo02/work/cop1/tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf',
    '/home/capo02/work/cop1/tests/AR2020.pdf'
]

print("\n" + "=" * 80)
print("HEURISTIC-BASED COMPONENT EXTRACTION TEST")
print("=" * 80 + "\n")

for pdf_path in pdf_files:
    label = pdf_path.split('/')[-1]
    print(f"📄 Processing: {label}")
    print("-" * 80)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages[:5]:  # First 5 pages for speed
                full_text += (page.extract_text() or "") + "\n"
        
        print(f"✓ Extracted {len(full_text)} characters from PDF")
        
        # Extract components
        components = extract_components_from_text(full_text)
        if components:
            print(f"\n✅ Components found ({len(components)}):")
            for comp in components:
                print(f"  • Type: {comp.get('type', 'unknown')}")
                print(f"    Confidence: {comp.get('confidence', 0.5):.1%}")
                print(f"    Context: {comp.get('context', '')[:60]}...")
        else:
            print(f"\n⚠ No components detected via keywords")
        
        # Match ICs
        known_ics = match_known_ics(full_text)
        if known_ics:
            print(f"\n✅ Known ICs found ({len(known_ics)}):")
            for ic in known_ics[:5]:
                print(f"  • {ic.get('ic_name', 'unknown')}")
                print(f"    Confidence: {ic.get('confidence', 0.5):.1%}")
                print(f"    Category: {ic.get('category', 'unknown')}")
        else:
            print(f"\n⚠ No known ICs matched")
        
        # Parse connectors
        connectors = parse_connectors(full_text)
        if connectors:
            print(f"\n✅ Connectors found ({len(connectors)}):")
            for conn in connectors[:5]:
                print(f"  • Type: {conn.get('bus_type', 'unknown')}")
                print(f"    Pins: {conn.get('pins', [])}")
        else:
            print(f"\n⚠ No connectors detected")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print()

