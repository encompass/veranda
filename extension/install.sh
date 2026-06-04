#!/usr/bin/env bash
# Install the Veranda GNOME Shell extension for the current user.
set -euo pipefail

UUID="veranda@encompass.gmail.com"
SRC="$(cd "$(dirname "$0")" && pwd)/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DEST"
cp -r "$SRC/." "$DEST/"
echo "Installed Veranda extension to: $DEST"

if command -v gnome-extensions >/dev/null; then
    gnome-extensions enable "$UUID" 2>/dev/null && echo "Enabled $UUID" || \
        echo "Enable it with: gnome-extensions enable $UUID"
fi

echo
echo "On Wayland, a newly added extension needs a fresh session: log out and"
echo "back in, then ensure it is enabled. The Veranda app must be running for"
echo "the Quick Settings entry to do anything."
