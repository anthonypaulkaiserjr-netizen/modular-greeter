#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[!] Please run with sudo: sudo ./deploy.sh"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)"
INSTALL_DIR="/etc/greetd/my-greeter"

echo "==> Detecting distribution & installing dependencies..."
if command -v pacman &>/dev/null; then
    pacman -S --needed --noconfirm greetd cage python-gobject gtk4 python-pillow
elif command -v apt-get &>/dev/null; then
    apt-get update
    apt-get install -y greetd cage python3-gi python3-gi-cairo gir1.2-gtk-4.0 python3-pil
elif command -v dnf &>/dev/null; then
    dnf install -y greetd cage python3-gobject gtk4 python3-pillow
elif command -v zypper &>/dev/null; then
    zypper --non-interactive install greetd cage python3-gobject python3-gobject-Gdk gtk4 python3-Pillow
elif command -v xbps-install &>/dev/null; then
    xbps-install -Sy greetd cage python3-gobject gtk4 python3-Pillow
elif command -v apk &>/dev/null; then
    apk add greetd cage py3-gobject3 gtk4.0 py3-pillow
else
    echo "[!] Unsupported package manager. Manually install: greetd, cage, python-gobject, gtk4, python-pillow"
    exit 1
fi

# Ensure the 'greeter' system user exists (needed on Fedora/Debian/Alpine)
id -u greeter &>/dev/null || useradd -r -M -s /sbin/nologin greeter

echo "==> Deploying greeter files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
SRC_DIR="${SCRIPT_DIR}/release"
for file in greeter.py ansi_bg.py style.css sessions.json; do
    if [[ -f "${SRC_DIR}/${file}" ]]; then
        cp "${SRC_DIR}/${file}" "${INSTALL_DIR}/${file}"
    else
        echo "[!] Missing required file: ${file}"
        exit 1
    fi
done

if [[ -f "${SRC_DIR}/users.json" ]]; then
    cp "${SRC_DIR}/users.json" "${INSTALL_DIR}/users.json"
else
    cat << JSON > "${INSTALL_DIR}/users.json"
{
  "users": ["${REAL_USER}"],
  "bg_mode": "ly",
  "bg_path": "${INSTALL_DIR}/wallpaper.png",
  "block_size": 18
}
JSON
fi

for img in wallpaper.png wallpaper.jpg bg.png bg.jpg; do
    if [[ -f "${SRC_DIR}/${img}" ]]; then
        cp "${SRC_DIR}/${img}" "${INSTALL_DIR}/${img}"
        sed -i "s|\"bg_path\":.*|\"bg_path\": \"${INSTALL_DIR}/${img}\",|" "${INSTALL_DIR}/users.json"
        break
    fi
done

chmod +x "${INSTALL_DIR}/greeter.py"
chown -R root:root "${INSTALL_DIR}"
chmod -R a+rX "${INSTALL_DIR}"

echo "==> Configuring /etc/greetd/config.toml..."
if [[ -f /etc/greetd/config.toml ]]; then
    cp /etc/greetd/config.toml "/etc/greetd/config.toml.bak.$(date +%s)"
fi

cat << TOML > /etc/greetd/config.toml
[terminal]
vt = 1

[default_session]
command = "cage -s -- python3 ${INSTALL_DIR}/greeter.py"
user = "greeter"
TOML

echo "==> Enabling greetd service..."
if command -v systemctl &>/dev/null; then
    for dm in sddm gdm gdm3 lightdm lxdm ly; do
        systemctl disable "${dm}.service" 2>/dev/null || true
    done
    systemctl enable greetd.service
elif [[ -d /etc/sv/greetd ]]; then
    ln -sf /etc/sv/greetd /var/service/
elif command -v rc-update &>/dev/null; then
    rc-update add greetd default
fi

echo ""
echo "[✓] Installation complete!"
echo "    Edit ${INSTALL_DIR}/users.json and ${INSTALL_DIR}/sessions.json to customize."
