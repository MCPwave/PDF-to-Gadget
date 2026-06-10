"""
@kernel_scout — Upstream Linux Driver Scout
For each detected peripheral, finds the corresponding upstream Linux kernel driver.

Data sources (in order):
  1. Built-in knowledge base (fast, offline)
  2. GitHub API — torvalds/linux tree search (online, optional)

Driver status values:
  mainline   — merged in upstream Linux, just enable via Kconfig
  backport   — in a recent kernel; older kernels may need backport
  vendor     — exists only as out-of-tree/BSP driver from silicon vendor
  wip        — work-in-progress patch series on LKML
  unknown    — cannot determine; needs investigation
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# ── Built-in driver knowledge base ────────────────────────────────────────────
# Key: (soc_family_re, peripheral_type)  →  driver info
# soc_family_re is matched against hw_map["soc"] case-insensitively.
# Use "*" to match any SoC.

_DRIVER_DB: list[tuple[str, str, dict]] = [
    # ── I2C ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "i2c",  {"module": "i2c-bcm2835",   "since": "v3.18", "kconfig": "I2C_BCM2835",       "path": "drivers/i2c/busses/i2c-bcm2835.c",       "maintainer": "Stephen Warren <swarren@wwwdotorg.org>", "status": "mainline"}),
    ("RK3[0-9]",        "i2c",  {"module": "i2c-rk3x",      "since": "v3.18", "kconfig": "I2C_RK3X",           "path": "drivers/i2c/busses/i2c-rk3x.c",           "maintainer": "Douglas Anderson <dianders@chromium.org>", "status": "mainline"}),
    ("i\\.MX|IMX",      "i2c",  {"module": "i2c-imx",       "since": "v2.6.27","kconfig": "I2C_IMX",           "path": "drivers/i2c/busses/i2c-imx.c",            "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]|OMAP",    "i2c",  {"module": "i2c-omap",      "since": "v2.6.30","kconfig": "I2C_OMAP",          "path": "drivers/i2c/busses/i2c-omap.c",           "maintainer": "Wolfram Sang <wsa@kernel.org>",         "status": "mainline"}),
    ("MT[0-9]",         "i2c",  {"module": "i2c-mt65xx",    "since": "v4.6",  "kconfig": "I2C_MT65XX",         "path": "drivers/i2c/busses/i2c-mt65xx.c",         "maintainer": "Qii Wang <qii.wang@mediatek.com>",     "status": "mainline"}),
    ("Allwinner|[AH][0-9]","i2c",{"module": "i2c-mv64xxx",  "since": "v3.2",  "kconfig": "I2C_MV64XXX",        "path": "drivers/i2c/busses/i2c-mv64xxx.c",        "maintainer": "Gregory Clement <gregory.clement@bootlin.com>", "status": "mainline"}),
    ("STM32",           "i2c",  {"module": "i2c-stm32f7",   "since": "v4.11", "kconfig": "I2C_STM32F7",        "path": "drivers/i2c/busses/i2c-stm32f7.c",        "maintainer": "Pierre-Yves MORDRET <pierre-yves.mordret@foss.st.com>", "status": "mainline"}),
    ("*",               "i2c",  {"module": "i2c-designware", "since": "v2.6.34","kconfig": "I2C_DESIGNWARE_CORE","path": "drivers/i2c/busses/i2c-designware-core.c","maintainer": "Jarkko Nikula <jarkko.nikula@linux.intel.com>","status": "mainline"}),

    # ── SPI ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "spi",  {"module": "spi-bcm2835",   "since": "v3.10", "kconfig": "SPI_BCM2835",        "path": "drivers/spi/spi-bcm2835.c",               "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("RK3[0-9]",        "spi",  {"module": "spi-rockchip",  "since": "v4.0",  "kconfig": "SPI_ROCKCHIP",       "path": "drivers/spi/spi-rockchip.c",              "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("i\\.MX|IMX",      "spi",  {"module": "spi-imx",       "since": "v2.6.31","kconfig": "SPI_IMX",           "path": "drivers/spi/spi-imx.c",                   "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]|OMAP",    "spi",  {"module": "spi-omap2-mcspi","since": "v2.6.22","kconfig": "SPI_OMAP2_MCSPI",  "path": "drivers/spi/spi-omap2-mcspi.c",           "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("MT[0-9]",         "spi",  {"module": "spi-mt65xx",    "since": "v4.6",  "kconfig": "SPI_MT65XX",         "path": "drivers/spi/spi-mt65xx.c",                "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("STM32",           "spi",  {"module": "spi-stm32",     "since": "v4.11", "kconfig": "SPI_STM32",          "path": "drivers/spi/spi-stm32.c",                 "maintainer": "Alain Volmat <alain.volmat@foss.st.com>","status": "mainline"}),
    ("*",               "spi",  {"module": "spi-pl022",     "since": "v2.6.30","kconfig": "SPI_PL022",         "path": "drivers/spi/spi-pl022.c",                 "maintainer": "Linus Walleij <linus.walleij@linaro.org>","status": "mainline"}),

    # ── UART ────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "uart", {"module": "amba-pl011",    "since": "v2.6.15","kconfig": "SERIAL_AMBA_PL011",  "path": "drivers/tty/serial/amba-pl011.c",         "maintainer": "Russell King <linux@armlinux.org.uk>", "status": "mainline"}),
    ("BCM2711|BCM283",  "usart",{"module": "amba-pl011",    "since": "v2.6.15","kconfig": "SERIAL_AMBA_PL011",  "path": "drivers/tty/serial/amba-pl011.c",         "maintainer": "Russell King <linux@armlinux.org.uk>", "status": "mainline"}),
    ("RK3[0-9]",        "uart", {"module": "serial-8250-dw","since": "v3.0",  "kconfig": "SERIAL_8250_DW",     "path": "drivers/tty/serial/8250/8250_dw.c",       "maintainer": "Heikki Krogerus <heikki.krogerus@linux.intel.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "uart", {"module": "imx-serial",   "since": "v2.6.18","kconfig": "SERIAL_IMX",         "path": "drivers/tty/serial/imx.c",                "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]|OMAP",    "uart", {"module": "omap-serial",  "since": "v2.6.37","kconfig": "SERIAL_OMAP",        "path": "drivers/tty/serial/omap-serial.c",        "maintainer": "Sebastian Andrzej Siewior <bigeasy@linutronix.de>","status": "mainline"}),
    ("MT[0-9]",         "uart", {"module": "mtk-uart",     "since": "v4.6",  "kconfig": "SERIAL_8250_MT6577", "path": "drivers/tty/serial/8250/8250_mtk.c",      "maintainer": "Long Cheng <long.cheng@mediatek.com>", "status": "mainline"}),
    ("STM32",           "uart", {"module": "stm32-usart",  "since": "v4.6",  "kconfig": "SERIAL_STM32",       "path": "drivers/tty/serial/stm32-usart.c",        "maintainer": "Gerald Baeza <gerald.baeza@foss.st.com>","status": "mainline"}),
    ("*",               "uart", {"module": "amba-pl011",    "since": "v2.6.15","kconfig": "SERIAL_AMBA_PL011",  "path": "drivers/tty/serial/amba-pl011.c",         "maintainer": "Russell King <linux@armlinux.org.uk>", "status": "mainline"}),

    # ── GPIO ────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "gpio", {"module": "pinctrl-bcm2835","since": "v3.12","kconfig": "PINCTRL_BCM2835",    "path": "drivers/pinctrl/bcm/pinctrl-bcm2835.c",   "maintainer": "Florian Fainelli <florian.fainelli@broadcom.com>","status": "mainline"}),
    ("RK3[0-9]",        "gpio", {"module": "pinctrl-rockchip","since": "v3.10","kconfig": "PINCTRL_ROCKCHIP",  "path": "drivers/pinctrl/rockchip/pinctrl-rockchip.c","maintainer": "Heiko Stuebner <heiko@sntech.de>",    "status": "mainline"}),
    ("i\\.MX|IMX",      "gpio", {"module": "pinctrl-imx",  "since": "v3.0",  "kconfig": "PINCTRL_IMX",        "path": "drivers/pinctrl/freescale/pinctrl-imx.c", "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]|OMAP",    "gpio", {"module": "gpio-omap",    "since": "v2.6.37","kconfig": "GPIO_OMAP",         "path": "drivers/gpio/gpio-omap.c",                "maintainer": "Javier Martinez Canillas <javier@dowhile0.org>","status": "mainline"}),
    ("STM32",           "gpio", {"module": "pinctrl-stm32","since": "v4.1",  "kconfig": "PINCTRL_STM32",      "path": "drivers/pinctrl/stm32/pinctrl-stm32.c",   "maintainer": "Maxime Coquelin <mcoquelin.stm32@gmail.com>","status": "mainline"}),
    ("*",               "gpio", {"module": "gpio-pl061",   "since": "v2.6.28","kconfig": "GPIO_PL061",         "path": "drivers/gpio/gpio-pl061.c",               "maintainer": "Linus Walleij <linus.walleij@linaro.org>","status": "mainline"}),

    # ── USB ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "usb",  {"module": "xhci-pci / dwc2","since": "v4.15","kconfig": "USB_DWC2",           "path": "drivers/usb/dwc2/",                       "maintainer": "Minas Harutyunyan <hminas@synopsys.com>","status": "mainline"}),
    ("RK3[0-9]",        "usb",  {"module": "dwc3-of-simple","since": "v4.9",  "kconfig": "USB_DWC3",           "path": "drivers/usb/dwc3/",                       "maintainer": "Felipe Balbi <balbi@kernel.org>",      "status": "mainline"}),
    ("i\\.MX|IMX",      "usb",  {"module": "ci-hdrc-imx",  "since": "v3.5",  "kconfig": "USB_CHIPIDEA_IMX",   "path": "drivers/usb/chipidea/ci_hdrc_imx.c",      "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]",         "usb",  {"module": "musb-dsps",    "since": "v3.7",  "kconfig": "USB_MUSB_DSPS",      "path": "drivers/usb/musb/musb_dsps.c",            "maintainer": "Bin Liu <b-liu@ti.com>",               "status": "mainline"}),
    ("MT[0-9]",         "usb",  {"module": "xhci-mtk",    "since": "v4.7",  "kconfig": "USB_XHCI_MTK",       "path": "drivers/usb/host/xhci-mtk.c",             "maintainer": "Chunfeng Yun <chunfeng.yun@mediatek.com>","status": "mainline"}),
    ("*",               "usb",  {"module": "xhci-hcd",    "since": "v2.6.31","kconfig": "USB_XHCI_HCD",       "path": "drivers/usb/host/xhci.c",                 "maintainer": "Mathias Nyman <mathias.nyman@intel.com>","status": "mainline"}),

    # ── Ethernet ────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "ethernet",{"module": "bcmgenet",  "since": "v3.14", "kconfig": "BCMGENET",           "path": "drivers/net/ethernet/broadcom/genet/",    "maintainer": "Florian Fainelli <florian.fainelli@broadcom.com>","status": "mainline"}),
    ("RK3[0-9]",        "ethernet",{"module": "stmmac",   "since": "v3.10", "kconfig": "STMMAC_ETH",         "path": "drivers/net/ethernet/stmicro/stmmac/",    "maintainer": "Giuseppe Cavallaro <peppe.cavallaro@st.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "ethernet",{"module": "fec",      "since": "v2.6.27","kconfig": "FEC",                "path": "drivers/net/ethernet/freescale/fec_main.c","maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]",         "ethernet",{"module": "cpsw",     "since": "v3.2",  "kconfig": "TI_CPSW",            "path": "drivers/net/ethernet/ti/cpsw.c",          "maintainer": "Grygorii Strashko <grygorii.strashko@ti.com>","status": "mainline"}),
    ("MT[0-9]",         "ethernet",{"module": "mtk-eth-soc","since": "v4.6","kconfig": "NET_MEDIATEK_SOC",    "path": "drivers/net/ethernet/mediatek/",          "maintainer": "Felix Fietkau <nbd@nbd.name>",         "status": "mainline"}),
    ("STM32",           "ethernet",{"module": "stmmac",   "since": "v4.14", "kconfig": "STMMAC_ETH",         "path": "drivers/net/ethernet/stmicro/stmmac/",    "maintainer": "Giuseppe Cavallaro <peppe.cavallaro@st.com>","status": "mainline"}),
    ("*",               "ethernet",{"module": "stmmac",   "since": "v3.10", "kconfig": "STMMAC_ETH",         "path": "drivers/net/ethernet/stmicro/stmmac/",    "maintainer": "Giuseppe Cavallaro <peppe.cavallaro@st.com>","status": "mainline"}),

    # ── CAN ─────────────────────────────────────────────────────────────────
    ("i\\.MX|IMX",      "can",  {"module": "flexcan",     "since": "v2.6.38","kconfig": "CAN_FLEXCAN",         "path": "drivers/net/can/flexcan/flexcan-core.c",  "maintainer": "Marc Kleine-Budde <mkl@pengutronix.de>","status": "mainline"}),
    ("i\\.MX|IMX",      "can_fd",{"module": "flexcan",    "since": "v5.3",  "kconfig": "CAN_FLEXCAN",         "path": "drivers/net/can/flexcan/flexcan-core.c",  "maintainer": "Marc Kleine-Budde <mkl@pengutronix.de>","status": "mainline"}),
    ("AM[0-9]",         "can",  {"module": "c_can",       "since": "v3.2",  "kconfig": "CAN_C_CAN",           "path": "drivers/net/can/c_can/",                  "maintainer": "Pengutronix Kernel Team <kernel@pengutronix.de>","status": "mainline"}),
    ("RK3[0-9]",        "can",  {"module": "rockchip-canfd","since": "v5.14","kconfig": "CAN_ROCKCHIP_CANFD", "path": "drivers/net/can/rockchip/rockchip_canfd.c","maintainer": "Marc Kleine-Budde <mkl@pengutronix.de>","status": "mainline"}),
    ("*",               "can",  {"module": "mcp251xfd",   "since": "v5.6",  "kconfig": "CAN_MCP251XFD",       "path": "drivers/net/can/spi/mcp251xfd/",          "maintainer": "Marc Kleine-Budde <mkl@pengutronix.de>","status": "mainline"}),
    ("*",               "can_fd",{"module": "mcp251xfd",  "since": "v5.6",  "kconfig": "CAN_MCP251XFD",       "path": "drivers/net/can/spi/mcp251xfd/",          "maintainer": "Marc Kleine-Budde <mkl@pengutronix.de>","status": "mainline"}),

    # ── HDMI / Display ──────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "hdmi", {"module": "vc4",         "since": "v4.4",  "kconfig": "DRM_VC4",             "path": "drivers/gpu/drm/vc4/",                    "maintainer": "Maxime Ripard <mripard@kernel.org>",   "status": "mainline"}),
    ("RK3[0-9]",        "hdmi", {"module": "dw-hdmi-rockchip","since": "v4.4","kconfig": "DRM_ROCKCHIP",      "path": "drivers/gpu/drm/rockchip/",               "maintainer": "Sandy Huang <hjc@rock-chips.com>",     "status": "mainline"}),
    ("i\\.MX|IMX",      "hdmi", {"module": "imx-lcdif",  "since": "v5.13", "kconfig": "DRM_IMX_LCDIF",       "path": "drivers/gpu/drm/imx/lcdif/",              "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("Allwinner|[AH][0-9]","hdmi",{"module": "sun4i-drm","since": "v4.7",  "kconfig": "DRM_SUN4I",           "path": "drivers/gpu/drm/sun4i/",                  "maintainer": "Maxime Ripard <mripard@kernel.org>",   "status": "mainline"}),
    ("MT[0-9]",         "hdmi", {"module": "mediatek-drm","since": "v4.6",  "kconfig": "DRM_MEDIATEK",        "path": "drivers/gpu/drm/mediatek/",               "maintainer": "CK Hu <ck.hu@mediatek.com>",           "status": "mainline"}),
    ("*",               "hdmi", {"module": "dw-hdmi",    "since": "v3.19", "kconfig": "DRM_DW_HDMI",         "path": "drivers/gpu/drm/bridge/synopsys/dw-hdmi.c","maintainer": "Neil Armstrong <neil.armstrong@linaro.org>","status": "mainline"}),
    ("*",               "displayport",{"module": "dp-aux","since": "v4.0", "kconfig": "DRM_DP_AUX_CHARDEV",   "path": "drivers/gpu/drm/",                        "maintainer": "Dave Airlie <airlied@redhat.com>",     "status": "mainline"}),

    # ── MIPI DSI ────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "mipi_dsi",{"module": "vc4-dsi",  "since": "v4.9", "kconfig": "DRM_VC4",             "path": "drivers/gpu/drm/vc4/vc4_dsi.c",           "maintainer": "Maxime Ripard <mripard@kernel.org>",   "status": "mainline"}),
    ("RK3[0-9]",        "mipi_dsi",{"module": "rockchip-dsi","since": "v4.12","kconfig": "DRM_ROCKCHIP",     "path": "drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c","maintainer": "Sandy Huang <hjc@rock-chips.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "mipi_dsi",{"module": "nwl-dsi",  "since": "v5.5", "kconfig": "DRM_NWL_MIPI_DSI",   "path": "drivers/gpu/drm/bridge/nwl-dsi.c",        "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("*",               "mipi_dsi",{"module": "dw-mipi-dsi","since": "v4.9","kconfig": "DRM_DW_MIPI_DSI",    "path": "drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c","maintainer": "Philippe CORNU <philippe.cornu@foss.st.com>","status": "mainline"}),

    # ── MIPI CSI / Camera ───────────────────────────────────────────────────
    ("BCM2711|BCM283",  "mipi_csi",{"module": "bcm2835-unicam","since": "v5.7","kconfig": "VIDEO_BCM2835_UNICAM","path": "drivers/media/platform/bcm2835/","maintainer": "Dave Stevenson <dave.stevenson@raspberrypi.com>","status": "mainline"}),
    ("BCM2711|BCM283",  "camera",  {"module": "bcm2835-unicam","since": "v5.7","kconfig": "VIDEO_BCM2835_UNICAM","path": "drivers/media/platform/bcm2835/","maintainer": "Dave Stevenson <dave.stevenson@raspberrypi.com>","status": "mainline"}),
    ("RK3[0-9]",        "mipi_csi",{"module": "rkisp1",   "since": "v5.8",  "kconfig": "VIDEO_ROCKCHIP_ISP1", "path": "drivers/media/platform/rockchip/rkisp1/", "maintainer": "Helen Koike <helen.koike@collabora.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "mipi_csi",{"module": "imx8-isi", "since": "v5.17", "kconfig": "VIDEO_IMX8_ISI",      "path": "drivers/media/platform/nxp/imx8-isi/",   "maintainer": "Laurent Pinchart <laurent.pinchart@ideasonboard.com>","status": "mainline"}),
    # Intel IPU6 — out-of-tree, requires github.com/intel/ipu6-drivers
    ("Meteor|12th|13th",  "ipu6",     {"module": "intel-ipu6",   "since": "N/A",  "kconfig": "IPU6",                "path": "github.com/intel/ipu6-drivers",           "maintainer": "Intel (ipu6-drivers)",               "status": "vendor"}),
    ("Meteor|12th|13th",  "mipi_csi", {"module": "intel-ipu6",   "since": "N/A",  "kconfig": "IPU6",                "path": "github.com/intel/ipu6-drivers",           "maintainer": "Intel (ipu6-drivers)",               "status": "vendor"}),
    ("Meteor|12th|13th",  "camera",   {"module": "intel-ipu6",   "since": "N/A",  "kconfig": "IPU6",                "path": "github.com/intel/ipu6-drivers",           "maintainer": "Intel (ipu6-drivers)",               "status": "vendor"}),
    ("*",               "mipi_csi",{"module": "mipi-csi2","since": "v5.9",  "kconfig": "VIDEO_MIPI_CSI2",     "path": "drivers/media/",                          "maintainer": "Mauro Carvalho Chehab <mchehab@kernel.org>","status": "mainline"}),
    ("*",               "camera",  {"module": "mipi-csi2","since": "v5.9",  "kconfig": "VIDEO_MIPI_CSI2",     "path": "drivers/media/",                          "maintainer": "Mauro Carvalho Chehab <mchehab@kernel.org>","status": "mainline"}),

    # ── PCIe ────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "pcie", {"module": "pcie-brcmstb","since": "v5.4",  "kconfig": "PCIE_BRCMSTB",        "path": "drivers/pci/controller/pcie-brcmstb.c",   "maintainer": "Florian Fainelli <florian.fainelli@broadcom.com>","status": "mainline"}),
    ("RK3[0-9]",        "pcie", {"module": "pcie-rockchip-host","since": "v4.14","kconfig": "PCIE_ROCKCHIP_HOST","path": "drivers/pci/controller/pcie-rockchip-host.c","maintainer": "Shawn Lin <shawn.lin@rock-chips.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "pcie", {"module": "pci-imx6",   "since": "v3.5",  "kconfig": "PCI_IMX6",            "path": "drivers/pci/controller/dwc/pci-imx6.c",   "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]",         "pcie", {"module": "pci-j721e",  "since": "v5.6",  "kconfig": "PCI_J721E",           "path": "drivers/pci/controller/cadence/pci-j721e.c","maintainer": "Kishon Vijay Abraham I <kishon@ti.com>","status": "mainline"}),
    ("MT[0-9]",         "pcie", {"module": "pcie-mediatek-gen3","since": "v5.14","kconfig": "PCIE_MEDIATEK_GEN3","path": "drivers/pci/controller/pcie-mediatek-gen3.c","maintainer": "Jianjun Wang <jianjun.wang@mediatek.com>","status": "mainline"}),
    ("*",               "pcie", {"module": "pcie-dwc",   "since": "v4.1",  "kconfig": "PCIE_DW_PLAT_HOST",   "path": "drivers/pci/controller/dwc/",             "maintainer": "Jingoo Han <jingoohan1@gmail.com>",    "status": "mainline"}),

    # ── SATA ────────────────────────────────────────────────────────────────
    ("RK3[0-9]",        "sata", {"module": "ahci",        "since": "v5.6",  "kconfig": "SATA_AHCI",           "path": "drivers/ata/ahci.c",                      "maintainer": "Jens Axboe <axboe@kernel.dk>",         "status": "mainline"}),
    ("i\\.MX|IMX",      "sata", {"module": "ahci-imx",   "since": "v3.2",  "kconfig": "SATA_AHCI_IMX",       "path": "drivers/ata/ahci_imx.c",                  "maintainer": "Shawn Guo <shawnguo@kernel.org>",      "status": "mainline"}),
    ("AM[0-9]",         "sata", {"module": "ahci",        "since": "v4.1",  "kconfig": "SATA_AHCI_PLATFORM",  "path": "drivers/ata/libahci_platform.c",          "maintainer": "Jens Axboe <axboe@kernel.dk>",         "status": "mainline"}),
    ("*",               "sata", {"module": "ahci",        "since": "v2.6.19","kconfig": "SATA_AHCI",          "path": "drivers/ata/ahci.c",                      "maintainer": "Jens Axboe <axboe@kernel.dk>",         "status": "mainline"}),

    # ── eMMC / SD ───────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "emmc", {"module": "sdhci-bcm2835","since": "v3.12","kconfig": "MMC_SDHCI_BCM2835",   "path": "drivers/mmc/host/sdhci-bcm2835.c",        "maintainer": "Stefan Wahren <stefan.wahren@i2se.com>","status": "mainline"}),
    ("RK3[0-9]",        "emmc", {"module": "sdhci-of-arasan","since": "v4.0","kconfig": "MMC_SDHCI_OF_ARASAN","path": "drivers/mmc/host/sdhci-of-arasan.c",      "maintainer": "Adrian Hunter <adrian.hunter@intel.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "emmc", {"module": "sdhci-esdhc-imx","since": "v2.6.36","kconfig": "MMC_SDHCI_ESDHC_IMX","path": "drivers/mmc/host/sdhci-esdhc-imx.c","maintainer": "NXP Linux Team <linux-imx@nxp.com>","status": "mainline"}),
    ("AM[0-9]",         "emmc", {"module": "sdhci-omap",  "since": "v4.18", "kconfig": "MMC_SDHCI_OMAP",      "path": "drivers/mmc/host/sdhci-omap.c",           "maintainer": "Kishon Vijay Abraham I <kishon@ti.com>","status": "mainline"}),
    ("MT[0-9]",         "emmc", {"module": "mtk-mmc",    "since": "v4.6",  "kconfig": "MMC_MTK",             "path": "drivers/mmc/host/mtk-mmc.c",              "maintainer": "Chaotian Jing <chaotian.jing@mediatek.com>","status": "mainline"}),
    ("STM32",           "emmc", {"module": "mmci",        "since": "v2.6.28","kconfig": "MMC_ARMMMCI",        "path": "drivers/mmc/host/mmci.c",                 "maintainer": "Linus Walleij <linus.walleij@linaro.org>","status": "mainline"}),
    ("*",               "emmc", {"module": "sdhci",       "since": "v2.6.17","kconfig": "MMC_SDHCI",          "path": "drivers/mmc/host/sdhci.c",                "maintainer": "Adrian Hunter <adrian.hunter@intel.com>","status": "mainline"}),
    ("*",               "sd",   {"module": "sdhci",       "since": "v2.6.17","kconfig": "MMC_SDHCI",          "path": "drivers/mmc/host/sdhci.c",                "maintainer": "Adrian Hunter <adrian.hunter@intel.com>","status": "mainline"}),
    ("*",               "sdio", {"module": "sdhci",       "since": "v2.6.17","kconfig": "MMC_SDHCI",          "path": "drivers/mmc/host/sdhci.c",                "maintainer": "Adrian Hunter <adrian.hunter@intel.com>","status": "mainline"}),

    # ── I2S / Audio ─────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "i2s",  {"module": "bcm2835-i2s", "since": "v3.12", "kconfig": "SND_BCM2835_SOC_I2S", "path": "sound/soc/bcm/bcm2835-i2s.c",             "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("RK3[0-9]",        "i2s",  {"module": "rockchip-i2s","since": "v4.1",  "kconfig": "SND_SOC_ROCKCHIP_I2S","path": "sound/soc/rockchip/rockchip_i2s.c",       "maintainer": "Sugar Zhang <sugar.zhang@rock-chips.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "i2s",  {"module": "fsl-sai",    "since": "v3.15", "kconfig": "SND_SOC_FSL_SAI",     "path": "sound/soc/fsl/fsl_sai.c",                 "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("AM[0-9]",         "i2s",  {"module": "mcasp",      "since": "v3.2",  "kconfig": "SND_SOC_DAVINCI_MCASP","path": "sound/soc/ti/davinci-mcasp.c",            "maintainer": "Misael Lopez Cruz <misael.lopez@ti.com>","status": "mainline"}),
    ("STM32",           "i2s",  {"module": "stm32-i2s",  "since": "v4.15", "kconfig": "SND_SOC_STM32_I2S",   "path": "sound/soc/stm/stm32_i2s.c",               "maintainer": "Olivier Moysan <olivier.moysan@foss.st.com>","status": "mainline"}),
    ("*",               "i2s",  {"module": "snd-soc-i2s","since": "v2.6.29","kconfig": "SND_SOC",             "path": "sound/soc/",                              "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("*",               "sai",  {"module": "snd-soc-fsl-sai","since": "v3.15","kconfig": "SND_SOC_FSL_SAI",  "path": "sound/soc/fsl/fsl_sai.c",                 "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),
    ("*",               "audio",{"module": "snd-soc",    "since": "v2.6.26","kconfig": "SND_SOC",             "path": "sound/soc/",                              "maintainer": "Mark Brown <broonie@kernel.org>",      "status": "mainline"}),

    # ── ADC ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "adc",  {"module": "mcp320x",    "since": "v3.10", "kconfig": "MCP320X",             "path": "drivers/iio/adc/mcp320x.c",               "maintainer": "Oskar Andero <oskar.andero@gmail.com>","status": "mainline"}),
    ("STM32",           "adc",  {"module": "stm32-adc",  "since": "v4.12", "kconfig": "STM32_ADC",           "path": "drivers/iio/adc/stm32-adc.c",             "maintainer": "Olivier Moysan <olivier.moysan@foss.st.com>","status": "mainline"}),
    ("AM[0-9]",         "adc",  {"module": "ti-ads7950", "since": "v4.3",  "kconfig": "TI_ADS7950",          "path": "drivers/iio/adc/ti-ads7950.c",            "maintainer": "David Lechner <david@lechnology.com>", "status": "mainline"}),
    ("*",               "adc",  {"module": "iio-adc",    "since": "v3.0",  "kconfig": "IIO",                 "path": "drivers/iio/adc/",                        "maintainer": "Jonathan Cameron <jic23@kernel.org>",  "status": "mainline"}),

    # ── PWM ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "pwm",  {"module": "pwm-bcm2835","since": "v3.13", "kconfig": "PWM_BCM2835",         "path": "drivers/pwm/pwm-bcm2835.c",               "maintainer": "Thierry Reding <thierry.reding@gmail.com>","status": "mainline"}),
    ("RK3[0-9]",        "pwm",  {"module": "pwm-rockchip","since": "v3.13","kconfig": "PWM_ROCKCHIP",        "path": "drivers/pwm/pwm-rockchip.c",              "maintainer": "Beniamino Galvani <b.galvani@gmail.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "pwm",  {"module": "pwm-imx27",  "since": "v3.0",  "kconfig": "PWM_IMX27",           "path": "drivers/pwm/pwm-imx27.c",                 "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("STM32",           "pwm",  {"module": "pwm-stm32",  "since": "v4.9",  "kconfig": "PWM_STM32",           "path": "drivers/pwm/pwm-stm32.c",                 "maintainer": "Lee Jones <lee@kernel.org>",           "status": "mainline"}),
    ("*",               "pwm",  {"module": "pwm-pl022",  "since": "v3.6",  "kconfig": "PWM",                 "path": "drivers/pwm/",                            "maintainer": "Thierry Reding <thierry.reding@gmail.com>","status": "mainline"}),

    # ── QSPI / NOR Flash ────────────────────────────────────────────────────
    ("*",               "qspi", {"module": "spi-nor",    "since": "v4.0",  "kconfig": "MTD_SPI_NOR",         "path": "drivers/mtd/spi-nor/",                    "maintainer": "Tudor Ambarus <tudor.ambarus@microchip.com>","status": "mainline"}),
    ("*",               "nor_flash",{"module": "spi-nor","since": "v4.0",  "kconfig": "MTD_SPI_NOR",         "path": "drivers/mtd/spi-nor/",                    "maintainer": "Tudor Ambarus <tudor.ambarus@microchip.com>","status": "mainline"}),
    ("*",               "nand", {"module": "nand-base",  "since": "v2.6.0","kconfig": "MTD_NAND",            "path": "drivers/mtd/nand/",                       "maintainer": "Miquel Raynal <miquel.raynal@bootlin.com>","status": "mainline"}),

    # ── JTAG / Debug ────────────────────────────────────────────────────────
    ("*",               "jtag", {"module": "aspeed-jtag","since": "v5.4",  "kconfig": "JTAG_ASPEED",         "path": "drivers/jtag/jtag-aspeed.c",              "maintainer": "Oleksandr Shamray <oleksandrs@mellanox.com>","status": "mainline"}),
    ("*",               "swd",  {"module": "N/A (user-space via SWD)","since": "N/A","kconfig": "N/A",       "path": "N/A",                                     "maintainer": "N/A",                                  "status": "vendor"}),

    # ── RTC ─────────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "rtc",  {"module": "rtc-pcf85363","since": "v4.6", "kconfig": "RTC_DRV_PCF85363",    "path": "drivers/rtc/rtc-pcf85363.c",              "maintainer": "Alexandre Belloni <alexandre.belloni@bootlin.com>","status": "mainline"}),
    ("STM32",           "rtc",  {"module": "rtc-stm32",  "since": "v4.4",  "kconfig": "RTC_DRV_STM32",       "path": "drivers/rtc/rtc-stm32.c",                 "maintainer": "Alexandre Belloni <alexandre.belloni@bootlin.com>","status": "mainline"}),
    ("i\\.MX|IMX",      "rtc",  {"module": "rtc-snvs",   "since": "v3.7",  "kconfig": "RTC_DRV_SNVS",        "path": "drivers/rtc/rtc-snvs.c",                  "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("*",               "rtc",  {"module": "rtc-ds1307",  "since": "v2.6.22","kconfig": "RTC_DRV_DS1307",    "path": "drivers/rtc/rtc-ds1307.c",                "maintainer": "Alexandre Belloni <alexandre.belloni@bootlin.com>","status": "mainline"}),

    # ── Watchdog ────────────────────────────────────────────────────────────
    ("BCM2711|BCM283",  "watchdog",{"module": "bcm2835-wdt","since": "v3.12","kconfig": "BCM2835_WDT",       "path": "drivers/watchdog/bcm2835_wdt.c",          "maintainer": "Florian Fainelli <florian.fainelli@broadcom.com>","status": "mainline"}),
    ("RK3[0-9]",        "watchdog",{"module": "dw-wdt",   "since": "v3.4",  "kconfig": "DW_WATCHDOG",        "path": "drivers/watchdog/dw_wdt.c",               "maintainer": "Jamie Iles <jamie@jamieiles.com>",     "status": "mainline"}),
    ("i\\.MX|IMX",      "watchdog",{"module": "imx2-wdt", "since": "v2.6.27","kconfig": "IMX2_WDT",         "path": "drivers/watchdog/imx2_wdt.c",             "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("STM32",           "watchdog",{"module": "stm32-iwdg","since": "v4.7", "kconfig": "STMP3XXX_RTC_WATCHDOG","path": "drivers/watchdog/stm32_iwdg.c",        "maintainer": "Guenter Roeck <linux@roeck-us.net>",   "status": "mainline"}),
    ("*",               "watchdog",{"module": "sp805-wdt", "since": "v2.6.37","kconfig": "SP805_WATCHDOG",   "path": "drivers/watchdog/sp805_wdt.c",            "maintainer": "Viresh Kumar <vireshk@kernel.org>",    "status": "mainline"}),

    # ── LVDS ────────────────────────────────────────────────────────────────
    ("i\\.MX|IMX",      "lvds", {"module": "ldb",         "since": "v3.11", "kconfig": "DRM_IMX_LDB",        "path": "drivers/gpu/drm/imx/imx-ldb.c",           "maintainer": "NXP Linux Team <linux-imx@nxp.com>",   "status": "mainline"}),
    ("*",               "lvds", {"module": "lvds-codec",  "since": "v5.0",  "kconfig": "DRM_LVDS_CODEC",     "path": "drivers/gpu/drm/bridge/lvds-codec.c",     "maintainer": "Laurent Pinchart <laurent.pinchart@ideasonboard.com>","status": "mainline"}),
]

# ── Component IC Driver Database ─────────────────────────────────────────────────
# Key: (component_type, ic_name, connection_type)  →  driver info
# component_type: "camera_sensor", "display", "sensor_temperature", etc.
# ic_name: exact IC model (e.g., "ov5647", "ili9341", "mpu6050")
# connection_type: "mipi_csi", "spi", "i2c", "usb", "lvds", etc.

_COMPONENT_DRIVER_DB: list[tuple[str, str, str, dict]] = [
    # ── Camera Sensors ──────────────────────────────────────────────────────
    ("camera_sensor", "ov5647", "mipi_csi", {
        "module": "ov5647",
        "since": "v4.5",
        "kconfig": "CONFIG_VIDEO_OV5647",
        "path": "drivers/media/i2c/ov5647.c",
        "maintainer": "Dave Stevenson <dave.stevenson@raspberrypi.org>",
        "status": "mainline",
    }),
    ("camera_sensor", "ov5647", "usb", {
        "module": "uvcvideo",
        "since": "v2.6.26",
        "kconfig": "CONFIG_MEDIA_USB_SUPPORT",
        "path": "drivers/media/usb/uvc/",
        "maintainer": "Laurent Pinchart <laurent.pinchart@ideasonboard.com>",
        "status": "mainline",
    }),
    ("camera_sensor", "imx219", "mipi_csi", {
        "module": "imx219",
        "since": "v5.3",
        "kconfig": "CONFIG_VIDEO_IMX219",
        "path": "drivers/media/i2c/imx219.c",
        "maintainer": "Dave Stevenson <dave.stevenson@raspberrypi.org>",
        "status": "mainline",
    }),
    ("camera_sensor", "imx477", "mipi_csi", {
        "module": "imx477",
        "since": "v5.7",
        "kconfig": "CONFIG_VIDEO_IMX477",
        "path": "drivers/media/i2c/imx477.c",
        "maintainer": "Dave Stevenson <dave.stevenson@raspberrypi.org>",
        "status": "mainline",
    }),
    ("camera_sensor", "ar0521", "mipi_csi", {
        "module": "ar0521",
        "since": "v5.10",
        "kconfig": "CONFIG_VIDEO_AR0521",
        "path": "drivers/media/i2c/ar0521.c",
        "maintainer": "Jacopo Mondi <jacopo@jmondi.org>",
        "status": "mainline",
    }),
    ("camera_sensor", "ar2020", "mipi_csi", {
        "module": "ar2020",
        "since": "v5.15",
        "kconfig": "CONFIG_VIDEO_AR2020",
        "path": "drivers/media/i2c/ar2020.c",
        "maintainer": "onsemi",
        "status": "vendor",
    }),
    ("camera_sensor", "ov8856", "mipi_csi", {
        "module": "ov8856",
        "since": "v5.6",
        "kconfig": "CONFIG_VIDEO_OV8856",
        "path": "drivers/media/i2c/ov8856.c",
        "maintainer": "Antti Laakso <antti.laakso@linux.intel.com>",
        "status": "mainline",
    }),
    ("camera_sensor", "ov7251", "mipi_csi", {
        "module": "ov7251",
        "since": "v4.5",
        "kconfig": "CONFIG_VIDEO_OV7251",
        "path": "drivers/media/i2c/ov7251.c",
        "maintainer": "Maxime Ripard <mripard@kernel.org>",
        "status": "mainline",
    }),
    ("camera_sensor", "ov2680", "mipi_csi", {
        "module": "ov2680",
        "since": "v4.4",
        "kconfig": "CONFIG_VIDEO_OV2680",
        "path": "drivers/media/i2c/ov2680.c",
        "maintainer": "Rui Miguel Silva <rmfrfs@gmail.com>",
        "status": "mainline",
    }),
    # ── Display Controllers ──────────────────────────────────────────────────
    ("display", "ili9341", "spi", {
        "module": "ili9341",
        "since": "v5.8",
        "kconfig": "CONFIG_DRM_PANEL_SIMPLE",
        "path": "drivers/gpu/drm/panel/panel-simple.c",
        "maintainer": "Linus Walleij <linus.walleij@linaro.org>",
        "status": "mainline",
    }),
    ("display", "st7789", "spi", {
        "module": "st7789",
        "since": "v5.11",
        "kconfig": "CONFIG_DRM_ST7789V",
        "path": "drivers/gpu/drm/tiny/st7789v.c",
        "maintainer": "David Lechner <david@lechnology.com>",
        "status": "mainline",
    }),
    ("display", "st7735", "spi", {
        "module": "st7735",
        "since": "v5.11",
        "kconfig": "CONFIG_DRM_ST7735R",
        "path": "drivers/gpu/drm/tiny/st7735r.c",
        "maintainer": "David Lechner <david@lechnology.com>",
        "status": "mainline",
    }),
    ("display", "uc8159", "spi", {
        "module": "uc8159",
        "since": "v5.10",
        "kconfig": "CONFIG_DRM_ULTRACHIP_UC8159",
        "path": "drivers/gpu/drm/tiny/uc8159.c",
        "maintainer": "David Lechner <david@lechnology.com>",
        "status": "mainline",
    }),

    # ── Touchscreen Controllers ──────────────────────────────────────────────
    ("touchscreen", "ft5406", "i2c", {
        "module": "ft5406",
        "since": "v4.14",
        "kconfig": "CONFIG_TOUCHSCREEN_FT5406",
        "path": "drivers/input/touchscreen/ft5406.c",
        "maintainer": "Dave Martin <dave.martin@linaro.org>",
        "status": "mainline",
    }),
    ("touchscreen", "edt-ft5x06", "i2c", {
        "module": "edt-ft5x06",
        "since": "v3.0",
        "kconfig": "CONFIG_TOUCHSCREEN_EDT_FT5X06",
        "path": "drivers/input/touchscreen/edt-ft5x06.c",
        "maintainer": "Simon Budig <simon.budig@kernelconcepts.de>",
        "status": "mainline",
    }),
    ("touchscreen", "goodix", "i2c", {
        "module": "goodix",
        "since": "v4.0",
        "kconfig": "CONFIG_TOUCHSCREEN_GOODIX",
        "path": "drivers/input/touchscreen/goodix.c",
        "maintainer": "Bastien Nocera <hadess@hadess.net>",
        "status": "mainline",
    }),

    # ── Temperature Sensors ──────────────────────────────────────────────────
    ("sensor_temperature", "tmp36", "i2c", {
        "module": "lm75",
        "since": "v2.6.16",
        "kconfig": "CONFIG_SENSORS_LM75",
        "path": "drivers/hwmon/lm75.c",
        "maintainer": "Jean Delvare <jdelvare@suse.de>",
        "status": "mainline",
    }),
    ("sensor_temperature", "bmp280", "i2c", {
        "module": "bmp280",
        "since": "v4.2",
        "kconfig": "CONFIG_BMP280",
        "path": "drivers/iio/pressure/bmp280-core.c",
        "maintainer": "Jonathan Cameron <jic23@kernel.org>",
        "status": "mainline",
    }),
    ("sensor_temperature", "bmp280", "spi", {
        "module": "bmp280",
        "since": "v4.2",
        "kconfig": "CONFIG_BMP280",
        "path": "drivers/iio/pressure/bmp280-spi.c",
        "maintainer": "Jonathan Cameron <jic23@kernel.org>",
        "status": "mainline",
    }),

    # ── Accelerometers / IMUs ───────────────────────────────────────────────
    ("sensor_accelerometer", "mpu6050", "i2c", {
        "module": "mpu6050",
        "since": "v3.9",
        "kconfig": "CONFIG_INV_MPU6050_I2C",
        "path": "drivers/iio/imu/inv_mpu6050/",
        "maintainer": "Jean-Baptiste Maneyrol <jmaneyrol@invensense.com>",
        "status": "mainline",
    }),
    ("sensor_accelerometer", "mpu6050", "spi", {
        "module": "mpu6050",
        "since": "v3.9",
        "kconfig": "CONFIG_INV_MPU6050_SPI",
        "path": "drivers/iio/imu/inv_mpu6050/",
        "maintainer": "Jean-Baptiste Maneyrol <jmaneyrol@invensense.com>",
        "status": "mainline",
    }),
    ("sensor_accelerometer", "lsm6dsm", "i2c", {
        "module": "st_lsm6dsx",
        "since": "v4.15",
        "kconfig": "CONFIG_ST_LSM6DSX",
        "path": "drivers/iio/imu/st_lsm6dsx/",
        "maintainer": "Lorenzo Bianconi <lorenzo@kernel.org>",
        "status": "mainline",
    }),
    ("sensor_accelerometer", "lsm6dsm", "spi", {
        "module": "st_lsm6dsx",
        "since": "v4.15",
        "kconfig": "CONFIG_ST_LSM6DSX",
        "path": "drivers/iio/imu/st_lsm6dsx/",
        "maintainer": "Lorenzo Bianconi <lorenzo@kernel.org>",
        "status": "mainline",
    }),

    # ── Proximity / Ambient Light Sensors ────────────────────────────────────
    ("sensor_proximity", "apds9960", "i2c", {
        "module": "apds9960",
        "since": "v5.14",
        "kconfig": "CONFIG_APDS9960",
        "path": "drivers/iio/light/apds9960.c",
        "maintainer": "Matteo Martelli <matmartelli@gmail.com>",
        "status": "mainline",
    }),
    ("sensor_light", "bh1750", "i2c", {
        "module": "bh1750",
        "since": "v3.9",
        "kconfig": "CONFIG_BH1750",
        "path": "drivers/iio/light/bh1750.c",
        "maintainer": "Tomasz Duszynski <tduszyns@gmail.com>",
        "status": "mainline",
    }),

    # ── Power Management ICs ─────────────────────────────────────────────────
    ("pmic", "axp209", "i2c", {
        "module": "axp20x",
        "since": "v3.13",
        "kconfig": "CONFIG_AXP20X_I2C",
        "path": "drivers/mfd/axp20x.c",
        "maintainer": "Chen-Yu Tsai <wens@csie.org>",
        "status": "mainline",
    }),
    ("pmic", "tps65217", "i2c", {
        "module": "tps65217",
        "since": "v3.2",
        "kconfig": "CONFIG_MFD_TPS65217",
        "path": "drivers/mfd/tps65217.c",
        "maintainer": "AnilKumar Ch <anilkumar@ti.com>",
        "status": "mainline",
    }),

    # ── ADCs (Analog-to-Digital Converters) ──────────────────────────────────
    ("adc", "ads1015", "i2c", {
        "module": "ads1015",
        "since": "v3.9",
        "kconfig": "CONFIG_ADS1015",
        "path": "drivers/iio/adc/ads1015.c",
        "maintainer": "Daniel Baluta <daniel.baluta@intel.com>",
        "status": "mainline",
    }),
    ("adc", "ads1115", "i2c", {
        "module": "ads1015",
        "since": "v3.9",
        "kconfig": "CONFIG_ADS1015",
        "path": "drivers/iio/adc/ads1015.c",
        "maintainer": "Daniel Baluta <daniel.baluta@intel.com>",
        "status": "mainline",
    }),
    ("adc", "mcp3008", "spi", {
        "module": "mcp320x",
        "since": "v3.10",
        "kconfig": "CONFIG_MCP320X",
        "path": "drivers/iio/adc/mcp320x.c",
        "maintainer": "Oskar Andero <oskar.andero@gmail.com>",
        "status": "mainline",
    }),
    ("adc", "mcp3208", "spi", {
        "module": "mcp320x",
        "since": "v3.10",
        "kconfig": "CONFIG_MCP320X",
        "path": "drivers/iio/adc/mcp320x.c",
        "maintainer": "Oskar Andero <oskar.andero@gmail.com>",
        "status": "mainline",
    }),

    # ── GPIO Expanders ──────────────────────────────────────────────────────
    ("gpio_expander", "pcf8574", "i2c", {
        "module": "gpio-pcf857x",
        "since": "v2.6.34",
        "kconfig": "CONFIG_GPIO_PCF857X",
        "path": "drivers/gpio/gpio-pcf857x.c",
        "maintainer": "David Brownell <dbrownell@users.sourceforge.net>",
        "status": "mainline",
    }),
    ("gpio_expander", "mcp23017", "i2c", {
        "module": "gpio-mcp23s08",
        "since": "v2.6.34",
        "kconfig": "CONFIG_GPIO_MCP23S08",
        "path": "drivers/gpio/gpio-mcp23s08.c",
        "maintainer": "Peter Korsgaard <peter@korsgaard.com>",
        "status": "mainline",
    }),
    ("gpio_expander", "mcp23008", "i2c", {
        "module": "gpio-mcp23s08",
        "since": "v2.6.34",
        "kconfig": "CONFIG_GPIO_MCP23S08",
        "path": "drivers/gpio/gpio-mcp23s08.c",
        "maintainer": "Peter Korsgaard <peter@korsgaard.com>",
        "status": "mainline",
    }),

    # ── Real-Time Clocks ────────────────────────────────────────────────────
    ("rtc", "ds1307", "i2c", {
        "module": "rtc-ds1307",
        "since": "v2.6.22",
        "kconfig": "CONFIG_RTC_DRV_DS1307",
        "path": "drivers/rtc/rtc-ds1307.c",
        "maintainer": "Alexandre Belloni <alexandre.belloni@bootlin.com>",
        "status": "mainline",
    }),
    ("rtc", "pcf8563", "i2c", {
        "module": "rtc-pcf8563",
        "since": "v2.6.29",
        "kconfig": "CONFIG_RTC_DRV_PCF8563",
        "path": "drivers/rtc/rtc-pcf8563.c",
        "maintainer": "Jingoo Han <jingoohan1@gmail.com>",
        "status": "mainline",
    }),

    # ── LEDs / Lighting ──────────────────────────────────────────────────────
    ("led", "apa102", "spi", {
        "module": "led-apa102",
        "since": "v4.19",
        "kconfig": "CONFIG_LEDS_APA102",
        "path": "drivers/leds/led-apa102.c",
        "maintainer": "Heiner Kallweit <hkallweit1@gmail.com>",
        "status": "mainline",
    }),
    ("led", "ws2812", "spi", {
        "module": "led-pwm",
        "since": "v3.1",
        "kconfig": "CONFIG_LEDS_PWM",
        "path": "drivers/leds/leds-pwm.c",
        "maintainer": "Luotao Fu <l.fu@pengutronix.de>",
        "status": "mainline",
    }),
]

# ── SoC family resolver ────────────────────────────────────────────────────────

def _soc_family(soc: str) -> str:
    """Return the SoC string to match against DB keys."""
    return soc or ""


def _lookup_db(soc: str, ptype: str) -> Optional[dict]:
    """Search built-in DB for best matching driver. SoC-specific match wins over wildcard."""
    soc_norm = _soc_family(soc)
    best_specific: Optional[dict] = None
    best_wildcard: Optional[dict] = None

    for soc_re, periph_type, info in _DRIVER_DB:
        if periph_type != ptype:
            continue
        if soc_re == "*":
            if best_wildcard is None:
                best_wildcard = dict(info)
        elif re.search(soc_re, soc_norm, re.I):
            best_specific = dict(info)
            break  # first SoC-specific match wins

    return best_specific or best_wildcard


def lookup_component_driver(
    component_type: str,
    ic_name: str,
    connection_type: str,
    soc: Optional[str] = None,
) -> dict:
    """
    Lookup component IC driver in the component driver database.

    Args:
        component_type: e.g., "camera_sensor", "display", "sensor_temperature"
        ic_name: IC model name (e.g., "ov5647", "ili9341", "mpu6050")
        connection_type: e.g., "mipi_csi", "spi", "i2c", "usb"
        soc: Optional SoC name (for future multi-SoC component support)

    Returns:
        dict with keys: {status, module, since, kconfig, path, maintainer}
        On failure: {status: "unknown", message: "..."}
    """
    comp_type_lower = component_type.lower()
    ic_lower = ic_name.lower()
    conn_lower = connection_type.lower()

    for comp_type, ic, conn, info in _COMPONENT_DRIVER_DB:
        if (comp_type.lower() == comp_type_lower and
            ic.lower() == ic_lower and
            conn.lower() == conn_lower):
            return dict(info)

    return {
        "status": "unknown",
        "message": f"No driver info for {ic_name} on {connection_type} ({component_type})",
    }


# ── GitHub API lookup (online enrichment) ─────────────────────────────────────

_GH_TIMEOUT = 5
_GH_HEADERS = {
    "User-Agent": "pdf-to-gadget/1.0",
    "Accept": "application/vnd.github.v3+json",
}


def _github_headers() -> dict:
    headers = dict(_GH_HEADERS)
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_search_repositories(query: str, limit: int = 3) -> list[dict]:
    """Search GitHub repositories by query; return empty list on any error."""
    if not query:
        return []
    q = urllib.parse.urlencode({
        "q": f'{query} in:name,description,readme fork:false',
        "per_page": str(limit),
        "sort": "stars",
    })
    url = f"https://api.github.com/search/repositories?{q}"
    try:
        req = urllib.request.Request(url, headers=_github_headers())
        with urllib.request.urlopen(req, timeout=_GH_TIMEOUT) as r:
            data = json.loads(r.read())
        return data.get("items", [])[:limit]
    except Exception:
        return []


def _github_search_code_in_repo(query: str, repo_full_name: str) -> Optional[dict]:
    """Search GitHub code within one repo; return first hit or None."""
    if not query or not repo_full_name:
        return None
    q = urllib.parse.urlencode({
        "q": f'"{query}" repo:{repo_full_name}',
        "per_page": "1",
    })
    url = f"https://api.github.com/search/code?{q}"
    try:
        req = urllib.request.Request(url, headers=_github_headers())
        with urllib.request.urlopen(req, timeout=_GH_TIMEOUT) as r:
            data = json.loads(r.read())
        items = data.get("items", [])
        if items:
            return {
                "github_path": items[0].get("path", ""),
                "github_url": items[0].get("html_url", ""),
            }
    except Exception:
        pass
    return None


def _github_search_driver(module_name: str) -> Optional[dict]:
    """
    Try to find driver in torvalds/linux via GitHub search API.
    Returns basic info dict or None on failure/rate-limit.
    """
    if not module_name or module_name in ("N/A", "iio-adc", "snd-soc"):
        return None
    query = urllib.parse.urlencode({
        "q": f"{module_name} repo:torvalds/linux language:C",
        "per_page": "1",
    })
    url = f"https://api.github.com/search/code?{query}"
    try:
        req = urllib.request.Request(url, headers=_github_headers())
        with urllib.request.urlopen(req, timeout=_GH_TIMEOUT) as r:
            data = json.loads(r.read())
        items = data.get("items", [])
        if items:
            return {
                "github_path": items[0].get("path", ""),
                "github_url":  items[0].get("html_url", ""),
            }
    except Exception:
        pass
    return None


def _repo_candidates(peripheral: dict, driver_info: dict) -> list[str]:
    """Build manufacturer-repo search terms from peripheral metadata."""
    candidates = []
    component_ic = peripheral.get("component_ic") if isinstance(peripheral.get("component_ic"), dict) else {}
    for raw in (
        peripheral.get("manufacturer"),
        component_ic.get("vendor"),
        component_ic.get("name"),
        peripheral.get("name"),
        driver_info.get("maintainer"),
    ):
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"<.*?>", "", cleaned).strip()
        cleaned = cleaned.split("@")[0].strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


def _search_vendor_public_repos(
    peripheral_name: str, 
    driver_module: str, 
    driver_status: str,
    soc: str,
) -> Optional[dict]:
    """
    Search vendor public repositories for drivers not found in Linux kernel.
    This is a targeted search across known vendor repos and generic driver searches.
    
    Returns dict with driver source info:
      {
        "found": bool,
        "github_repo_name": str,
        "github_repo_url": str,
        "github_url": str,        # Direct link to driver file
        "github_path": str,
        "driver_source": str,     # "kernel" | "vendor_public" | "vendor_bsp"
      }
    """
    # Only search vendor repos if driver not found in kernel
    if driver_status and driver_status in ("mainline", "backport"):
        return None
    
    if not peripheral_name and not driver_module:
        return None
    
    # Build search terms
    search_terms = []
    if driver_module and driver_module not in ("unknown", "N/A"):
        search_terms.append(driver_module)
    if peripheral_name and peripheral_name not in ("unknown", "N/A"):
        # Add full name and component model number
        search_terms.append(peripheral_name)
        # Extract IC/chip model (e.g., "ov5640" from "OV5640 Camera Sensor")
        match = re.search(r'([A-Za-z0-9]{4,})', peripheral_name)
        if match:
            search_terms.append(match.group(1))
    
    # Add SoC-specific repos (e.g., Raspberry Pi, Rockchip, NXP, etc.)
    soc_lower = (soc or "").lower()
    vendor_orgs = []
    if "bcm" in soc_lower or "raspberry" in soc_lower:
        vendor_orgs.extend(["raspberrypi", "broadcom"])
    if "rk3" in soc_lower or "rockchip" in soc_lower:
        vendor_orgs.extend(["rockchip"])
    if "imx" in soc_lower or "nxp" in soc_lower:
        vendor_orgs.extend(["nxp-imx"])
    if "mediatek" in soc_lower or "mt" in soc_lower:
        vendor_orgs.extend(["MediaTek"])
    if "stm32" in soc_lower or "st" in soc_lower:
        vendor_orgs.extend(["STMicroelectronics"])
    if "allwinner" in soc_lower or "h3" in soc_lower or "h5" in soc_lower:
        vendor_orgs.extend(["Allwinner"])
    
    # Search in vendor organizations first
    for org in vendor_orgs:
        for term in search_terms[:2]:  # Limit to top 2 search terms per org
            q = urllib.parse.urlencode({
                "q": f"{term} org:{org} language:C",
                "per_page": "3",
                "sort": "stars",
            })
            url = f"https://api.github.com/search/repositories?{q}"
            try:
                req = urllib.request.Request(url, headers=_github_headers())
                with urllib.request.urlopen(req, timeout=_GH_TIMEOUT) as r:
                    data = json.loads(r.read())
                repos = data.get("items", [])[:3]
                
                for repo in repos:
                    repo_name = repo.get("full_name", "")
                    if not repo_name:
                        continue
                    
                    # Search for driver code in this repo
                    for code_term in search_terms[:2]:
                        hit = _github_search_code_in_repo(code_term, repo_name)
                        if hit:
                            return {
                                "found": True,
                                "github_repo_name": repo_name,
                                "github_repo_url": repo.get("html_url", ""),
                                "github_url": hit.get("github_url", ""),
                                "github_path": hit.get("github_path", ""),
                                "driver_source": "vendor_public",
                            }
            except Exception:
                pass
    
    # Fallback: broad search across all of GitHub
    for term in search_terms[:1]:
        q = urllib.parse.urlencode({
            "q": f'"{term}" driver language:C -repo:torvalds/linux',
            "per_page": "3",
            "sort": "stars",
        })
        url = f"https://api.github.com/search/repositories?{q}"
        try:
            req = urllib.request.Request(url, headers=_github_headers())
            with urllib.request.urlopen(req, timeout=_GH_TIMEOUT) as r:
                data = json.loads(r.read())
            repos = data.get("items", [])[:3]
            
            for repo in repos:
                repo_name = repo.get("full_name", "")
                if not repo_name:
                    continue
                
                hit = _github_search_code_in_repo(term, repo_name)
                if hit:
                    return {
                        "found": True,
                        "github_repo_name": repo_name,
                        "github_repo_url": repo.get("html_url", ""),
                        "github_url": hit.get("github_url", ""),
                        "github_path": hit.get("github_path", ""),
                        "driver_source": "vendor_public",
                    }
        except Exception:
            pass
    
    return None


def _lookup_manufacturer_repo(peripheral: dict, driver_info: dict) -> dict:
    """
    Try to find a manufacturer GitHub repo for the component or driver.
    Returns repo_url/repo_name plus optional source file hit.
    Also searches vendor public repos if driver not found in Linux kernel.
    """
    module_name = driver_info.get("module", "")
    driver_status = driver_info.get("status", "")
    soc = peripheral.get("soc", "") if isinstance(peripheral, dict) else ""
    
    # Special case: vendor-specific components with hardcoded repos
    for comp_key, comp_info in _VENDOR_COMPONENTS.items():
        if module_name == comp_info["module"]:
            repo = comp_info.get("github_repo", "")
            if repo:
                repo_url = f"https://github.com/{repo}" if "/" in repo else repo
                return {
                    "github_repo_name": repo,
                    "github_repo_url": repo_url,
                    "github_url": repo_url,
                    "github_path": comp_info.get("path", ""),
                    "driver_source": "vendor_public",
                }
    
    component_ic = peripheral.get("component_ic") if isinstance(peripheral.get("component_ic"), dict) else {}
    ic_name = component_ic.get("name", "") or peripheral.get("name", "")
    for term in _repo_candidates(peripheral, driver_info)[:3]:
        repos = _github_search_repositories(term, limit=3)
        if not repos:
            continue

        repo = repos[0]
        full_name = repo.get("full_name", "")
        repo_url = repo.get("html_url", "")
        if not full_name or not repo_url:
            continue

        # Prefer concrete code hit in repo.
        for q in (module_name, ic_name, peripheral.get("name", "")):
            if not q:
                continue
            hit = _github_search_code_in_repo(q, full_name)
            if hit:
                return {
                    "github_repo_name": full_name,
                    "github_repo_url": repo_url,
                    "github_url": hit.get("github_url", ""),
                    "github_path": hit.get("github_path", ""),
                    "driver_source": "vendor_public",
                }

        # No file hit, still expose repo candidate.
        return {
            "github_repo_name": full_name,
            "github_repo_url": repo_url,
            "github_url": "",
            "github_path": "",
            "driver_source": "vendor_public",
        }
    
    # Search vendor public repos as fallback
    vendor_search = _search_vendor_public_repos(
        peripheral.get("name", ""),
        module_name,
        driver_status,
        soc,
    )
    if vendor_search and vendor_search.get("found"):
        return {
            "github_repo_name": vendor_search.get("github_repo_name", ""),
            "github_repo_url": vendor_search.get("github_repo_url", ""),
            "github_url": vendor_search.get("github_url", ""),
            "github_path": vendor_search.get("github_path", ""),
            "driver_source": "vendor_public",
        }

    return {
        "github_repo_name": "",
        "github_repo_url": "",
        "github_url": "",
        "github_path": "",
        "driver_source": "unknown",
    }


# ── Public API ─────────────────────────────────────────────────────────────────

# Vendor-specific component patterns → driver info mapping
_VENDOR_COMPONENTS = {
    # Intel components
    "ipu6": {
        "pattern": r"ipu[56]|imaging.*processor.*6",
        "module": "intel-ipu6",
        "kconfig": "IPU6",
        "since": "N/A",
        "path": "github.com/intel/ipu6-drivers",
        "status": "vendor",
        "maintainer": "Intel (ipu6-drivers)",
        "github_repo": "intel/ipu6-drivers",
    },
    "arc-gpu": {
        "pattern": r"arc.*(?:graphics|gpu)|intel.*arc",
        "module": "i915-xe",
        "kconfig": "DRM_XE",
        "since": "v6.2",
        "path": "drivers/gpu/drm/xe/",
        "status": "mainline",
        "maintainer": "Intel (DRM/GPU)",
        "github_repo": "torvalds/linux",
    },
    "iris-gpu": {
        "pattern": r"iris.*(?:graphics|gpu)|intel.*iris",
        "module": "i915",
        "kconfig": "DRM_I915",
        "since": "v3.2",
        "path": "drivers/gpu/drm/i915/",
        "status": "mainline",
        "maintainer": "Intel (DRM/GPU)",
        "github_repo": "torvalds/linux",
    },
    "gvt": {
        "pattern": r"gvt|graphics.*virtualization",
        "module": "kvmgt",
        "kconfig": "DRM_I915_GVT",
        "since": "v4.10",
        "path": "drivers/gpu/drm/i915/gvt/",
        "status": "mainline",
        "maintainer": "Intel (GVT)",
        "github_repo": "torvalds/linux",
    },
    "atsc-tuner": {
        "pattern": r"mceusb|atsc|tuner.*(?:at86rf|si)|media.*tuner",
        "module": "mceusb",
        "kconfig": "DVB_USB_MCEUSB",
        "since": "v2.6.37",
        "path": "drivers/media/usb/dvb-usb-v2/",
        "status": "mainline",
        "maintainer": "Mauro Carvalho Chehab",
        "github_repo": "torvalds/linux",
    },
    "movidius-vpu": {
        "pattern": r"movidius|myriad|neural.*engine|vpu",
        "module": "myriad",
        "kconfig": "MOVIDIUS_VPU",
        "since": "N/A",
        "path": "github.com/intel/openvino",
        "status": "vendor",
        "maintainer": "Intel (OpenVINO)",
        "github_repo": "intel/openvino",
    },
}

# GPU-specific driver mapping (model name → driver info)
_GPU_DRIVERS = {
    # NVIDIA GPUs
    "rtx 4090": {
        "module": "nvidia",
        "kconfig": "NVIDIA_DRIVER",
        "since": "N/A",
        "path": "github.com/NVIDIA/open-gpu-kernel-modules",
        "status": "vendor",
        "maintainer": "NVIDIA",
    },
    "rtx 4080": {
        "module": "nvidia",
        "kconfig": "NVIDIA_DRIVER",
        "since": "N/A",
        "path": "github.com/NVIDIA/open-gpu-kernel-modules",
        "status": "vendor",
        "maintainer": "NVIDIA",
    },
    "rtx 4070": {
        "module": "nvidia",
        "kconfig": "NVIDIA_DRIVER",
        "since": "N/A",
        "path": "github.com/NVIDIA/open-gpu-kernel-modules",
        "status": "vendor",
        "maintainer": "NVIDIA",
    },
    "rtx 40 series": {
        "module": "nvidia",
        "kconfig": "NVIDIA_DRIVER",
        "since": "N/A",
        "path": "github.com/NVIDIA/open-gpu-kernel-modules",
        "status": "vendor",
        "maintainer": "NVIDIA",
    },
    "tesla": {
        "module": "nvidia",
        "kconfig": "NVIDIA_DRIVER",
        "since": "N/A",
        "path": "github.com/NVIDIA/open-gpu-kernel-modules",
        "status": "vendor",
        "maintainer": "NVIDIA",
    },
    # AMD GPUs
    "radeon rx": {
        "module": "amdgpu",
        "kconfig": "DRM_AMDGPU",
        "since": "v4.2",
        "path": "drivers/gpu/drm/amd/amdgpu/",
        "status": "mainline",
        "maintainer": "AMD (amdgpu)",
    },
    "radeon": {
        "module": "radeon",
        "kconfig": "DRM_RADEON",
        "since": "v2.6.34",
        "path": "drivers/gpu/drm/radeon/",
        "status": "mainline",
        "maintainer": "AMD",
    },
    "mi300": {
        "module": "amdgpu",
        "kconfig": "DRM_AMDGPU",
        "since": "v6.3",
        "path": "drivers/gpu/drm/amd/amdgpu/",
        "status": "mainline",
        "maintainer": "AMD (amdgpu)",
    },
    # Intel GPUs
    "arc graphics": {
        "module": "i915-xe",
        "kconfig": "DRM_XE",
        "since": "v6.2",
        "path": "drivers/gpu/drm/xe/",
        "status": "mainline",
        "maintainer": "Intel (DRM/GPU)",
    },
    "iris graphics": {
        "module": "i915",
        "kconfig": "DRM_I915",
        "since": "v3.2",
        "path": "drivers/gpu/drm/i915/",
        "status": "mainline",
        "maintainer": "Intel (DRM/GPU)",
    },
    "intel gpu": {
        "module": "i915",
        "kconfig": "DRM_I915",
        "since": "v3.2",
        "path": "drivers/gpu/drm/i915/",
        "status": "mainline",
        "maintainer": "Intel (DRM/GPU)",
    },
}


def _is_generic_component(peripheral_name: str, peripheral_type: str) -> bool:
    """
    Check if component is generic (non-vendor specific).
    Generic components should not go through driver lookup.
    
    Examples of generic: "Audio", "GPU", "Camera", "Ethernet", "Display"
    Examples of specific: "RTX 4090", "Intel Arc", "IPU6", "ov8856", "mcp3208"
    """
    if not peripheral_name:
        return True
    
    name_lower = peripheral_name.lower().strip()
    type_lower = (peripheral_type or "").lower().strip()
    
    # Generic/too-vague component names (single word, no vendor/model info)
    generic_patterns = [
        r"^(unknown|generic|device|component|peripheral|module|chip|ic|board)$",
        r"^(audio|sound)$",
        r"^(display|screen|panel)$",
        r"^(camera|webcam)$",
        r"^(usb|connector|port|interface)$",
        r"^(power|regulator|battery)$",
        r"^(sensor|thermistor)$",
        r"^(ethernet|network|lan|wlan)$",
        r"^(gpio|pin|connector)$",
        r"^(clock|oscillator|pll)$",
        r"^gpu$",  # plain "GPU" is generic
        r"^controller$",
    ]
    
    # Check if name matches generic pattern
    for pattern in generic_patterns:
        if re.match(pattern, name_lower):
            return True
    
    # Single word + no numbers/vendor = likely generic
    if " " not in name_lower and not re.search(r"[0-9]", name_lower):
        # Exception: if has vendor keyword, it's specific
        vendors = ["intel", "nvidia", "amd", "broadcom", "qualcomm", "arm", "st", "nxp", "ti", "samsung", "onsemi", "nvidia"]
        if not any(v in name_lower for v in vendors):
            return True
    
    return False


def detect_vendor_components(peripheral_name: str, peripheral_type: str) -> Optional[dict]:
    """
    Detect vendor-specific components (IPU6, Arc GPU, etc.) from peripheral name/type.
    Returns driver info dict if found, else None.
    """
    name_lower = (peripheral_name or "").lower()
    type_lower = (peripheral_type or "").lower()
    search_text = f"{name_lower} {type_lower}"
    
    # GPU-specific lookup (preferred for gpu type)
    if "gpu" in type_lower:
        for gpu_model, gpu_info in _GPU_DRIVERS.items():
            if gpu_model.lower() in name_lower:
                return dict(gpu_info)
    
    # Vendor component lookup
    for comp_key, comp_info in _VENDOR_COMPONENTS.items():
        if re.search(comp_info["pattern"], search_text, re.I):
            return {
                "module": comp_info["module"],
                "kconfig": comp_info["kconfig"],
                "since": comp_info["since"],
                "path": comp_info["path"],
                "status": comp_info["status"],
                "maintainer": comp_info["maintainer"],
            }
    return None


def lookup_drivers(
    hw_map: dict,
    online: bool = True,
) -> list[dict]:
    """
    For each peripheral in hw_map, find the upstream Linux kernel driver
    and/or vendor public repository driver.

    Returns list of dicts:
      {
        peripheral_id, peripheral_name, peripheral_type,
        driver_module, kernel_since, kconfig, source_path,
        maintainer, status,              # mainline/backport/vendor/unknown
        github_url,                      # online lookup result (or "")
        driver_source,                   # "kernel" | "vendor_public" | "unknown"
        effort,                          # low/medium/high/investigate
        notes,
      }
    """
    soc = hw_map.get("soc", "")
    results: list[dict] = []

    for p in hw_map.get("peripherals", []):
        if not isinstance(p, dict):
            continue
        ptype_raw = p.get("type", "other")
        ptype = ptype_raw.lower() if isinstance(ptype_raw, str) and ptype_raw else "other"
        pid   = p.get("id", "")
        pname = p.get("name", pid)
        
        # Don't confuse touch controllers with GPIO pins
        # Touch (capacitive/resistive) uses I2C/SPI touchscreen drivers, not GPIO
        if "touch" in pname.lower() and "gpio" in ptype.lower():
            ptype = "touchscreen"  # Correct type for touch controllers

        # Skip driver lookup for generic (non-vendor-specific) components
        is_generic = _is_generic_component(pname, ptype)
        
        # Try vendor-specific detection FIRST (before generic DB lookup)
        info = detect_vendor_components(pname, ptype)
        
        # Fall back to component DB if no vendor match (check specific IC names like "goodix")
        if info is None and not is_generic:
            # Try multiple lookups: full name, first/last words, common IC model patterns
            words = pname.lower().split()
            candidates = [pname.lower(), words[0] if words else pname.lower(), words[-1] if words else pname.lower()]
            # Remove duplicates
            candidates = list(dict.fromkeys(candidates))
            
            for conn_type in ["i2c", "spi", "mipi_csi"]:
                for ic_candidate in candidates:
                    result = lookup_component_driver(ptype, ic_candidate, conn_type)
                    if result.get("status") != "unknown":
                        info = result
                        break
                if info:
                    break
        
        # Fall back to generic driver DB if no component/vendor match AND not a generic component
        if info is None and not is_generic:
            info = _lookup_db(soc, ptype)
        manufacturer_repo = {"github_repo_name": "", "github_repo_url": "", "github_url": "", "github_path": "", "driver_source": "unknown"}
        if online and isinstance(p, dict):
            try:
                manufacturer_repo = _lookup_manufacturer_repo(p, info or {})
            except Exception:
                manufacturer_repo = {"github_repo_name": "", "github_repo_url": "", "github_url": "", "github_path": "", "driver_source": "unknown"}

        if info is None:
            # Determine reason for no driver info
            if is_generic:
                notes = "Generic component (no vendor/model specified). Use specific component names (e.g., 'RTX 4090' instead of 'GPU')."
                effort = "N/A"
                driver_source = "unknown"
            else:
                notes = "No driver found in knowledge base."
                effort = "investigate"
                # Check vendor repos for unknown drivers
                driver_source = "unknown"
                if online:
                    vendor_search = _search_vendor_public_repos(pname, "", "", soc)
                    if vendor_search and vendor_search.get("found"):
                        driver_source = "vendor_public"
                        notes = f"Driver found in vendor repo: {vendor_search.get('github_repo_name', '')}"
            
            entry = {
                "peripheral_id":   pid,
                "peripheral_name": pname,
                "peripheral_type": ptype,
                "driver_module":   "unknown",
                "kernel_since":    "unknown",
                "kconfig":         "unknown",
                "source_path":     "unknown",
                "maintainer":      "unknown",
                "status":          "unknown",
                "github_url":      "",
                "github_repo_name": "",
                "github_repo_url": "",
                "driver_source":   driver_source,
                "effort":          effort,
                "notes":           notes,
            }
        else:
            status = info["status"]
            # Determine driver source: kernel or vendor public repo
            driver_source = "kernel" if status in ("mainline", "backport") else (manufacturer_repo.get("driver_source", "unknown"))
            
            effort = {
                "mainline": "low",
                "backport":  "medium",
                "vendor":    "high",
                "wip":       "medium",
                "unknown":   "investigate",
            }.get(status, "investigate")

            gh_url = ""
            gh_repo_name = ""
            gh_repo_url = ""
            if online:
                gh_url = manufacturer_repo.get("github_url", "")
                gh_repo_name = manufacturer_repo.get("github_repo_name", "")
                gh_repo_url = manufacturer_repo.get("github_repo_url", "")
                if not gh_url and status == "unknown":
                    gh = _github_search_driver(info.get("module", ""))
                    if gh:
                        gh_url = gh.get("github_url", "")

            entry = {
                "peripheral_id":   pid,
                "peripheral_name": pname,
                "peripheral_type": ptype,
                "driver_module":   info.get("module",      ""),
                "kernel_since":    info.get("since",       "unknown"),
                "kconfig":         info.get("kconfig",     ""),
                "source_path":     info.get("path",        ""),
                "maintainer":      info.get("maintainer",  "unknown"),
                "status":          status,
                "github_url":      gh_url,
                "github_repo_name": gh_repo_name,
                "github_repo_url": gh_repo_url,
                "driver_source":   driver_source,
                "effort":          effort,
                "notes":           "Manufacturer repo checked" if gh_repo_url else "",
            }

        results.append(entry)

    return results
