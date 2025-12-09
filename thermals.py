import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QTreeWidget, QTreeWidgetItem,
    QWidget, QVBoxLayout, QHeaderView, QStyle, QSplashScreen
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QPixmap

APP_NAME = "LX Thermals"
APP_VERSION = "1.0.0"
APP_AUTHOR = "WYUnknown89"


# -------------------------------------------------
# hwmon paths (your system)
# -------------------------------------------------
CPU_HWMON = Path("/sys/class/hwmon/hwmon4")   # k10temp
GPU_HWMONS = [
    Path("/sys/class/hwmon/hwmon2"),
    Path("/sys/class/hwmon/hwmon3"),
]
NVME_HWMON = Path("/sys/class/hwmon/hwmon1")  # nvme

PCI_IDS = Path("/usr/share/misc/pci.ids")

ASSETS_DIR = Path(__file__).parent / "assets"
SPLASH_IMAGE = ASSETS_DIR / "lx-thermals.png"
APP_ICON_IMAGE = ASSETS_DIR / "lx-thermals-icon.png"

# -------------------------------------------------
# Hardware name helpers
# -------------------------------------------------
def get_cpu_name():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "Unknown CPU"

def lookup_pci_name(vendor, device):
    if not PCI_IDS.exists():
        return None

    vendor = vendor.lower()
    device = device.lower()
    current_vendor = None

    for line in PCI_IDS.read_text(errors="ignore").splitlines():
        if not line or line.startswith("#"):
            continue

        if not line.startswith("\t"):
            parts = line.split(maxsplit=1)
            current_vendor = parts[1] if parts[0].lower() == vendor and len(parts) > 1 else None
        elif current_vendor:
            parts = line.strip().split(maxsplit=1)
            if parts[0].lower() == device:
                return f"{current_vendor} {parts[1]}"

    return None

def get_gpu_name():
    try:
        for card in Path("/sys/class/drm").glob("card*"):
            vendor_file = card / "device/vendor"
            device_file = card / "device/device"

            if not (vendor_file.exists() and device_file.exists()):
                continue

            vendor = vendor_file.read_text().strip().replace("0x", "")
            device = device_file.read_text().strip().replace("0x", "")

            name = lookup_pci_name(vendor, device)
            if name:
                return name, True

            return f"AMD Radeon [{vendor}:{device}]", False
    except Exception:
        pass

    return "Unknown GPU", False

CPU_NAME = get_cpu_name()
GPU_NAME, GPU_NAME_KNOWN = get_gpu_name()

# -------------------------------------------------
# Min / Max storage
# -------------------------------------------------
cpu_pkg_min = cpu_pkg_max = None
cpu_die_min = cpu_die_max = None
cpu_clk_min = cpu_clk_max = None

gpu_temp_min = gpu_temp_max = None
gpu_hot_min = gpu_hot_max = None
gpu_mem_min = gpu_mem_max = None
gpu_clk_min = gpu_clk_max = None
gpu_memclk_min = gpu_memclk_max = None
gpu_fan_min = gpu_fan_max = None

nvme_min = nvme_max = None

# -------------------------------------------------
# Generic hwmon reader (temps)
# -------------------------------------------------
def read_hwmon(path):
    results = {}

    for p in path.glob("temp*_input"):
        idx = p.stem.replace("temp", "").replace("_input", "")
        label = path / f"temp{idx}_label"
        crit = path / f"temp{idx}_crit"

        if label.exists():
            name = label.read_text().strip()
            value = int(p.read_text().strip()) / 1000
            crit_val = int(crit.read_text().strip()) / 1000 if crit.exists() else None
            results[name] = (value, crit_val)

    return results

# -------------------------------------------------
# Clock / fan readers
# -------------------------------------------------
def read_cpu_clock():
    freqs = []
    for cpu in Path("/sys/devices/system/cpu").glob("cpu[0-9]*"):
        f = cpu / "cpufreq/scaling_cur_freq"
        if f.exists():
            freqs.append(int(f.read_text().strip()) / 1_000_000)  # GHz
    return sum(freqs) / len(freqs) if freqs else None

def read_gpu_clocks_and_fan():
    core_clocks = []
    mem_clock = None
    fan = None

    for h in GPU_HWMONS:
        for p in h.glob("freq*_input"):
            val = int(p.read_text().strip())
            if val > 0:
                core_clocks.append(val / 1_000_000)  # MHz

        f = h / "fan1_input"
        if f.exists():
            fan = int(f.read_text().strip())

        m = h / "freq2_input"
        if m.exists():
            mem_clock = int(m.read_text().strip()) / 1_000_000  # MHz

    core = max(core_clocks) if core_clocks else None
    return core, mem_clock, fan

# -------------------------------------------------
# Colour helpers
# -------------------------------------------------
def temp_colour(value):
    if value >= 85:
        return QColor("#c0392b")
    if value >= 80:
        return QColor("#f39c12")
    return None

