# Agent Orchestration Logic

## Data Flow
- **Input:** PDF Datasheet (Text/OCR)
- **Middleware:** `hardware_map.json` (The shared state)
- **Output A:** `index.html` (Web Visualizer)
- **Output B:** `board.dts` (Device Tree)
- **Output C:** `gadget.snap` (Packaging)

## Validation Superpower
Before generating the Device Tree, the agent must run a **Pinmux Conflict Check**:
- If `Pin_X` is assigned to `UART_TX`, it cannot be assigned to `GPIO_OUT`.
- If a conflict is found, the agent must pause and ask: "Pin conflict detected on Pin X. Priority: UART or GPIO?"
