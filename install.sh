#!/bin/bash

echo "This script will install Warden on your system in ${WARDEN_INSTALL_DIR:-/opt/warden} (/opt/warden by default). Please ensure you have the necessary permissions to write to this directory."

INSTALL_DIR="${WARDEN_INSTALL_DIR:-/opt/warden}"
# Create the installation directory if it doesn't exist
if ! mkdir -p "$INSTALL_DIR" 2>/dev/null; then
    echo "Error: Cannot create directory $INSTALL_DIR. Please run this script with sudo or as root."
    exit 1
fi

# Check if the repository already exists
if [ -d "$INSTALL_DIR/.git" ]; then
    # Update the existing repository
    cd "$INSTALL_DIR"
    git pull
else
    # Clone the repository
    git clone https://github.com/pasqal-io/warden "$INSTALL_DIR"
fi

# Change to the cloned directory
cd "$INSTALL_DIR"

# Wait for user input
echo "Open ${INSTALL_DIR}/config.mk to review the configuration before installation."
read -p "Press Enter to continue with installation..."

# Run make install
make install
