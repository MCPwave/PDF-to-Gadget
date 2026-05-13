# Engineering Skillset: Hardware-to-Snap

## 1. Hardware Analysis
- **Datasheet OCR & Parsing:** Extracting pinmux tables, I2C/SPI addresses, and voltage domains.
- **Pinmux Validation:** Logic checks to prevent GPIO/Bus pin assignment conflicts.

## 2. Linux Kernel & Device Tree
- **DTS/DTSI Authoring:** Writing Device Tree Sources following standard kernel bindings.
- **DTC (Device Tree Compiler):** Validating syntax and compiling `.dts` to `.dtb`.
- **Regulator Mapping:** Defining power-fixed and power-managed rails.

## 3. Ubuntu Core Packaging
- **Snapcraft CLI:** Creating `snapcraft.yaml` with appropriate plugins (kbuild, nil, dump).
- **Gadget Logic:** Structuring `gadget.yaml` for U-Boot or GRUB.
- **Interface Management:** Defining hardware "slots" to expose pins to application snaps.
