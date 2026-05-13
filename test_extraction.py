import sys
import io
import pdfplumber
sys.path.insert(0, '/home/capo02/work/cop1/server')

from agents import librarian

def extract_pdf_sections(pdf_path):
    """Extract PDF content grouped into logical sections."""
    sections = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append({
                    "heading": f"Page {page_num}",
                    "text": text,
                    "page_start": page_num,
                    "page_end": page_num,
                })
    return sections

pdf_files = [
    ('/home/capo02/work/cop1/tests/Jetson_Orin_NX_DS-10712-001_v0.5.pdf', 'Board'),
    ('/home/capo02/work/cop1/tests/AR2020.pdf', 'Camera Component')
]

print("\n" + "=" * 80)
print("TESTING PDF EXTRACTION")
print("=" * 80 + "\n")

all_maps = []
for pdf_path, label in pdf_files:
    print(f"📄 {label}: {pdf_path.split('/')[-1]}")
    print("-" * 80)
    
    try:
        sections = extract_pdf_sections(pdf_path)
        print(f"  ✓ Extracted {len(sections)} sections from PDF")
        
        hw_map, mode, section_log = librarian.run_sections(sections, model_override="")
        print(f"  ✓ Extraction mode: {mode}")
        
        # Show board info
        if hw_map:
            print(f"\n✅ Hardware Map Extracted:")
            print(f"  Board Name: {hw_map.get('board_name', 'Unknown')}")
            print(f"  SoC: {hw_map.get('soc', 'Unknown')}")
            print(f"  Architecture: {hw_map.get('arch', 'Unknown')}")
            print(f"  CPU Core: {hw_map.get('cpu_core', 'Unknown')}")
            
            # Show components
            peripherals = hw_map.get('peripherals', [])
            components = [p for p in peripherals if p.get('is_component', False)]
            
            print(f"\n  Peripherals: {len(peripherals)} total")
            print(f"  Components: {len(components)} detected")
            
            if components:
                print(f"\n  Component Details:")
                for comp in components:
                    print(f"    • {comp.get('name', 'Unknown')}")
                    print(f"      - Type: {comp.get('type', 'Unknown')}")
                    print(f"      - Connection: {comp.get('connection_type', 'Unknown')}")
                    ic = comp.get('component_ic', {})
                    if ic:
                        print(f"      - IC: {ic.get('name', 'Unknown')}")
                        print(f"      - Driver: {ic.get('driver_status', 'Unknown')}")
            
            all_maps.append(hw_map)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()

# Merge maps
if len(all_maps) > 1:
    print("\n" + "=" * 80)
    print("MERGING HARDWARE MAPS")
    print("=" * 80 + "\n")
    
    try:
        merged = librarian.merge_hardware_maps(all_maps)
        print(f"✅ Merge successful:")
        print(f"  Board SoC: {merged.get('soc', 'Unknown')}")
        print(f"  Total Peripherals: {len(merged.get('peripherals', []))}")
        
        components = [p for p in merged.get('peripherals', []) if p.get('is_component', False)]
        print(f"  Total Components: {len(components)}")
        
        print(f"\n📊 Component Summary:")
        for comp in components:
            print(f"    • {comp.get('name', 'Unknown')} ({comp.get('type', 'unknown')})")
    except Exception as e:
        print(f"  ✗ Merge error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80 + "\n")
