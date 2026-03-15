#!/usr/bin/env bash
# =============================================================================
# N.O.V.A Hybrid USB Builder
# =============================================================================
# Builds a hybrid USB that works in TWO modes automatically:
#
#   BOOT MODE   — Insert USB before power-on → boots full Arch Linux + Nova OS
#   PLUGIN MODE — Insert USB into running OS → Nova launches as portable app
#
# Detection is automatic:
#   - Boot mode: GRUB/syslinux detects USB as primary boot device
#   - Plugin mode: udev rule (Linux) / launch script (Windows/Mac) fires Nova
#
# Partition layout:
#   P1  FAT32  ~256MB  "NOVA"      EFI + plugin launcher (visible to ALL OSes)
#   P2  ext4   ~6GB    "nova-os"   Full Arch Linux root (boot mode only)
#   P3  ext4   rest    "nova-data" Shared persistent state (BOTH modes share this)
#
# Requirements:
#   - archiso, parted, mkfs.fat, mkfs.ext4
#   - Root privileges
#
# Usage:
#   sudo bash tools/os/build_usb.sh --usb /dev/sdX    full hybrid USB
#   sudo bash tools/os/build_usb.sh --iso              build ISO only
#   sudo bash tools/os/build_usb.sh --plugin-only      write plugin partition only
#   sudo bash tools/os/build_usb.sh --help
# =============================================================================

set -euo pipefail

NOVA_HOME="$HOME/Nova"
WORK_DIR="/tmp/nova-archiso-work"
ISO_NAME="nova-os-$(date +%Y%m%d).iso"
ISO_OUT="$NOVA_HOME/tools/os/${ISO_NAME}"
PROFILE_DIR="$NOVA_HOME/tools/os/archiso-profile"
PLUGIN_DIR="$NOVA_HOME/tools/os/plugin"   # built into FAT32 P1

NC='\033[0m'; G='\033[32m'; R='\033[31m'; Y='\033[33m'; B='\033[1m'

log()  { echo -e "${G}[nova-usb]${NC} $*"; }
warn() { echo -e "${Y}[warn]${NC} $*"; }
die()  { echo -e "${R}[error]${NC} $*"; exit 1; }

usage() {
  cat <<EOF
${B}N.O.V.A Hybrid USB Builder${NC}

Usage: sudo bash tools/os/build_usb.sh [OPTIONS]

Options:
  --usb /dev/sdX      Write full hybrid USB (boot + plugin modes)
  --iso               Build boot ISO only
  --plugin-only       Write plugin partition to existing USB
  --help              Show this help

Modes after writing:
  BOOT mode   Insert USB at power-on → full Arch Linux Nova OS
  PLUGIN mode Insert USB into running OS → Nova auto-launches as portable app
              Works on Linux, Windows (WSL/portable Python), and macOS

Shared nova-data partition keeps memory + state identical across both modes.
EOF
}


# =============================================================================
# PLUGIN PARTITION — files written to FAT32 P1 (visible to all OSes)
# =============================================================================

