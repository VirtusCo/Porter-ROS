# Zephyr RTOS — Build System (CMake, Kconfig, Devicetree) — Skill File

> Source: https://docs.zephyrproject.org/latest/build/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

Zephyr's build system has three pillars:
1. **CMake** — Build orchestration
2. **Kconfig** — Software configuration (`CONFIG_*` symbols)
3. **Devicetree** — Hardware description (DTS/DTSI/overlay)

---

## 1. CMake Build System

### Build Flow
```
CMakeLists.txt → find_package(Zephyr) → Configure → Generate → Build
                                         ↓
                                  prj.conf → Kconfig merge → .config
                                  app.overlay → DTS merge → devicetree_generated.h
```

### Key CMake Functions

```cmake
# Required: find Zephyr package
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

# Project name (MUST come after find_package)
project(my_app)

# Add source files
target_sources(app PRIVATE src/main.c src/driver.c)

# Add include paths
target_include_directories(app PRIVATE include/)

# Add compile definitions
target_compile_definitions(app PRIVATE MY_DEFINE=1)

# Link libraries
target_link_libraries(app PRIVATE my_lib)
```

### Zephyr CMake Package
- Auto-detected in workspace apps
- For freestanding apps: set `ZEPHYR_BASE` env var
- `find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})`

---

## 2. Kconfig System

### Configuration Hierarchy (lowest to highest priority)
1. SoC/board `*_defconfig` files (base)
2. Application `prj.conf` (app overrides)
3. Board-specific `boards/<board>.conf` (board overrides)
4. `EXTRA_CONF_FILE` (additional overrides)
5. Command-line `-DCONFIG_*=y` (highest)

### Common Kconfig Patterns

```kconfig
# Enable a feature
CONFIG_GPIO=y

# Set a numeric value
CONFIG_MAIN_STACK_SIZE=4096

# Set a string value
CONFIG_USB_DEVICE_PRODUCT="Porter Motor Controller"

# Disable a feature (set to n)
CONFIG_PRINTK=n
```

### Interactive Configuration

```bash
# Terminal-based menu
west build -t menuconfig

# GUI-based menu
west build -t guiconfig
```

### Kconfig Search
- Online: https://docs.zephyrproject.org/latest/kconfig.html
- Build-time: `west build -t menuconfig` → search with `/`

### Experimental Features Warning
```kconfig
CONFIG_WARN_EXPERIMENTAL=y
```

---

## 3. Devicetree System

### Devicetree Compilation Flow
```
Board .dts + SoC .dtsi + app.overlay → DTC compiler → zephyr.dts → devicetree_generated.h
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Node** | Represents a hardware component |
| **Property** | Key-value pair on a node |
| **Compatible** | Identifies the driver binding |
| **Status** | `"okay"` (enabled) or `"disabled"` |
| **Phandle** | Reference to another node |
| **Label** | Named reference (`&label_name`) |

### Devicetree Overlay Syntax

```dts
/* Enable a disabled peripheral */
&uart0 {
    status = "okay";
    current-speed = <115200>;
};

/* Add a new child node */
&i2c0 {
    my_sensor: sensor@48 {
        compatible = "vendor,my-sensor";
        reg = <0x48>;
        int-gpios = <&gpio0 5 GPIO_ACTIVE_LOW>;
    };
};

/* Override chosen nodes */
/ {
    chosen {
        zephyr,console = &uart0;
    };
};

/* Define aliases */
/ {
    aliases {
        led0 = &green_led;
        sw0 = &user_button;
    };
};
```

### Devicetree Macros in C

```c
/* Node identifiers */
#define MY_NODE DT_NODELABEL(my_sensor)
#define UART_NODE DT_CHOSEN(zephyr_console)
#define LED_NODE DT_ALIAS(led0)
#define PATH_NODE DT_PATH(soc, i2c_40003000)

/* Property access */
DT_PROP(node, property_name)       /* Get property value */
DT_REG_ADDR(node)                  /* Get reg address */
DT_REG_SIZE(node)                  /* Get reg size */

/* Existence checks */
DT_NODE_EXISTS(node)               /* Does node exist? */
DT_NODE_HAS_STATUS(node, okay)     /* Is node enabled? */
DT_HAS_CHOSEN(zephyr_console)      /* Is chosen defined? */

/* GPIO from devicetree */
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

/* PWM from devicetree */
static const struct pwm_dt_spec pwm = PWM_DT_SPEC_GET(DT_ALIAS(pwm0));
```

---

## 4. Sysbuild (Multi-Image Builds)

For building multiple images (e.g., bootloader + app):

```bash
west build -b esp32_devkitc/esp32/procpu --sysbuild my_app
```

Sysbuild can build MCUboot + application in one step.

---

## 5. Flashing & Signing

### Flash Commands
```bash
west flash                    # Flash with default runner
west flash --runner openocd   # Use specific runner
west flash --recover          # Recover bricked board (if supported)
```

### ESP32 Flashing
```bash
west flash                    # Uses esptool by default for ESP32
west espressif monitor        # Serial monitor
```

### Binary Signing (MCUboot)
```bash
west sign -t imgtool -- --key my_key.pem
```

---

## 6. Version Management

### VERSION file
```
VERSION_MAJOR = 0
VERSION_MINOR = 1
PATCHLEVEL = 0
VERSION_TWEAK = 0
```

### Access in code
```c
#include <zephyr/version.h>

printk("Zephyr version: %s\n", KERNEL_VERSION_STRING);
printk("App version: %d.%d.%d\n",
    APP_VERSION_MAJOR, APP_VERSION_MINOR, APP_PATCHLEVEL);
```

---

## 7. Snippets

Reusable configuration fragments:

```bash
# Apply a snippet
west build -b <board> -S <snippet_name>

# Example: enable CDC ACM console
west build -b esp32_devkitc/esp32/procpu -S cdc-acm-console
```

Snippets combine Kconfig and devicetree changes into named, reusable units.