def set_temp_colour(item, column, value):
    colour = temp_colour(value)
    item.setForeground(column, colour if colour else QColor())

# -------------------------------------------------
# UI + Splash
# -------------------------------------------------
app = QApplication(sys.argv)

app_icon_pixmap = QPixmap(str(APP_ICON_IMAGE))
splash_pixmap = QPixmap(str(SPLASH_IMAGE))

app.setWindowIcon(app_icon_pixmap)

splash = QSplashScreen(splash_pixmap)
splash.show()
app.processEvents()

SPLASH_MIN_MS = 5000  # 5 seconds minimum

window = QWidget()
window.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
window.resize(750, 420)

layout = QVBoxLayout(window)
tree = QTreeWidget()
tree.setColumnCount(5)
tree.setHeaderLabels(["Sensor", "Current", "Min", "Max", "Crit"])

header = tree.header()
font = QFont()
font.setBold(True)
header.setFont(font)

tree.setColumnWidth(0, 260)
header.setSectionResizeMode(0, QHeaderView.Fixed)
for col in range(1, 5):
    header.setSectionResizeMode(col, QHeaderView.Stretch)

layout.addWidget(tree)

# -------------------------------------------------
# CPU
# -------------------------------------------------
cpu_parent = QTreeWidgetItem(tree, [f"CPU ({CPU_NAME})"])
cpu_parent.setExpanded(True)

cpu_pkg_item = QTreeWidgetItem(cpu_parent, ["CPU Package"])
cpu_die_item = QTreeWidgetItem(cpu_parent, ["CPU Die"])
cpu_clk_item = QTreeWidgetItem(cpu_parent, ["CPU Clock (GHz)"])

for item in (cpu_pkg_item, cpu_die_item):
    item.setText(4, "—")
    item.setForeground(4, QColor("gray"))
    item.setToolTip(4, "CPU critical temperature not exposed by kernel")

# -------------------------------------------------
# GPU
# -------------------------------------------------
gpu_parent = QTreeWidgetItem(tree, [f"GPU ({GPU_NAME})"])
gpu_parent.setExpanded(True)

if not GPU_NAME_KNOWN:
    gpu_parent.setToolTip(
        0,
        "GPU model name not yet available in the system PCI database.\n"
        "This will update automatically when pci.ids is refreshed."
    )
    gpu_parent.setIcon(0, app.style().standardIcon(QStyle.SP_MessageBoxInformation))

gpu_temp_item = QTreeWidgetItem(gpu_parent, ["GPU Temp"])
gpu_hot_item = QTreeWidgetItem(gpu_parent, ["GPU Hotspot"])
gpu_mem_item = QTreeWidgetItem(gpu_parent, ["GPU Memory"])
gpu_clk_item = QTreeWidgetItem(gpu_parent, ["GPU Core Clock (MHz)"])
gpu_memclk_item = QTreeWidgetItem(gpu_parent, ["GPU Memory Clock (MHz)"])
gpu_fan_item = QTreeWidgetItem(gpu_parent, ["GPU Fan Speed (RPM)"])

# -------------------------------------------------
# Storage
# -------------------------------------------------
storage_parent = QTreeWidgetItem(tree, ["Storage"])
storage_parent.setExpanded(True)

nvme_item = QTreeWidgetItem(storage_parent, ["NVMe Composite"])
nvme_item.setText(4, "—")
nvme_item.setForeground(4, QColor("gray"))
nvme_item.setToolTip(4, "Critical temperature not exposed by kernel")

