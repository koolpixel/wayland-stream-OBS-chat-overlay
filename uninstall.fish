#!/usr/bin/env fish
set -l appdir "$HOME/.local/share/stream-chat-overlay"
set -l bindir "$HOME/.local/bin"
set -l desktopfile "$HOME/.local/share/applications/com.koolpixel.StreamChatOverlay.desktop"
set -l icondir "$HOME/.local/share/icons/hicolor"

rm -rf "$appdir"
rm -f "$bindir/stream-chat-overlay"
rm -f "$desktopfile"
for size in 16 22 24 32 48 64 128 256 512
    rm -f "$icondir/"$size"x"$size"/apps/com.koolpixel.StreamChatOverlay.png"
end

if type -q gtk-update-icon-cache
    gtk-update-icon-cache -q "$icondir" >/dev/null 2>&1
end

if type -q update-desktop-database
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1
end

if type -q kbuildsycoca6
    kbuildsycoca6 >/dev/null 2>&1
end

printf "Stream Chat Overlay app files removed.\n"
printf "Settings were kept at: ~/.config/stream-chat-overlay/\n"
printf "To remove settings too, run: rm -rf ~/.config/stream-chat-overlay\n"
