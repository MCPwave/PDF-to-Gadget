# Web Visualization Skill

## Block Diagram Template
The agent should generate Mermaid code to be rendered in the browser.

### Example Generation:
```mermaid
graph TD
    subgraph SoC [System on Chip]
        CPU[ARM Cortex-A72]
        I2C1[I2C Bus 1]
        SPI0[SPI Bus 0]
        GPIO[GPIO Controller]
    end

    Sensor1[TMP102 Temp Sensor] --> I2C1
    Display[OLED Screen] --> SPI0
    LED[Status LED] --> GPIO