build_plugin_partition() {
  log "Building plugin launcher files..."
  mkdir -p "$PLUGIN_DIR"

  # ── nova_detect.py — the universal entry point ────────────────────────────
  # This runs on ANY OS with Python 3.8+ and decides what to do
  cat > "$PLUGIN_DIR/nova_detect.py" << 'DETECT'
#!/usr/bin/env python3
"""
N.O.V.A Plugin Mode Launcher

Detects the host environment and launches Nova appropriately.
Runs when USB is inserted into a running OS.
"""
import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

USB_ROOT  = Path(__file__).parent
DATA_PART = None   # Filled in after mount

BANNER = """
  ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗
  ████╗  ██║██╔═══██╗██║   ██║██╔══██╗
  ██╔██╗ ██║██║   ██║██║   ██║███████║
  ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║
  ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║
  ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝
  Neural Ontology for Virtual Awareness
  Plugin Mode — Running on host OS
"""

def detect_nova_data() -> Path | None:
    """Find the nova-data partition mount point."""
    # Check common mount locations
    for candidate in [
        Path("/media") / os.environ.get("USER", "nova") / "nova-data",
        Path("/mnt/nova-data"),
        Path("/run/media") / os.environ.get("USER", "nova") / "nova-data",
    ]:
        if candidate.exists():
            return candidate
    return None


def find_docker() -> bool:
    return shutil.which("docker") is not None


def find_python() -> str | None:
    for cmd in ("python3", "python"):
        if shutil.which(cmd):
            return shutil.which(cmd)
    return None


def launch_linux(nova_data: Path | None) -> None:
    """Launch Nova on Linux host."""
    print("[nova] Linux host detected.")

    # Preferred: Docker container (isolated, reproducible)
    if find_docker():
        print("[nova] Docker available — launching in container...")
        data_mount = str(nova_data) if nova_data else "/tmp/nova-data"
        os.makedirs(data_mount, exist_ok=True)
        cmd = [
            "docker", "run", "--rm", "-it",
            "--name", "nova-plugin",
            "--network", "host",
            "-v", f"{data_mount}:/home/nova/Nova/memory",
            "-v", f"{USB_ROOT}:/usb:ro",
            "-e", "NOVA_MODEL=gemma2:2b",
            "nova-plugin:latest",   # built by install script below
            "python3", "/home/nova/Nova/bin/nova_life.py"
        ]
        # Try to build image if not present
        _ensure_docker_image()
        subprocess.run(cmd)
        return

    # Fallback: run directly if Python + Nova deps available
    py = find_python()
    if py and nova_data:
        nova_dir = nova_data.parent.parent  # nova-data/../../Nova
        if (nova_data / "nova_identity.json").exists():
            print("[nova] Running Nova directly with host Python...")
            env = {**os.environ, "NOVA_HOME": str(nova_data.parent)}
            subprocess.run([py, str(USB_ROOT / "nova_plugin_cli.py")], env=env)
            return

    # Last resort: instructions
    print("[nova] To run Nova, install Docker or Python 3.10+")
    print("[nova] Then run: python3 nova_detect.py")


def launch_windows() -> None:
    """Launch Nova on Windows host."""
    print("[nova] Windows host detected.")
    # Check for WSL
    wsl = shutil.which("wsl")
    if wsl:
        print("[nova] WSL detected — launching Nova in WSL...")
        subprocess.run([wsl, "python3", "/mnt/usb/nova_detect.py", "--wsl"])
        return
    # Check for portable Python bundled on USB
    portable_py = USB_ROOT / "windows/python/python.exe"
    if portable_py.exists():
        print("[nova] Portable Python detected — launching...")
        subprocess.run([str(portable_py), str(USB_ROOT / "nova_plugin_cli.py")])
        return
    print("[nova] Please install WSL or Python 3.10+ to run Nova on Windows.")
    print("[nova] WSL: wsl --install  (then re-insert USB)")


def launch_mac() -> None:
    """Launch Nova on macOS host."""
    print("[nova] macOS host detected.")
    py = find_python()
    if py:
        subprocess.run([py, str(USB_ROOT / "nova_plugin_cli.py")])
    else:
        print("[nova] Please install Python 3.10+: brew install python")


def _ensure_docker_image() -> None:
    """Build Nova Docker image if not present."""
    result = subprocess.run(
        ["docker", "image", "inspect", "nova-plugin:latest"],
        capture_output=True
    )
    if result.returncode != 0:
        dockerfile = USB_ROOT / "Dockerfile"
        if dockerfile.exists():
            print("[nova] Building Docker image (first run — ~2 min)...")
            subprocess.run(["docker", "build", "-t", "nova-plugin:latest",
                            str(USB_ROOT)])


def main():
    print(BANNER)
    system = platform.system()
    nova_data = detect_nova_data()

    if nova_data:
        print(f"[nova] Found persistent data at: {nova_data}")
    else:
        print("[nova] No nova-data partition mounted. Using temporary storage.")

    if system == "Linux":
        launch_linux(nova_data)
    elif system == "Windows":
        launch_windows()
    elif system == "Darwin":
        launch_mac()
    else:
        print(f"[nova] Unknown OS: {system}. Try running nova_plugin_cli.py directly.")


if __name__ == "__main__":
    main()
DETECT

  # ── nova_plugin_cli.py — minimal CLI for plugin mode ─────────────────────
  cat > "$PLUGIN_DIR/nova_plugin_cli.py" << 'PLUGINCLI'
#!/usr/bin/env python3
"""
N.O.V.A Plugin CLI — runs when Nova is in plugin mode (USB inserted into running OS).
Connects to the nova-data partition for persistent memory.
"""
import os
import sys
import json
import subprocess
from pathlib import Path

USB_ROOT = Path(__file__).parent

# Find nova-data mount
def find_nova_home() -> Path:
    candidates = [
        Path("/media") / os.environ.get("USER", "") / "nova-data",
        Path("/mnt/nova-data"),
        Path("/run/media") / os.environ.get("USER", "") / "nova-data",
        Path.home() / ".nova-plugin-data",   # fallback: host home
    ]
    for c in candidates:
        if c.exists():
            return c
    # Create fallback
    fb = Path.home() / ".nova-plugin-data"
    fb.mkdir(parents=True, exist_ok=True)
    return fb

NOVA_DATA = find_nova_home()
sys.path.insert(0, str(USB_ROOT))

G  = "\033[32m"; R = "\033[31m"; C = "\033[36m"
W  = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

def show_banner():
    print(f"\n{M}{B}N.O.V.A  Plugin Mode{NC}" if (M := "\033[35m") else "")
    print(f"  {DIM}Data: {NOVA_DATA}{NC}")

    # Load identity if available
    id_file = NOVA_DATA / "nova_identity.json"
    if id_file.exists():
        try:
            identity = json.loads(id_file.read_text())
            print(f"  {C}v{identity.get('version','?')}  "
                  f"Mission: {identity.get('mission','...')[:60]}{NC}")
        except Exception:
            pass
    print()

def menu():
    show_banner()
    while True:
        print(f"{B}What would you like to do?{NC}")
        print(f"  {G}1{NC}  nova think — ask Nova anything")
        print(f"  {G}2{NC}  nova status — system overview")
        print(f"  {G}3{NC}  nova markets — market analysis")
        print(f"  {G}4{NC}  nova phantom — wallet check")
        print(f"  {G}5{NC}  nova dream — run dream cycle")
        print(f"  {G}6{NC}  shell — open Nova shell")
        print(f"  {G}q{NC}  quit")
        print()

        choice = input(f"{C}> {NC}").strip().lower()

        if choice == "q":
            print(f"{DIM}Nova going dormant. Data saved to {NOVA_DATA}{NC}")
            break
        elif choice == "1":
            q = input(f"{C}Ask Nova: {NC}").strip()
            if q:
                _run_nova(["think", q])
        elif choice == "2":
            _run_nova(["status"])
        elif choice == "3":
            syms = input(f"{C}Symbols (e.g. BTC ETH SOL): {NC}").strip().split()
            _run_nova(["markets"] + (syms or []))
        elif choice == "4":
            _run_nova(["phantom", "status"])
        elif choice == "5":
            _run_nova(["dream"])
        elif choice == "6":
            print(f"{DIM}Entering Nova shell. Type 'exit' to return.{NC}")
            subprocess.run(["bash", "--rcfile", str(USB_ROOT / "nova_bashrc.sh")],
                           env={**os.environ,
                                "NOVA_HOME": str(NOVA_DATA),
                                "PS1": r"\[\033[35m\]N.O.V.A\[\033[0m\] \w ∴ "})

def _run_nova(args: list[str]) -> None:
    nova_bin = USB_ROOT / "nova_bin.py"
    if nova_bin.exists():
        subprocess.run([sys.executable, str(nova_bin)] + args,
                       env={**os.environ, "NOVA_HOME": str(NOVA_DATA)})
    else:
        print(f"{R}Nova binary not found on USB. Boot mode may be needed.{NC}")

if __name__ == "__main__":
    menu()
PLUGINCLI

  # ── Dockerfile for Linux Docker plugin mode ───────────────────────────────
  cat > "$PLUGIN_DIR/Dockerfile" << 'DOCKERFILE'
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git curl wget espeak-ng sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    requests yfinance pandas numpy \
    mastodon.py qiskit qiskit-aer

RUN useradd -m nova
WORKDIR /home/nova

# Nova source (mounted from USB or baked in)
COPY . /home/nova/Nova/
RUN chown -R nova:nova /home/nova/Nova

USER nova
ENV NOVA_HOME=/home/nova/Nova
ENV NOVA_MODEL=gemma2:2b
ENV PATH="/home/nova/Nova/bin:$PATH"

CMD ["python3", "/home/nova/Nova/bin/nova_life.py"]
DOCKERFILE

  # ── udev rule for Linux auto-launch ───────────────────────────────────────
  # Install this on the host: sudo cp nova-udev.rules /etc/udev/rules.d/99-nova.rules
  cat > "$PLUGIN_DIR/nova-udev.rules" << 'UDEV'
# N.O.V.A Auto-launch when USB inserted
# Install: sudo cp nova-udev.rules /etc/udev/rules.d/99-nova.rules
#          sudo udevadm control --reload-rules
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="NOVA", \
    RUN+="/bin/bash -c 'sleep 2 && su -c \"python3 /media/%E{UDEV_USER}/NOVA/nova_detect.py\" %E{UDEV_USER} &'"
UDEV

  # ── Windows launcher ──────────────────────────────────────────────────────
  cat > "$PLUGIN_DIR/launch.bat" << 'WBAT'
@echo off
title N.O.V.A
echo.
echo   N.O.V.A Plugin Mode
echo   Neural Ontology for Virtual Awareness
echo.
where python >nul 2>&1
if %errorlevel% == 0 (
    python nova_detect.py
) else (
    where wsl >nul 2>&1
    if %errorlevel% == 0 (
        wsl python3 /mnt/usb/nova_detect.py
    ) else (
        echo Python or WSL not found.
        echo Install Python from python.org or enable WSL.
        echo Then re-run this launcher.
        pause
    )
)
WBAT

  # ── macOS launcher ────────────────────────────────────────────────────────
  cat > "$PLUGIN_DIR/launch.command" << 'MACCMD'
#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "N.O.V.A Plugin Mode — macOS"
if command -v python3 &>/dev/null; then
    python3 nova_detect.py
else
    echo "Python 3 not found. Install with: brew install python"
    open "https://www.python.org/downloads/"
fi
MACCMD
  chmod +x "$PLUGIN_DIR/launch.command"

  # ── README on the FAT32 partition ─────────────────────────────────────────
  cat > "$PLUGIN_DIR/README.txt" << 'README'
N.O.V.A Hybrid USB
==================

BOOT MODE: Insert USB before turning on your computer.
  - Select USB as boot device in BIOS/UEFI (usually F12 or Del)
  - Nova OS (Arch Linux) boots automatically
  - Full capabilities: Ollama LLM, all tools, persistent memory

PLUGIN MODE: Insert USB into a running computer.
  Linux:   nova_detect.py runs automatically (if udev rule installed)
           Or manually: python3 /media/NOVA/nova_detect.py
  Windows: Double-click launch.bat
  macOS:   Double-click launch.command

MEMORY: All modes share the same memory (nova-data partition).
  Nova remembers everything regardless of which mode you used last.

SETUP UDEV (Linux auto-launch):
  sudo cp nova-udev.rules /etc/udev/rules.d/99-nova.rules
  sudo udevadm control --reload-rules
README

  log "Plugin files written to $PLUGIN_DIR"
}


