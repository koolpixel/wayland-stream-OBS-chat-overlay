#!/usr/bin/env fish
set -l appdir "$HOME/.local/share/stream-chat-overlay"
set -l bindir "$HOME/.local/bin"
set -l desktopdir "$HOME/.local/share/applications"
set -l icondir "$HOME/.local/share/icons/hicolor"

printf "Installing system dependencies with pacman...\n"
sudo pacman -S --needed python python-gobject python-cairo gtk4 gtk4-layer-shell webkitgtk-6.0

mkdir -p "$appdir" "$bindir" "$desktopdir"
cp stream_chat_overlay.py "$appdir/stream_chat_overlay.py"
chmod +x "$appdir/stream_chat_overlay.py"

mkdir -p "$icondir/16x16/apps" "$icondir/22x22/apps" "$icondir/24x24/apps" "$icondir/32x32/apps" "$icondir/48x48/apps" "$icondir/64x64/apps" "$icondir/128x128/apps" "$icondir/256x256/apps" "$icondir/512x512/apps"
for size in 16 22 24 32 48 64 128 256 512
    cp "assets/icons/com.koolpixel.StreamChatOverlay-$size.png" "$icondir/"$size"x"$size"/apps/com.koolpixel.StreamChatOverlay.png"
end

printf '%s\n' '#!/usr/bin/env fish' \
'set -x GDK_BACKEND wayland' \
'exec python3 "$HOME/.local/share/stream-chat-overlay/stream_chat_overlay.py"' \
> "$bindir/stream-chat-overlay"
chmod +x "$bindir/stream-chat-overlay"

cp packaging/com.koolpixel.StreamChatOverlay.desktop "$desktopdir/com.koolpixel.StreamChatOverlay.desktop"

if type -q gtk-update-icon-cache
    gtk-update-icon-cache -q "$icondir" >/dev/null 2>&1
end

if type -q update-desktop-database
    update-desktop-database "$desktopdir" >/dev/null 2>&1
end

if type -q kbuildsycoca6
    kbuildsycoca6 >/dev/null 2>&1
end

printf "\nDone. Open it from KDE app launcher: Stream Chat Overlay\n"
printf "Or run: stream-chat-overlay\n"
