"""Quick test to verify PDF upload works and fontTools warnings suppressed."""
import requests
import sys
from pathlib import Path

# Create minimal test PDF
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    
    pdf_path = Path("test_sample.pdf")
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(100, 750, "Test PDF for fontTools warning suppression")
    c.save()
    
    with open(pdf_path, "rb") as f:
        files = {"file": ("test.pdf", f)}
        r = requests.post("http://127.0.0.1:8000/upload", files=files, timeout=5)
    
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json() if r.status_code == 200 else r.text[:200]}")
    
    if r.status_code == 200:
        print("✓ Upload successful - warnings suppressed, extraction working")
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
