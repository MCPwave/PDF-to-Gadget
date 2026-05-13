# System Superpowers & Guardrails

- **Zero-Conflict Policy:** If two components are assigned to the same physical SoC pin, the process must halt and trigger a human-in-the-loop (HITL) resolution.
- **Architecture Locking:** The system must verify the CPU architecture (e.g., Cortex-A72 -> arm64) before selecting the Snap base (`core22`/`core24`).
- **Power Integrity:** Every Device Tree node for a peripheral MUST include a `vcc-supply` or `regulator` reference found in the datasheet.
- **Visual-First Reporting:** Every hardware change must trigger an update to the Mermaid.js block diagram for human verification.
