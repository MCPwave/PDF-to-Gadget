# Project Manifest: PDF-to-Gadget

## Execution Pipeline
1. **Ingest:** User provides datasheet snippet or PDF.
2. **Map:** `@librarian` generates `hardware_map.json`.
3. **Visualize:** System generates a Mermaid block diagram for the web interface.
4. **Draft:** `@dt_architect` creates the `.dts` file using the JSON map.
5. **Package:** `@snap_engineer` creates the Gadget Snap files.

## Metadata
- **Project Goal:** Automated Gadget Snap generation for custom boards.
- **Verified Bases:** core20, core22, core24.
- **Documentation Standard:** Linux Kernel Documentation (v5.15+).

## Directory Structure
- `/src`: Device Tree Sources (`.dts`)
- `/meta`: `gadget.yaml` and `snapcraft.yaml`
- `/web`: `index.html` and `visualizer.py`
