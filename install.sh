#!/bin/bash

DEFAULT_INSTALL_DIR="/opt/warden"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    COLOR_BOLD=$'\033[1m'
    COLOR_BLUE=$'\033[1;34m'
    COLOR_YELLOW=$'\033[1;33m'
    COLOR_RED=$'\033[1;31m'
    COLOR_GREEN=$'\033[1;32m'
    COLOR_RESET=$'\033[0m'
else
    COLOR_BOLD=""
    COLOR_BLUE=""
    COLOR_YELLOW=""
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_RESET=""
fi

info() {
    printf "%b\n" "${COLOR_BLUE}$*${COLOR_RESET}"
}

warn() {
    printf "%b\n" "${COLOR_YELLOW}$*${COLOR_RESET}"
}

error() {
    printf "%b\n" "${COLOR_RED}$*${COLOR_RESET}" >&2
}

success() {
    printf "%b\n" "${COLOR_GREEN}$*${COLOR_RESET}"
}

resolve_python_command() {
    make -s -f - print-python <<'EOF'
include config.mk
print-python:
	@printf '%s' "$(PYTHON)"
EOF
}

validate_python_config() {
    local python_value python_version
    local -a python_cmd

    python_value="$(resolve_python_command)"
    if [[ -z "$python_value" ]]; then
        error "Error: config.mk does not define a usable PYTHON value."
        return 1
    fi

    read -r -a python_cmd <<< "$python_value"
    if ! python_version="$("${python_cmd[@]}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"; then
        error "Error: PYTHON in config.mk is set to '$python_value', but that interpreter could not be executed."
        return 1
    fi

    case "$python_version" in
        3.11|3.12)
            success "Detected supported Python $python_version from PYTHON=$python_value."
            return 0
            ;;
        *)
            error "Error: PYTHON in config.mk resolves to Python $python_version. Please use Python 3.11 or 3.12."
            return 1
            ;;
    esac
}

printf "%b\n" "${COLOR_BOLD}This script will install Warden on your system.${COLOR_RESET}"
warn "Please ensure you have the necessary permissions to write to the installation directory."
read -r -p "Installation directory [${WARDEN_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}]: " USER_INSTALL_DIR < /dev/tty
INSTALL_DIR="${USER_INSTALL_DIR:-${WARDEN_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}}"

# Create the installation directory if it doesn't exist
if ! mkdir -p "$INSTALL_DIR" 2>/dev/null; then
    error "Error: Cannot create directory $INSTALL_DIR. Please run this script with sudo or as root."
    exit 1
fi

# Check if the repository already exists
if [ -d "$INSTALL_DIR/.git" ]; then
    # Update the existing repository
    info "Updating existing checkout in $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull
else
    # Clone the repository
    info "Cloning Warden into $INSTALL_DIR..."
    git clone https://github.com/pasqal-io/warden "$INSTALL_DIR"
fi

# Change to the cloned directory
cd "$INSTALL_DIR"

git checkout an/test-install

# Wait for user input
while true; do
    warn "Open ${INSTALL_DIR}/config.mk to review the configuration before proceeding with installation."
    warn "PYTHON must point to Python 3.11 or 3.12."
    read -r -p "Press Enter to validate the configuration..." < /dev/tty

    if validate_python_config; then
        break
    fi
done

# Run make install
info "Running installation..."
make install

success "Installation complete! You can now:"
printf "%b\n" "1. Configure the Warden installation by editing the ${COLOR_BOLD}${INSTALL_DIR}/config.yaml${COLOR_RESET}"
printf "%b\n" "2. Run ${COLOR_BOLD}cd ${INSTALL_DIR} && make run${COLOR_RESET} to start Warden."
printf "%b\n" "3. Check the full configuration guide in the README at https://github.com/pasqal-io/warden"