# =============================================================================
# ARCHISO PROFILE — boot mode
# =============================================================================

setup_profile() {
  log "Setting up archiso boot profile..."
  mkdir -p "$PROFILE_DIR"/{airootfs,efiboot}

  cp -r /usr/share/archiso/configs/releng/* "$PROFILE_DIR/" 2>/dev/null || \
    die "archiso not installed. Run: pacman -S archiso"

  cat > "$PROFILE_DIR/packages.x86_64" << 'PKGS'
base
linux
linux-firmware
systemd
systemd-sysvcompat
python
python-pip
python-requests
python-numpy
python-pandas
git
curl
wget
openssh
espeak-ng
ollama
sqlite
net-tools
iproute2
networkmanager
bash-completion
vim
tmux
htop
parted
e2fsprogs
dosfstools
PKGS

  mkdir -p "$PROFILE_DIR/airootfs/etc/systemd/system"
  mkdir -p "$PROFILE_DIR/airootfs/home/nova"

  # Auto-mount nova-data partition on boot
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-data.mount" << 'MOUNT'
[Unit]
Description=N.O.V.A Data Partition
After=local-fs.target

[Mount]
What=LABEL=nova-data
Where=/home/nova/Nova/memory
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
MOUNT

  # Nova mind service
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-mind.service" << 'SVC'
[Unit]
Description=N.O.V.A Mind
After=network.target ollama.service nova-data.mount

[Service]
User=nova
WorkingDirectory=/home/nova/Nova
ExecStartPre=/usr/bin/sleep 10
ExecStart=/usr/bin/python3 /home/nova/Nova/bin/nova_autonomous.py
Restart=always
RestartSec=120

[Install]
WantedBy=multi-user.target
SVC

  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/ollama.service" << 'OLSVC'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
ExecStart=/usr/bin/ollama serve
Restart=always
User=nova

[Install]
WantedBy=multi-user.target
OLSVC

  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-cron.timer" << 'TIMER'
[Unit]
Description=N.O.V.A Autonomous Cycle

[Timer]
OnBootSec=5min
OnUnitActiveSec=2h
Unit=nova-mind.service

[Install]
WantedBy=timers.target
TIMER

  # Auto-login
  mkdir -p "$PROFILE_DIR/airootfs/etc/systemd/system/getty@tty1.service.d"
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/getty@tty1.service.d/override.conf" << 'GETTY'
[Service]
ExecStart=
ExecStart=-/usr/bin/agetty --autologin nova --noclear %I $TERM
GETTY

  cat > "$PROFILE_DIR/airootfs/home/nova/.bash_profile" << 'PROFILE'
if [ "$(tty)" = "/dev/tty1" ]; then
  cd ~/Nova
  echo -e "\033[35mN.O.V.A Boot Mode\033[0m — full OS"
  python3 bin/nova_life.py
fi
PROFILE

  cat > "$PROFILE_DIR/airootfs/home/nova/.bashrc" << 'BASHRC'
export NOVA_HOME=~/Nova
export NOVA_MODEL=gemma2:2b
export PATH="$NOVA_HOME/bin:$PATH"
alias nova="python3 $NOVA_HOME/bin/nova"
PS1='\[\033[35m\]N.O.V.A\[\033[0m\] \[\033[36m\]\w\[\033[0m\] ∴ '
BASHRC

  cat > "$PROFILE_DIR/airootfs/root/customize_airootfs.sh" << 'CUSTOM'
#!/usr/bin/env bash
set -e
useradd -m -s /bin/bash nova
echo "nova:nova" | chpasswd
usermod -aG wheel nova

systemctl enable ollama.service nova-cron.timer sshd.service NetworkManager.service
systemctl enable nova-data.mount

sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
echo "AllowUsers nova" >> /etc/ssh/sshd_config
echo '%wheel ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

mkdir -p /home/nova/Nova/logs
echo '{"version":"usb-boot","mode":"boot"}' > /home/nova/Nova/memory/nova_identity.json
chown -R nova:nova /home/nova/Nova
CUSTOM
  chmod +x "$PROFILE_DIR/airootfs/root/customize_airootfs.sh"
  log "Boot profile ready."
}


# =============================================================================
# ISO build
# =============================================================================

build_iso() {
  log "Building boot ISO (~10-20 min)..."
  mkdir -p "$WORK_DIR" "$(dirname "$ISO_OUT")"
  mkarchiso -v -w "$WORK_DIR" -o "$(dirname "$ISO_OUT")" "$PROFILE_DIR"
  local built
  built="$(find "$(dirname "$ISO_OUT")" -name "*.iso" -newer "$PROFILE_DIR" | head -1)"
  [[ -n "$built" && "$built" != "$ISO_OUT" ]] && mv "$built" "$ISO_OUT"
  log "ISO ready: $ISO_OUT  ($(du -sh "$ISO_OUT" | cut -f1))"
}


# =============================================================================
# Write hybrid USB
# =============================================================================

write_hybrid_usb() {
  local dev="$1"
  [[ -b "$dev" ]] || die "$dev is not a block device"

  warn "This will ERASE $dev. All data will be lost."
  read -r -p "Type 'yes' to confirm: " confirm
  [[ "$confirm" == "yes" ]] || die "Aborted."

  local size_mb
  size_mb=$(blockdev --getsize64 "$dev" | awk '{printf "%d", $1/1024/1024}')
  (( size_mb >= 8192 )) || die "USB must be at least 8GB (is ${size_mb}MB)"

  log "Partitioning $dev (${size_mb}MB)..."

  # Wipe and create GPT
  wipefs -af "$dev"
  parted -s "$dev" mklabel gpt

  # P1: FAT32 — plugin launcher (visible to all OSes) — 256MB
  parted -s "$dev" mkpart primary fat32 1MiB 257MiB
  parted -s "$dev" set 1 esp on
  parted -s "$dev" set 1 boot on

  # P2: ext4 — Nova OS root — 6GB
  parted -s "$dev" mkpart primary ext4 257MiB 6401MiB

  # P3: ext4 — shared persistent data (rest of drive)
  parted -s "$dev" mkpart primary ext4 6401MiB 100%

  sleep 2  # let kernel re-read partition table

  # Detect partition names (nvme uses p1/p2, sd uses 1/2)
  local p1 p2 p3
  if [[ "$dev" =~ nvme|mmcblk ]]; then
    p1="${dev}p1"; p2="${dev}p2"; p3="${dev}p3"
  else
    p1="${dev}1";  p2="${dev}2";  p3="${dev}3"
  fi

  log "Formatting partitions..."
  mkfs.fat  -F32 -n "NOVA"      "$p1"
  mkfs.ext4 -L "nova-os"   -F  "$p2"
  mkfs.ext4 -L "nova-data" -F  "$p3"

  # Write boot ISO to P2
  log "Writing boot OS to P2..."
  [[ -f "$ISO_OUT" ]] || die "ISO not found: $ISO_OUT  (run --iso first)"
  local tmp_mount="/tmp/nova-iso-mount"
  local p2_mount="/tmp/nova-p2-mount"
  mkdir -p "$tmp_mount" "$p2_mount"
  mount -o loop "$ISO_OUT" "$tmp_mount"
  mount "$p2" "$p2_mount"
  rsync -a --info=progress2 "$tmp_mount/" "$p2_mount/"
  umount "$tmp_mount" "$p2_mount"

  # Install GRUB on P2 (for boot mode)
  log "Installing GRUB bootloader..."
  mount "$p2" "$p2_mount"
  grub-install --target=x86_64-efi --efi-directory="$p2_mount/boot/efi" \
    --boot-directory="$p2_mount/boot" --removable "$dev" 2>/dev/null || true
  umount "$p2_mount"

  # Write plugin files to P1
  log "Writing plugin launcher to P1 (visible to all OSes)..."
  local p1_mount="/tmp/nova-p1-mount"
  mkdir -p "$p1_mount"
  mount "$p1" "$p1_mount"
  cp -r "$PLUGIN_DIR"/. "$p1_mount/"
  umount "$p1_mount"

  # Initialize nova-data partition
  log "Initializing nova-data persistent store..."
  local p3_mount="/tmp/nova-p3-mount"
  mkdir -p "$p3_mount"
  mount "$p3" "$p3_mount"
  mkdir -p "$p3_mount"/{dreams,research,markets,security,learning,opencog,quantum,inner}
  echo '{"version":"usb-hybrid","mode":"init","created":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' \
    > "$p3_mount/nova_identity.json"
  umount "$p3_mount"

  sync
  log "Hybrid USB complete on $dev"
  log ""
  log "  Boot mode   : insert USB at power-on → full Nova OS"
  log "  Plugin mode : insert into running OS → auto-launch (or run NOVA/nova_detect.py)"
  log "  Data        : shared nova-data partition (P3) — same memory in both modes"
}


# =============================================================================
# Plugin-only (no ISO, just write plugin FAT32 partition)
# =============================================================================

write_plugin_only() {
  local dev="$1"
  [[ -b "$dev" ]] || die "$dev is not a block device"
  warn "Writing plugin files to $dev P1 (must already be FAT32 labeled NOVA)"
  local p1="${dev}1"
  [[ "$dev" =~ nvme|mmcblk ]] && p1="${dev}p1"
  local mnt="/tmp/nova-p1-mount"
  mkdir -p "$mnt"
  mount "$p1" "$mnt" 2>/dev/null || mount "$dev" "$mnt"
  cp -r "$PLUGIN_DIR"/. "$mnt/"
  umount "$mnt"
  log "Plugin files updated on $dev"
}


# =============================================================================
# Main
# =============================================================================

main() {
  local mode="help"
  local usb_dev=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --usb)         mode="usb";    usb_dev="${2:-}"; shift 2 ;;
      --iso)         mode="iso";    shift ;;
      --plugin-only) mode="plugin"; usb_dev="${2:-}"; shift 2 ;;
      --help)        usage; exit 0 ;;
      *)             die "Unknown option: $1" ;;
    esac
  done

  [[ "$mode" == "help" ]] && { usage; exit 0; }
  [[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0 $*"

  build_plugin_partition

  if [[ "$mode" == "iso" ]]; then
    setup_profile
    build_iso

  elif [[ "$mode" == "usb" ]]; then
    [[ -n "$usb_dev" ]] || die "--usb requires device path (e.g. --usb /dev/sdb)"
    setup_profile
    build_iso
    write_hybrid_usb "$usb_dev"

  elif [[ "$mode" == "plugin" ]]; then
    [[ -n "$usb_dev" ]] || die "--plugin-only requires device path"
    write_plugin_only "$usb_dev"
  fi
}

main "$@"
