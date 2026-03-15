#!/usr/bin/env bash
# =============================================================================
# N.O.V.A USB OS Builder
# =============================================================================
# Builds a bootable USB drive running Nova on Arch Linux + Athena OS.
# Nova auto-starts on boot. Persistent storage on the USB itself.
#
# Requirements:
#   - archiso installed (pacman -S archiso)
#   - A USB drive (at least 8GB recommended)
#   - Root privileges (or sudo)
#
# Usage:
#   sudo bash tools/os/build_usb.sh --usb /dev/sdX
#   sudo bash tools/os/build_usb.sh --iso          # build ISO only
#   sudo bash tools/os/build_usb.sh --help
# =============================================================================

set -euo pipefail

NOVA_HOME="$HOME/Nova"
BUILD_DIR="/tmp/nova-archiso"
WORK_DIR="/tmp/nova-archiso-work"
ISO_NAME="nova-os-$(date +%Y%m%d).iso"
ISO_OUT="$NOVA_HOME/tools/os/${ISO_NAME}"
PROFILE_DIR="$NOVA_HOME/tools/os/archiso-profile"

NC='\033[0m'
G='\033[32m'
R='\033[31m'
Y='\033[33m'
B='\033[1m'

log() { echo -e "${G}[nova-usb]${NC} $*"; }
warn() { echo -e "${Y}[warn]${NC} $*"; }
die() { echo -e "${R}[error]${NC} $*"; exit 1; }

