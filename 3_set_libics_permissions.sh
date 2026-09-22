#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_SRC="${LIBICSNEO_RULES_SRC:-${SCRIPT_DIR}/../libicsneo/99-intrepidcs.rules}"
RULES_DEST="/etc/udev/rules.d/99-intrepidcs.rules"

if [[ ! -f "$RULES_SRC" ]]; then
    echo "Rules file not found at $RULES_SRC"
    echo "Set LIBICSNEO_RULES_SRC to the path of libicsneo's 99-intrepidcs.rules, or clone"
    echo "https://github.com/intrepidcs/libicsneo next to this project."
    exit 1
fi

echo "Installing Intrepid udev rules from $RULES_SRC to $RULES_DEST..."
sudo cp "$RULES_SRC" "$RULES_DEST"

echo "Reloading udev rules..."
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Done. Plug in the device (or unplug/replug it) and verify with:"
echo "  ls -la /dev/ttyACM0"
echo "It should show group 'users' with mode 0666 (crw-rw-rw-)."
