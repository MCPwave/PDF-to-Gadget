import json
import sys
import os

def generate_mermaid_diagram(data):
    """Converts hardware map JSON into Mermaid.js flowchart syntax."""
    soc_name = data.get("soc", "Unknown SoC")
    arch = data.get("arch", "Unknown Arch")
    
    # Start the diagram
    lines = ["graph TD"]
    lines.append(f'    SoC["{soc_name} ({arch})"]:::socStyle')
    
    # Process peripherals
    for item in data.get("peripherals", []):
        name = item.get("name")
        bus = item.get("bus")
        addr = item.get("address", item.get("pin", ""))
        
        # Create a connection label
        label = f"{bus} [{addr}]" if addr else bus
        lines.append(f'    SoC -- "{label}" --> {name.replace(" ", "_")}["{name}"]')

    # Add some basic styling
    lines.append("    classDef socStyle fill:#f96,stroke:#333,stroke-width:4px;")
    
    return "\n".join(lines)

def update_html(mermaid_code):
    """Injects the generated code into the HTML template."""
    template_path = "web/index.html"
    if not os.path.exists(template_path):
        print(f"Error: {template_path} not found. Ensure your web directory is setup.")
        return

    with open(template_path, "r") as f:
        content = f.read()

    # Find the insertion point defined in your web-visualizer.md
    placeholder = "%% MERMAID_INSERTION_POINT %%"
    if placeholder in content:
        new_content = content.replace(placeholder, mermaid_code)
        with open("web/output.html", "w") as f:
            f.write(new_content)
        print("Success: Visualization generated at web/output.html")
    else:
        print("Error: Placeholder not found in index.html")

if __name__ == "__main__":
    # Expects JSON piped from stdin (e.g., cat map.json | python3 visualizer.py)
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print("No data received via stdin.")
            sys.exit(1)
            
        json_map = json.loads(input_data)
        mermaid_string = generate_mermaid_diagram(json_map)
        update_html(mermaid_string)
        
    except json.JSONDecodeError:
        print("Error: Input was not valid JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