# -------------------------------------------------
# Update loop
# -------------------------------------------------
def update():
    global cpu_pkg_min, cpu_pkg_max, cpu_die_min, cpu_die_max
    global cpu_clk_min, cpu_clk_max
    global gpu_temp_min, gpu_temp_max, gpu_hot_min, gpu_hot_max, gpu_mem_min, gpu_mem_max
    global gpu_clk_min, gpu_clk_max, gpu_memclk_min, gpu_memclk_max, gpu_fan_min, gpu_fan_max
    global nvme_min, nvme_max

    cpu = read_hwmon(CPU_HWMON)

    if "Tctl" in cpu:
        t, _ = cpu["Tctl"]
        cpu_pkg_min = t if cpu_pkg_min is None else min(cpu_pkg_min, t)
        cpu_pkg_max = t if cpu_pkg_max is None else max(cpu_pkg_max, t)
        cpu_pkg_item.setText(1, f"{t:.1f}")
        cpu_pkg_item.setText(2, f"{cpu_pkg_min:.1f}")
        cpu_pkg_item.setText(3, f"{cpu_pkg_max:.1f}")
        set_temp_colour(cpu_pkg_item, 1, t)

    if "Tccd1" in cpu:
        t, _ = cpu["Tccd1"]
        cpu_die_min = t if cpu_die_min is None else min(cpu_die_min, t)
        cpu_die_max = t if cpu_die_max is None else max(cpu_die_max, t)
        cpu_die_item.setText(1, f"{t:.1f}")
        cpu_die_item.setText(2, f"{cpu_die_min:.1f}")
        cpu_die_item.setText(3, f"{cpu_die_max:.1f}")
        set_temp_colour(cpu_die_item, 1, t)

    clk = read_cpu_clock()
    if clk:
        cpu_clk_min = clk if cpu_clk_min is None else min(cpu_clk_min, clk)
        cpu_clk_max = clk if cpu_clk_max is None else max(cpu_clk_max, clk)
        cpu_clk_item.setText(1, f"{clk:.2f}")
        cpu_clk_item.setText(2, f"{cpu_clk_min:.2f}")
        cpu_clk_item.setText(3, f"{cpu_clk_max:.2f}")

    for path in GPU_HWMONS:
        gpu = read_hwmon(path)

        if "edge" in gpu:
            t, c = gpu["edge"]
            gpu_temp_min = t if gpu_temp_min is None else min(gpu_temp_min, t)
            gpu_temp_max = t if gpu_temp_max is None else max(gpu_temp_max, t)
            gpu_temp_item.setText(1, f"{t:.1f}")
            gpu_temp_item.setText(2, f"{gpu_temp_min:.1f}")
            gpu_temp_item.setText(3, f"{gpu_temp_max:.1f}")
            if c:
                gpu_temp_item.setText(4, f"{c:.0f}")
                gpu_temp_item.setForeground(4, QColor("#c0392b"))

        if "junction" in gpu:
            t, c = gpu["junction"]
            gpu_hot_min = t if gpu_hot_min is None else min(gpu_hot_min, t)
            gpu_hot_max = t if gpu_hot_max is None else max(gpu_hot_max, t)
            gpu_hot_item.setText(1, f"{t:.1f}")
            gpu_hot_item.setText(2, f"{gpu_hot_min:.1f}")
            gpu_hot_item.setText(3, f"{gpu_hot_max:.1f}")
            if c:
                gpu_hot_item.setText(4, f"{c:.0f}")
                gpu_hot_item.setForeground(4, QColor("#c0392b"))

        if "mem" in gpu:
            t, c = gpu["mem"]
            gpu_mem_min = t if gpu_mem_min is None else min(gpu_mem_min, t)
            gpu_mem_max = t if gpu_mem_max is None else max(gpu_mem_max, t)
            gpu_mem_item.setText(1, f"{t:.1f}")
            gpu_mem_item.setText(2, f"{gpu_mem_min:.1f}")
            gpu_mem_item.setText(3, f"{gpu_mem_max:.1f}")
            if c:
                gpu_mem_item.setText(4, f"{c:.0f}")
                gpu_mem_item.setForeground(4, QColor("#c0392b"))

    gclk, gmemclk, gfan = read_gpu_clocks_and_fan()

    if gclk:
        gpu_clk_min = gclk if gpu_clk_min is None else min(gpu_clk_min, gclk)
        gpu_clk_max = gclk if gpu_clk_max is None else max(gpu_clk_max, gclk)
        gpu_clk_item.setText(1, f"{gclk:.0f}")
        gpu_clk_item.setText(2, f"{gpu_clk_min:.0f}")
        gpu_clk_item.setText(3, f"{gpu_clk_max:.0f}")

    if gmemclk:
        gpu_memclk_min = gmemclk if gpu_memclk_min is None else min(gpu_memclk_min, gmemclk)
        gpu_memclk_max = gmemclk if gpu_memclk_max is None else max(gpu_memclk_max, gmemclk)
        gpu_memclk_item.setText(1, f"{gmemclk:.0f}")
        gpu_memclk_item.setText(2, f"{gpu_memclk_min:.0f}")
        gpu_memclk_item.setText(3, f"{gpu_memclk_max:.0f}")

    if gfan is not None:
        gpu_fan_min = gfan if gpu_fan_min is None else min(gpu_fan_min, gfan)
        gpu_fan_max = gfan if gpu_fan_max is None else max(gpu_fan_max, gfan)
        gpu_fan_item.setText(1, f"{gfan}")
        gpu_fan_item.setText(2, f"{gpu_fan_min}")
        gpu_fan_item.setText(3, f"{gpu_fan_max}")

    nvme = read_hwmon(NVME_HWMON)
    if nvme:
        _, (t, _) = next(iter(nvme.items()))
        nvme_min = t if nvme_min is None else min(nvme_min, t)
        nvme_max = t if nvme_max is None else max(nvme_max, t)
        nvme_item.setText(1, f"{t:.1f}")
        nvme_item.setText(2, f"{nvme_min:.1f}")
        nvme_item.setText(3, f"{nvme_max:.1f}")

timer = QTimer()
timer.timeout.connect(update)
timer.start(1000)

def show_main():
    window.show()
    splash.finish(window)
    update()

QTimer.singleShot(SPLASH_MIN_MS, show_main)

sys.exit(app.exec())
