# Snap-Engineer Superpowers

## Gadget Snap Structure
- **Base Selection:** Verify architecture via `uname -m` or datasheet before choosing `core22` vs `core24`.
- **Interface Mapping:** Every hardware component found by @librarian must have a corresponding "slot" in `gadget.yaml`.

## Template Generation
Generate a `snapcraft.yaml` that includes:
1. `plugin: nil` for the gadget files.
2. `dump` plugin for the compiled `.dtb`.
3. Architecture-specific build-packages (e.g., `libc6-dev-arm64-cross`).
