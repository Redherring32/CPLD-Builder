#!/bin/sh
# Install CPLD-Builder for the current user (no root needed):
#   ./install.sh            install / update
#   ./install.sh --remove   uninstall
# Puts the app in ~/.local/opt/CPLD-Builder, a `cpldglue` command in
# ~/.local/bin and a menu entry in ~/.local/share/applications.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPT="$HOME/.local/opt/CPLD-Builder"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

if [ "$1" = "--remove" ]; then
    rm -rf "$OPT" "$BIN/cpldglue" "$BIN/cpld-builder" "$APPS/cpld-builder.desktop" \
           "$ICONS/cpld-builder.png"
    echo "CPLD-Builder removed. (Downloaded tools stay in ~/.local/share/cpldglue.)"
    exit 0
fi

mkdir -p "$OPT" "$BIN" "$APPS" "$ICONS"
rm -rf "$OPT"
cp -r "$HERE" "$OPT"
ln -sf "$OPT/cpldglue" "$BIN/cpldglue"
ln -sf "$OPT/CPLD-Builder" "$BIN/cpld-builder"
cp "$OPT/_internal/icon.png" "$ICONS/cpld-builder.png"
sed "s|@OPT@|$OPT|g" "$OPT/cpld-builder.desktop" > "$APPS/cpld-builder.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
echo "Installed. Start it from your applications menu, or run: cpld-builder"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "(Add $BIN to your PATH to use the commands.)";; esac
