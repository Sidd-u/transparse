#!/bin/sh
# transparse installer
# Usage: sh install.sh

set -e

REPO="https://raw.githubusercontent.com/Sidd-u/transparse/main"
INSTALL_DIR="/usr/local/bin"
TOOL_NAME="transparse"

# ─────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { printf "${GREEN}[OK]${NC}    %s\n" "$1"; }
err()  { printf "${RED}[ERROR]${NC} %s\n" "$1"; exit 1; }
info() { printf "${YELLOW}[..]${NC}    %s\n" "$1"; }

# ─────────────────────────────────────────────
# STEP 1 — CHECK / INSTALL PYTHON 3
# ─────────────────────────────────────────────
info "Checking for Python 3..."

if command -v python3 > /dev/null 2>&1; then
    PY_VER=$(python3 --version 2>&1)
    ok "Python 3 found: $PY_VER"
else
    info "Python 3 not found. Attempting to install..."

    # Detect package manager
    if command -v apt-get > /dev/null 2>&1; then
        sudo apt-get update -qq && sudo apt-get install -y python3
    elif command -v dnf > /dev/null 2>&1; then
        sudo dnf install -y python3
    elif command -v yum > /dev/null 2>&1; then
        sudo yum install -y python3
    elif command -v pacman > /dev/null 2>&1; then
        sudo pacman -Sy --noconfirm python
    else
        err "Could not detect package manager. Please install Python 3 manually and re-run."
    fi

    # Verify install succeeded
    if command -v python3 > /dev/null 2>&1; then
        ok "Python 3 installed successfully."
    else
        err "Python 3 installation failed. Please install it manually and re-run."
    fi
fi

# ─────────────────────────────────────────────
# STEP 2 — CHECK INTERNET + DOWNLOAD TOOL
# ─────────────────────────────────────────────
info "Downloading transparse..."

# Try curl first, then wget
if command -v curl > /dev/null 2>&1; then
    curl -fsSL "$REPO/transparse.py" -o /tmp/transparse || err "Download failed. Check your internet connection."
elif command -v wget > /dev/null 2>&1; then
    wget -q "$REPO/transparse.py" -O /tmp/transparse || err "Download failed. Check your internet connection."
else
    err "Neither curl nor wget found. Please install one and re-run."
fi

ok "Download complete."

# ─────────────────────────────────────────────
# STEP 3 — INSTALL TO /usr/local/bin
# ─────────────────────────────────────────────
info "Installing to $INSTALL_DIR/$TOOL_NAME..."

sudo mv /tmp/transparse "$INSTALL_DIR/$TOOL_NAME" || err "Failed to move file to $INSTALL_DIR. Try running with sudo."
sudo chmod +x "$INSTALL_DIR/$TOOL_NAME"           || err "Failed to set execute permission."

ok "Installed to $INSTALL_DIR/$TOOL_NAME"

# ─────────────────────────────────────────────
# STEP 4 — VERIFY
# ─────────────────────────────────────────────
info "Verifying installation..."

if command -v transparse > /dev/null 2>&1; then
    ok "transparse is ready."
else
    err "Installation succeeded but 'transparse' not found in PATH. Try restarting your terminal."
fi

# ─────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────
printf "\n"
printf "${GREEN}transparse installed successfully!${NC}\n"
printf "\n"
printf "Usage:\n"
printf "  transparse /path/to/file.txt\n"
printf "  transparse /path/to/file.txt --lines 50\n"
printf "\n"
printf "Output is saved to your Desktop as: filename_parsed.txt\n"