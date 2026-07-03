# Wayland Stream Chat Overlay

A simple click-through chat overlay for single-monitor streamers on KDE/Wayland. Built and tested on CachyOS.

It creates a small always-on-top Wayland overlay for Kick, Twitch, YouTube, or a custom chat URL. Use clickable setup mode for cookies/login/positioning, then switch to click-through overlay mode while playing so the game keeps mouse control.

![App icon](assets/icon.png)

## Features

- Kick, Twitch, YouTube, and custom chat URL presets.
- Clickable setup mode.
- Click-through read-only overlay mode.
- Top-left, top-right, bottom-left, and bottom-right placement.
- Position nudge buttons for Wayland-friendly placement.
- Opacity control.
- Experimental safe hiding of the message input area.
- Fish-friendly installer for CachyOS / Arch-based systems.

## Tested on

- CachyOS
- KDE Plasma
- Wayland session

Other wlroots/KDE/GNOME Wayland setups may work, but are not the main target yet.

## Install

```fish
git clone https://github.com/YOURNAME/wayland-stream-chat-overlay.git
cd wayland-stream-chat-overlay
fish install.fish
```

The installer installs these Arch/CachyOS packages if needed:

```text
python python-gobject python-cairo gtk4 gtk4-layer-shell webkitgtk-6.0
```

Then start it from the KDE launcher:

```text
Stream Chat Overlay
```

Or run:

```fish
stream-chat-overlay
```

## Basic workflow

1. Open **Stream Chat Overlay**.
2. Choose **Kick**, **Twitch**, **YouTube**, or **Custom URL**.
3. Enter your channel name or chat URL.
4. Click **Start CLICKABLE Setup**.
5. Accept cookies / login / position the overlay.
6. Click **Start CLICK-THROUGH Overlay**.
7. Start your game and read chat while mouse input passes through to the game.

## Uninstall

```fish
fish uninstall.fish
```

This removes the installed app files and launcher. It keeps your settings at:

```text
~/.config/stream-chat-overlay/
```

Remove settings manually if desired:

```fish
rm -rf ~/.config/stream-chat-overlay
```

## Notes and limitations

- This is an alpha release.
- It is designed for Wayland layer-shell, especially KDE Plasma Wayland.
- The message input hiding option is experimental because Kick/Twitch/YouTube can change their page structure.
- Use borderless/windowed fullscreen games when possible.
- Display capture in OBS may capture the overlay. Use game/window capture if you want the overlay visible only to you.

## License

MIT
