# LX Thermals

LX Thermals is a lightweight hardware monitoring application for Linux, built with PySide6.

It provides a clean, HWMonitor-style view of system temperatures, clocks, and fan speeds using
direct kernel interfaces (`/sys/class/hwmon`) — no background services, no bloat.

## Features

- CPU temperature monitoring (package and die)
- CPU clock speed monitoring
- GPU temperature monitoring (edge, hotspot, memory)
- GPU core clock, memory clock, and fan speed
- NVMe temperature monitoring
- Min / Max tracking
- Visual temperature warnings
- Native Qt UI
- AppImage distribution (no installation required)

## Supported Hardware

### Fully Supported
- AMD CPUs
- AMD GPUs
- NVMe SSDs

### Not Currently Supported
- Intel CPUs
- NVIDIA GPUs

## Credits
Created by WYUnknown89 © 2025

## Installation

Download the AppImage and run:

```bash
chmod +x LX_Thermals-x86_64.AppImage
./LX_Thermals-x86_64.AppImage