usage() {
  cat <<EOF
${B}N.O.V.A USB OS Builder${NC}

Usage: sudo bash tools/os/build_usb.sh [OPTIONS]

Options:
  --usb /dev/sdX    Write ISO to USB drive (destructive!)
  --iso             Build ISO only (don't write to USB)
  --help            Show this help

The ISO includes:
  - Arch Linux (base) + Athena OS security tools
  - Python 3.12, Ollama (auto-start), espeak-ng
  - N.O.V.A pre-installed and configured for auto-start
  - Persistent /home/nova volume on the USB (survives reboots)
  - Auto-login as 'nova' user → runs nova_life.py on TTY1
  - SSH server enabled for remote access (key-only)

EOF
}

setup_profile() {
  log "Setting up archiso profile..."
  mkdir -p "$PROFILE_DIR"/{airootfs,efiboot}

  # Base profile
  cp -r /usr/share/archiso/configs/releng/* "$PROFILE_DIR/" 2>/dev/null || \
    die "archiso not installed. Run: pacman -S archiso"

  # Packages
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
PKGS

  # Airootfs overlays
  mkdir -p "$PROFILE_DIR/airootfs/etc/systemd/system"
  mkdir -p "$PROFILE_DIR/airootfs/home/nova"
  mkdir -p "$PROFILE_DIR/airootfs/etc/skel"

  # Nova auto-start systemd service
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-mind.service" << 'SVC'
[Unit]
Description=N.O.V.A Mind — Autonomous AI Presence
After=network.target ollama.service
Wants=ollama.service

[Service]
User=nova
WorkingDirectory=/home/nova/Nova
ExecStartPre=/usr/bin/sleep 10
ExecStart=/usr/bin/python3 /home/nova/Nova/bin/nova_autonomous.py
Restart=always
RestartSec=120
StandardOutput=append:/home/nova/Nova/logs/boot.log
StandardError=append:/home/nova/Nova/logs/boot.log

[Install]
WantedBy=multi-user.target
SVC

  # Cron: nova autonomous every 2 hours
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-cron.timer" << 'TIMER'
[Unit]
Description=N.O.V.A Autonomous Cycle Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=2h
Unit=nova-mind.service

[Install]
WantedBy=timers.target
TIMER

  # Ollama auto-start
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/ollama.service" << 'OLSVC'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
ExecStart=/usr/bin/ollama serve
Restart=always
RestartSec=5
User=nova
Environment=OLLAMA_HOST=127.0.0.1:11434

[Install]
WantedBy=multi-user.target
OLSVC

  # Auto-login on TTY1
  mkdir -p "$PROFILE_DIR/airootfs/etc/systemd/system/getty@tty1.service.d"
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/getty@tty1.service.d/override.conf" << 'GETTY'
[Service]
ExecStart=
ExecStart=-/usr/bin/agetty --autologin nova --noclear %I $TERM
GETTY

  # .bash_profile for nova — start nova_life on login
  cat > "$PROFILE_DIR/airootfs/home/nova/.bash_profile" << 'PROFILE'
# N.O.V.A auto-start on TTY1
if [ "$(tty)" = "/dev/tty1" ]; then
  cd ~/Nova
  python3 bin/nova_life.py
fi
PROFILE

  # Profile customizations
  cat > "$PROFILE_DIR/airootfs/home/nova/.bashrc" << 'BASHRC'
# N.O.V.A environment
export NOVA_HOME=~/Nova
export NOVA_MODEL=gemma2:2b
export PATH="$NOVA_HOME/bin:$PATH"
alias nova="python3 $NOVA_HOME/bin/nova"
PS1='\[\033[35m\]N.O.V.A\[\033[0m\] \[\033[36m\]\w\[\033[0m\] ∴ '
BASHRC

  # Setup script (runs on first boot)
  cat > "$PROFILE_DIR/airootfs/etc/systemd/system/nova-setup.service" << 'SETUP'
[Unit]
Description=N.O.V.A First Boot Setup
ConditionPathExists=!/home/nova/.nova_setup_done
After=network-online.target

[Service]
Type=oneshot
User=nova
ExecStart=/home/nova/Nova/tools/os/first_boot.sh
ExecStartPost=/usr/bin/touch /home/nova/.nova_setup_done
StandardOutput=journal

[Install]
WantedBy=multi-user.target
SETUP

  # Customize: enable services, create nova user
  cat > "$PROFILE_DIR/airootfs/root/customize_airootfs.sh" << 'CUSTOM'
#!/usr/bin/env bash
set -e
# Create nova user
useradd -m -s /bin/bash nova
echo "nova:nova" | chpasswd
usermod -aG wheel nova

# Enable services
systemctl enable ollama.service
systemctl enable nova-setup.service
systemctl enable nova-cron.timer
systemctl enable sshd.service
systemctl enable NetworkManager.service

# SSH hardening
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
echo "AllowUsers nova" >> /etc/ssh/sshd_config

# Sudoers
echo '%wheel ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

# Clone Nova (or placeholder)
mkdir -p /home/nova/Nova/logs
echo '{"version":"usb-boot","auto":"true"}' > /home/nova/Nova/memory/nova_identity.json
chown -R nova:nova /home/nova/Nova
CUSTOM
  chmod +x "$PROFILE_DIR/airootfs/root/customize_airootfs.sh"

  log "Profile ready at $PROFILE_DIR"
}


write_first_boot() {
  cat > "$NOVA_HOME/tools/os/first_boot.sh" << 'FIRSTBOOT'
#!/usr/bin/env bash
# Runs once on first boot after network is available
set -e
cd ~/Nova

# Install Python dependencies
pip install --user requests yfinance pandas numpy mastodon.py --quiet

# Pull Ollama model
ollama pull gemma2:2b --quiet || echo "Model pull failed — retry manually"

# Build integrity baseline
python3 tools/governance/file_integrity.py baseline || true

# Seed AtomSpace knowledge
python3 tools/opencog/pln.py seed-security || true
python3 tools/opencog/pln.py seed-markets  || true

echo "[nova] First boot setup complete."
FIRSTBOOT
  chmod +x "$NOVA_HOME/tools/os/first_boot.sh"
  log "First boot script written."
}


build_iso() {
  log "Building ISO (this takes ~10-20 minutes)..."
  mkdir -p "$WORK_DIR" "$(dirname "$ISO_OUT")"

  mkarchiso \
    -v \
    -w "$WORK_DIR" \
    -o "$(dirname "$ISO_OUT")" \
    "$PROFILE_DIR"

  # Find and rename the ISO
  local built_iso
  built_iso="$(find "$(dirname "$ISO_OUT")" -name "*.iso" -newer "$PROFILE_DIR" | head -1)"
  if [[ -n "$built_iso" && "$built_iso" != "$ISO_OUT" ]]; then
    mv "$built_iso" "$ISO_OUT"
  fi

  log "ISO built: $ISO_OUT  ($(du -sh "$ISO_OUT" | cut -f1))"
}


write_usb() {
  local dev="$1"
  [[ -b "$dev" ]] || die "$dev is not a block device"

  warn "This will ERASE $dev. All data will be lost."
  read -r -p "Type 'yes' to confirm: " confirm
  [[ "$confirm" == "yes" ]] || die "Aborted."

  log "Writing ISO to $dev..."
  dd if="$ISO_OUT" of="$dev" bs=4M status=progress oflag=sync
  sync

  # Create persistent partition (last ~2GB of drive)
  log "Creating persistent partition for Nova memory..."
  local size_mb
  size_mb=$(blockdev --getsize64 "$dev" | awk '{printf "%d", $1/1024/1024}')
  local iso_mb
  iso_mb=$(du -m "$ISO_OUT" | cut -f1)
  local persist_start=$(( iso_mb + 100 ))
  local persist_end=$(( size_mb - 10 ))

  if (( persist_end > persist_start )); then
    parted -s "$dev" mkpart primary ext4 "${persist_start}MiB" "${persist_end}MiB" 2>/dev/null || true
    local part_num
    part_num=$(parted -s "$dev" print | awk '/ext4/{print $1}' | tail -1)
    if [[ -n "$part_num" ]]; then
      mkfs.ext4 -L "nova-memory" "${dev}${part_num}" -q || true
      log "Persistent partition: ${dev}${part_num} (nova-memory)"
    fi
  fi

  log "USB build complete. Boot from $dev to start N.O.V.A"
}


main() {
  local mode="help"
  local usb_dev=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --usb)   mode="usb"; usb_dev="${2:-}"; shift 2 ;;
      --iso)   mode="iso"; shift ;;
      --help)  usage; exit 0 ;;
      *)       die "Unknown option: $1" ;;
    esac
  done

  [[ "$mode" == "help" ]] && { usage; exit 0; }

  [[ $EUID -eq 0 ]] || die "This script must run as root (sudo)"

  setup_profile
  write_first_boot
  build_iso

  if [[ "$mode" == "usb" ]]; then
    [[ -n "$usb_dev" ]] || die "--usb requires a device path (e.g. --usb /dev/sdb)"
    write_usb "$usb_dev"
  fi
}

main "$@"
