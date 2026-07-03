#!/usr/bin/env python3
"""
Wayland Stream Chat Overlay - layer-shell chat overlay for KDE/Wayland.

Goal:
- Small normal control window for settings.
- Separate read-only overlay window for Kick/Twitch/YouTube/custom chat.
- Overlay window is always above and mouse click-through.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import cairo
from ctypes import CDLL

# Ensure the gtk4-layer-shell library is loaded before GI imports it.
try:
    CDLL("libgtk4-layer-shell.so")
except OSError:
    # GI import below will show the real error if the package is missing.
    pass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk, Gdk, GLib, WebKit  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402


APP_ID = "com.koolpixel.StreamChatOverlay"
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "stream-chat-overlay"
CONFIG_PATH = CONFIG_DIR / "config.json"

VERSION = "0.1.0-alpha"

DEFAULT_CONFIG: Dict[str, Any] = {
    "platform": "Kick",
    "kick_channel": "",
    "twitch_channel": "",
    "youtube_video_id": "",
    "custom_url": "",
    "width": 430,
    "height": 620,
    "corner": "Top Right",
    "horizontal_margin": 30,
    "vertical_margin": 80,
    "nudge_step": 10,
    "opacity": 0.82,
    "auto_start": False,
    "clickthrough": True,
    "hide_composer": False,
}

PLATFORMS = ["Kick", "Twitch", "YouTube", "Custom URL"]
CORNERS = ["Top Right", "Top Left", "Bottom Right", "Bottom Left"]


def load_config() -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
    except Exception as exc:
        print(f"Could not read config: {exc}", file=sys.stderr)
    return config


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def build_chat_url(config: Dict[str, Any]) -> str:
    platform = config.get("platform", "Kick")

    if platform == "Kick":
        channel = str(config.get("kick_channel", "")).strip().lstrip("@")
        if not channel:
            raise ValueError("Fill in your Kick channel name first.")
        return f"https://kick.com/popout/{channel}/chat"

    if platform == "Twitch":
        channel = str(config.get("twitch_channel", "")).strip().lstrip("@")
        if not channel:
            raise ValueError("Fill in your Twitch channel name first.")
        # parent=localhost is enough for local WebKit embed usage.
        return f"https://www.twitch.tv/embed/{channel}/chat?parent=localhost"

    if platform == "YouTube":
        video_id = str(config.get("youtube_video_id", "")).strip()
        if video_id.startswith("http://") or video_id.startswith("https://"):
            return video_id
        if not video_id:
            raise ValueError("Fill in the YouTube live video ID or full popout chat URL first.")
        return f"https://www.youtube.com/live_chat?is_popout=1&v={video_id}"

    custom_url = str(config.get("custom_url", "")).strip()
    if not custom_url:
        raise ValueError("Fill in a custom chat URL first.")
    return custom_url


def rgba_from_text(text: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.parse(text)
    return rgba


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def install_app_css() -> None:
    """GTK-only styling. This does not inject anything into Kick/Twitch/YouTube."""
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        """)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception as exc:
        print(f"Could not load CSS: {exc}", file=sys.stderr)



class OverlayWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: Dict[str, Any], url: str):
        super().__init__(application=app)
        self.config = config
        self.url = url

        width = int(config.get("width", DEFAULT_CONFIG["width"]))
        height = int(config.get("height", DEFAULT_CONFIG["height"]))
        opacity = float(config.get("opacity", DEFAULT_CONFIG["opacity"]))
        self.clickthrough = bool(config.get("clickthrough", DEFAULT_CONFIG["clickthrough"]))
        self.hide_composer = bool(config.get("hide_composer", DEFAULT_CONFIG["hide_composer"]))
        self.width_px = width
        self.height_px = height
        self.corner = str(config.get("corner", DEFAULT_CONFIG["corner"]))
        self.h_margin = int(config.get("horizontal_margin", DEFAULT_CONFIG["horizontal_margin"]))
        self.v_margin = int(config.get("vertical_margin", DEFAULT_CONFIG["vertical_margin"]))
        self._drag_start_h_margin = self.h_margin
        self._drag_start_v_margin = self.v_margin

        self.set_title("Stream Chat Overlay")
        try:
            self.set_icon_name(APP_ID)
        except Exception:
            pass
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(width, height)
        self.set_opacity(max(0.20, min(1.0, opacity)))

        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "stream-chat-overlay")
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self, 0)
        self._apply_anchors()

        # A simple frame lets opacity work even when web pages have dark backgrounds.
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.set_size_request(width, height)

        if not self.clickthrough:
            drag_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            drag_bar.set_size_request(width, 34)
            drag_bar.add_css_class("toolbar")
            drag_bar.set_margin_start(6)
            drag_bar.set_margin_end(6)

            drag_label = Gtk.Label(label="Drag bar, or use nudge buttons")
            drag_label.set_xalign(0)
            drag_label.set_hexpand(True)
            drag_bar.append(drag_label)

            hint_label = Gtk.Label(label="Setup mode")
            hint_label.add_css_class("dim-label")
            drag_bar.append(hint_label)

            gesture = Gtk.GestureDrag.new()
            gesture.connect("drag-begin", self._on_drag_begin)
            gesture.connect("drag-update", self._on_drag_update)
            gesture.connect("drag-end", self._on_drag_end)
            drag_bar.add_controller(gesture)

            frame.append(drag_bar)

        self.webview = WebKit.WebView()
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)

        try:
            self.webview.set_background_color(rgba_from_text("rgba(0,0,0,0)"))
        except Exception:
            pass

        settings = self.webview.get_settings()
        try:
            settings.set_enable_javascript(True)
        except Exception:
            pass

        # Give all usable space to the web page. If hide_composer is enabled,
        # we hide the bottom chat input inside the page using careful JS after load.
        # This avoids the v0.7 black mask / unused block.
        visible_web_height = max(80, height - (34 if not self.clickthrough else 0))
        self.webview.set_size_request(width, visible_web_height)
        frame.append(self.webview)

        self.set_child(frame)
        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.load_uri(url)

        # Apply input mode once the compositor has created the surface.
        self.connect("realize", lambda *_: GLib.timeout_add(250, self.apply_input_mode))

    def _apply_anchors(self) -> None:
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self, edge, False)
            LayerShell.set_margin(self, edge, 0)

        if "Top" in self.corner:
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_margin(self, LayerShell.Edge.TOP, self.v_margin)
        else:
            LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, self.v_margin)

        if "Right" in self.corner:
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, self.h_margin)
        else:
            LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, self.h_margin)

    def _set_overlay_margins(self, h_margin: int, v_margin: int) -> None:
        self.h_margin = clamp_int(h_margin, 0, 5000)
        self.v_margin = clamp_int(v_margin, 0, 5000)

        if "Top" in self.corner:
            LayerShell.set_margin(self, LayerShell.Edge.TOP, self.v_margin)
        else:
            LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, self.v_margin)

        if "Right" in self.corner:
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, self.h_margin)
        else:
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, self.h_margin)

        self.config["horizontal_margin"] = self.h_margin
        self.config["vertical_margin"] = self.v_margin

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, _x: float, _y: float) -> None:
        self._drag_start_h_margin = self.h_margin
        self._drag_start_v_margin = self.v_margin

    def _on_drag_update(self, _gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        # Layer-shell windows are anchored by margins, not normal x/y coordinates.
        # For a right/bottom anchored window, dragging toward that edge reduces the margin.
        if "Right" in self.corner:
            new_h = self._drag_start_h_margin - round(offset_x)
        else:
            new_h = self._drag_start_h_margin + round(offset_x)

        if "Bottom" in self.corner:
            new_v = self._drag_start_v_margin - round(offset_y)
        else:
            new_v = self._drag_start_v_margin + round(offset_y)

        self._set_overlay_margins(new_h, new_v)

        # Do not update the control window on every drag event; on Wayland that can make
        # layer-shell dragging stutter. The controls are updated once at drag-end.

    def _on_drag_end(self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float) -> None:
        app = self.get_application()
        if hasattr(app, "on_overlay_margins_changed"):
            app.on_overlay_margins_changed(self.h_margin, self.v_margin, save=True)


    def _on_load_changed(self, _webview: WebKit.WebView, load_event: WebKit.LoadEvent) -> None:
        # Run after the page is mostly ready, then repeat a few times because Kick/Twitch
        # build chat dynamically after login/cookies.
        if not self.hide_composer:
            return
        try:
            if load_event in (WebKit.LoadEvent.COMMITTED, WebKit.LoadEvent.FINISHED):
                for delay in (500, 1500, 3000, 6000):
                    GLib.timeout_add(delay, self._run_composer_cleanup)
        except Exception:
            pass

    def _run_webview_js(self, script: str) -> None:
        try:
            # WebKitGTK 6
            if hasattr(self.webview, "evaluate_javascript"):
                self.webview.evaluate_javascript(script, -1, None, None, None, None, None)
                return
        except TypeError:
            try:
                self.webview.evaluate_javascript(script, len(script), None, None, None, None, None)
                return
            except Exception:
                pass
        except Exception as exc:
            print(f"Could not evaluate JavaScript: {exc}", file=sys.stderr)
            return

        try:
            # Older WebKitGTK bindings
            if hasattr(self.webview, "run_javascript"):
                self.webview.run_javascript(script, None, None, None)
        except Exception as exc:
            print(f"Could not run JavaScript: {exc}", file=sys.stderr)

    def _run_composer_cleanup(self) -> bool:
        if not self.hide_composer:
            return False

        # Conservative heuristic:
        # - never inspect all div.innerText, because parent chat containers also contain "Send a message".
        # - only target actual input-like elements and small bottom controls.
        # - if the compositor/chat DOM is not identifiable, do nothing instead of hiding chat messages.
        script = r"""
(function () {
  const HIDDEN = 'data-stream-overlay-hidden-safe';
  const vh = window.innerHeight || document.documentElement.clientHeight || 0;
  const vw = window.innerWidth || document.documentElement.clientWidth || 0;

  function textish(el) {
    return ((el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || el.innerText || el.textContent || '') + '').trim();
  }

  function rect(el) {
    try { return el.getBoundingClientRect(); } catch (_) { return null; }
  }

  function isSafeBottomRect(r) {
    if (!r) return false;
    if (r.width < 24 || r.height < 8) return false;
    if (r.height > 120) return false;
    if (r.top < vh - 190) return false;
    if (r.bottom < vh - 120) return false;
    if (r.width > vw * 0.98 && r.height > 90) return false;
    return true;
  }

  function hideOnly(el) {
    if (!el || el === document.body || el === document.documentElement) return false;
    const r = rect(el);
    if (!isSafeBottomRect(r)) return false;
    el.setAttribute(HIDDEN, 'true');
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
    el.style.setProperty('height', '0px', 'important');
    el.style.setProperty('min-height', '0px', 'important');
    el.style.setProperty('max-height', '0px', 'important');
    el.style.setProperty('padding', '0px', 'important');
    el.style.setProperty('margin', '0px', 'important');
    el.style.setProperty('border', '0px', 'important');
    el.style.setProperty('overflow', 'hidden', 'important');
    return true;
  }

  function composerAncestor(el) {
    let best = null;
    let cur = el;
    for (let i = 0; cur && i < 5; i++, cur = cur.parentElement) {
      const r = rect(cur);
      if (!r) continue;
      // hard safety: never select tall parent/chat list/page containers
      if (r.height > 150 || r.top < vh - 220) break;
      if (isSafeBottomRect(r) && r.width >= Math.min(180, vw * 0.35)) best = cur;
    }
    return best || el;
  }

  const styleId = 'stream-overlay-safe-cleanup-style';
  if (!document.getElementById(styleId)) {
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `[${HIDDEN}="true"] { display: none !important; visibility: hidden !important; height: 0 !important; min-height: 0 !important; max-height: 0 !important; padding: 0 !important; margin: 0 !important; border: 0 !important; overflow: hidden !important; }`;
    document.documentElement.appendChild(style);
  }

  // Actual input-like elements only. No generic div scan.
  Array.from(document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]')).forEach(el => {
    const t = textish(el);
    const r = rect(el);
    if (!isSafeBottomRect(r)) return;
    if (/send a message|send message|message/i.test(t) || el.matches('textarea,input,[contenteditable="true"],[role="textbox"]')) {
      hideOnly(composerAncestor(el));
    }
  });

  // Small bottom controls only; hide the button/control itself, not its parents.
  Array.from(document.querySelectorAll('button,[role="button"]')).forEach(el => {
    const t = textish(el);
    const r = rect(el);
    if (!isSafeBottomRect(r)) return;
    if (/^chat$|emoji|emote|settings|send/i.test(t)) hideOnly(el);
  });

  // Small status text like slow mode; hide only the exact small element.
  Array.from(document.querySelectorAll('span,p,small')).forEach(el => {
    const t = textish(el);
    const r = rect(el);
    if (!isSafeBottomRect(r)) return;
    if (/slow mode activated/i.test(t)) hideOnly(el);
  });

  // Reclaim simple bottom padding without changing heights or hiding containers.
  Array.from(document.querySelectorAll('div,main,section')).forEach(el => {
    const r = rect(el);
    if (!r || r.height < 180 || r.top > vh - 160) return;
    const cs = getComputedStyle(el);
    const scrollish = /(auto|scroll)/i.test(cs.overflowY) || el.scrollHeight > el.clientHeight + 20;
    if (!scrollish) return;
    el.style.setProperty('padding-bottom', '0px', 'important');
    el.style.setProperty('margin-bottom', '0px', 'important');
  });
})();
"""
        self._run_webview_js(script)
        return False

    def apply_input_mode(self) -> bool:
        surface = self.get_surface()
        if surface is None:
            return True

        try:
            if self.clickthrough:
                # Empty input region = visible window, but mouse input passes to the game below.
                surface.set_input_region(cairo.Region())
                print("Overlay mode: click-through active")
            else:
                # Full input region = normal clickable setup window.
                rect = cairo.RectangleInt(0, 0, max(1, self.width_px), max(1, self.height_px))
                surface.set_input_region(cairo.Region(rect))
                print("Setup mode: overlay is clickable")
        except Exception as exc:
            print(f"Could not set overlay input mode: {exc}", file=sys.stderr)
        return False


class ControlWindow(Gtk.ApplicationWindow):
    def __init__(self, app: "StreamChatOverlayApp"):
        super().__init__(application=app)
        self.app = app
        self.set_title("Stream Chat Overlay")
        try:
            self.set_icon_name(APP_ID)
        except Exception:
            pass
        self.set_default_size(560, 680)
        self.set_resizable(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(16)
        outer.set_margin_end(16)
        self.set_child(outer)

        title = Gtk.Label()
        title.set_markup(f"<b>Stream Chat Overlay</b> <span foreground=\"gray\">{VERSION}</span>")
        title.set_xalign(0)
        outer.append(title)

        info = Gtk.Label(label="Use clickable setup mode for cookies/login and positioning. Drag the setup bar to move the overlay. Use click-through mode while playing.")
        info.set_wrap(True)
        info.set_xalign(0)
        outer.append(info)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        grid.set_hexpand(True)
        outer.append(grid)

        self.platform = Gtk.ComboBoxText()
        for item in PLATFORMS:
            self.platform.append_text(item)
        self._set_combo_text(self.platform, self.app.config.get("platform", "Kick"), PLATFORMS)
        grid.attach(Gtk.Label(label="Platform", xalign=0), 0, 0, 1, 1)
        grid.attach(self.platform, 1, 0, 1, 1)

        self.kick_channel = Gtk.Entry()
        self.kick_channel.set_text(str(self.app.config.get("kick_channel", "")))
        self.kick_channel.set_placeholder_text("your Kick channel name")
        grid.attach(Gtk.Label(label="Kick channel", xalign=0), 0, 1, 1, 1)
        grid.attach(self.kick_channel, 1, 1, 1, 1)

        self.twitch_channel = Gtk.Entry()
        self.twitch_channel.set_text(str(self.app.config.get("twitch_channel", "")))
        self.twitch_channel.set_placeholder_text("your Twitch channel name")
        grid.attach(Gtk.Label(label="Twitch channel", xalign=0), 0, 2, 1, 1)
        grid.attach(self.twitch_channel, 1, 2, 1, 1)

        self.youtube_video_id = Gtk.Entry()
        self.youtube_video_id.set_text(str(self.app.config.get("youtube_video_id", "")))
        self.youtube_video_id.set_placeholder_text("YouTube video ID or full popout chat URL")
        grid.attach(Gtk.Label(label="YouTube", xalign=0), 0, 3, 1, 1)
        grid.attach(self.youtube_video_id, 1, 3, 1, 1)

        self.custom_url = Gtk.Entry()
        self.custom_url.set_text(str(self.app.config.get("custom_url", "")))
        self.custom_url.set_placeholder_text("https://...")
        grid.attach(Gtk.Label(label="Custom URL", xalign=0), 0, 4, 1, 1)
        grid.attach(self.custom_url, 1, 4, 1, 1)

        self.width = self._spin(int(self.app.config.get("width", 430)), 200, 1200, 10, 0)
        self.height = self._spin(int(self.app.config.get("height", 620)), 200, 1400, 10, 0)
        grid.attach(Gtk.Label(label="Width", xalign=0), 0, 5, 1, 1)
        grid.attach(self.width, 1, 5, 1, 1)
        grid.attach(Gtk.Label(label="Height", xalign=0), 0, 6, 1, 1)
        grid.attach(self.height, 1, 6, 1, 1)

        self.corner = Gtk.ComboBoxText()
        for item in CORNERS:
            self.corner.append_text(item)
        self._set_combo_text(self.corner, self.app.config.get("corner", "Top Right"), CORNERS)
        grid.attach(Gtk.Label(label="Corner", xalign=0), 0, 7, 1, 1)
        grid.attach(self.corner, 1, 7, 1, 1)

        self.horizontal_margin = self._spin(int(self.app.config.get("horizontal_margin", 30)), 0, 800, 5, 0)
        self.vertical_margin = self._spin(int(self.app.config.get("vertical_margin", 80)), 0, 800, 5, 0)
        grid.attach(Gtk.Label(label="Horizontal margin", xalign=0), 0, 8, 1, 1)
        grid.attach(self.horizontal_margin, 1, 8, 1, 1)
        grid.attach(Gtk.Label(label="Vertical margin", xalign=0), 0, 9, 1, 1)
        grid.attach(self.vertical_margin, 1, 9, 1, 1)

        nudge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.nudge_step = self._spin(int(self.app.config.get("nudge_step", 10)), 1, 100, 1, 0)

        nudge_left = Gtk.Button(label="←")
        nudge_left.connect("clicked", lambda *_: self.on_nudge_clicked(-int(self.nudge_step.get_value()), 0))
        nudge_up = Gtk.Button(label="↑")
        nudge_up.connect("clicked", lambda *_: self.on_nudge_clicked(0, -int(self.nudge_step.get_value())))
        nudge_down = Gtk.Button(label="↓")
        nudge_down.connect("clicked", lambda *_: self.on_nudge_clicked(0, int(self.nudge_step.get_value())))
        nudge_right = Gtk.Button(label="→")
        nudge_right.connect("clicked", lambda *_: self.on_nudge_clicked(int(self.nudge_step.get_value()), 0))
        snap_btn = Gtk.Button(label="Snap to corner")
        snap_btn.connect("clicked", self.on_snap_clicked)

        nudge_box.append(nudge_left)
        nudge_box.append(nudge_up)
        nudge_box.append(nudge_down)
        nudge_box.append(nudge_right)
        nudge_box.append(Gtk.Label(label="Step"))
        nudge_box.append(self.nudge_step)
        nudge_box.append(snap_btn)
        grid.attach(Gtk.Label(label="Position", xalign=0), 0, 10, 1, 1)
        grid.attach(nudge_box, 1, 10, 1, 1)

        self.opacity = self._spin(float(self.app.config.get("opacity", 0.82)), 0.20, 1.00, 0.05, 2)
        grid.attach(Gtk.Label(label="Opacity", xalign=0), 0, 11, 1, 1)
        grid.attach(self.opacity, 1, 11, 1, 1)

        self.clickthrough = Gtk.CheckButton(label="Click-through mode while playing")
        self.clickthrough.set_active(bool(self.app.config.get("clickthrough", True)))
        grid.attach(self.clickthrough, 1, 12, 1, 1)

        self.hide_composer = Gtk.CheckButton(label="Hide message input safely (experimental)")
        self.hide_composer.set_active(bool(self.app.config.get("hide_composer", False)))
        grid.attach(self.hide_composer, 1, 13, 1, 1)

        self.auto_start = Gtk.CheckButton(label="Start overlay automatically when this app opens")
        self.auto_start.set_active(bool(self.app.config.get("auto_start", False)))
        grid.attach(self.auto_start, 1, 14, 1, 1)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.append(button_box)

        setup_btn = Gtk.Button(label="Start CLICKABLE Setup")
        setup_btn.connect("clicked", self.on_start_setup_clicked)
        button_box.append(setup_btn)

        overlay_btn = Gtk.Button(label="Start CLICK-THROUGH Overlay")
        overlay_btn.connect("clicked", self.on_start_overlay_clicked)
        button_box.append(overlay_btn)

        stop_btn = Gtk.Button(label="Stop Overlay")
        stop_btn.connect("clicked", self.on_stop_clicked)
        button_box.append(stop_btn)

        save_btn = Gtk.Button(label="Save Settings")
        save_btn.connect("clicked", self.on_save_clicked)
        button_box.append(save_btn)

        self.status = Gtk.Label(label="Ready.")
        self.status.set_wrap(True)
        self.status.set_xalign(0)
        outer.append(self.status)

        note = Gtk.Label(label="Setup flow: Start CLICKABLE Setup → accept cookies/login → position with nudge buttons → enable input hiding if needed → Start CLICK-THROUGH Overlay → play.")
        note.set_wrap(True)
        note.set_xalign(0)
        outer.append(note)

    @staticmethod
    def _spin(value: float, low: float, high: float, step: float, digits: int) -> Gtk.SpinButton:
        adj = Gtk.Adjustment(value=value, lower=low, upper=high, step_increment=step, page_increment=step * 5)
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=digits)
        spin.set_hexpand(True)
        return spin

    @staticmethod
    def _set_combo_text(combo: Gtk.ComboBoxText, value: str, options: list[str]) -> None:
        try:
            combo.set_active(options.index(value))
        except ValueError:
            combo.set_active(0)

    def collect_config(self) -> Dict[str, Any]:
        config = dict(self.app.config)
        config.update(
            {
                "platform": self.platform.get_active_text() or "Kick",
                "kick_channel": self.kick_channel.get_text().strip(),
                "twitch_channel": self.twitch_channel.get_text().strip(),
                "youtube_video_id": self.youtube_video_id.get_text().strip(),
                "custom_url": self.custom_url.get_text().strip(),
                "width": int(self.width.get_value()),
                "height": int(self.height.get_value()),
                "corner": self.corner.get_active_text() or "Top Right",
                "horizontal_margin": int(self.horizontal_margin.get_value()),
                "vertical_margin": int(self.vertical_margin.get_value()),
                "opacity": float(self.opacity.get_value()),
                "nudge_step": int(self.nudge_step.get_value()),
                "clickthrough": bool(self.clickthrough.get_active()),
                "hide_composer": bool(self.hide_composer.get_active()),
                "auto_start": bool(self.auto_start.get_active()),
            }
        )
        return config

    def set_margin_controls(self, h_margin: int, v_margin: int) -> None:
        self.horizontal_margin.set_value(h_margin)
        self.vertical_margin.set_value(v_margin)
        self.status.set_text(f"Overlay position saved: horizontal margin {h_margin}, vertical margin {v_margin}.")

    def on_nudge_clicked(self, dx: int, dy: int) -> None:
        # Save current form fields first so corner/size settings are respected.
        self.app.config = self.collect_config()
        self.app.move_overlay_visual(dx, dy)

    def on_snap_clicked(self, _button: Gtk.Button) -> None:
        self.app.config = self.collect_config()
        self.app.set_overlay_margins(0, 0, save=True)

    def on_save_clicked(self, _button: Gtk.Button) -> None:
        self.app.config = self.collect_config()
        save_config(self.app.config)
        self.status.set_text(f"Saved settings to {CONFIG_PATH}")

    def _start_with_mode(self, clickthrough: bool) -> None:
        self.app.config = self.collect_config()
        self.app.config["clickthrough"] = clickthrough
        self.clickthrough.set_active(clickthrough)
        save_config(self.app.config)
        try:
            url = build_chat_url(self.app.config)
            self.app.start_overlay(self.app.config, url)
            if clickthrough:
                self.status.set_text("Overlay running in CLICK-THROUGH mode. Use this while playing.")
            else:
                self.status.set_text("Overlay running in CLICKABLE setup mode. Use this for cookies/login, then switch to click-through.")
        except Exception as exc:
            self.status.set_text(str(exc))

    def on_start_setup_clicked(self, _button: Gtk.Button) -> None:
        self._start_with_mode(False)

    def on_start_overlay_clicked(self, _button: Gtk.Button) -> None:
        self._start_with_mode(True)

    def on_stop_clicked(self, _button: Gtk.Button) -> None:
        self.app.stop_overlay()
        self.status.set_text("Overlay stopped.")


class StreamChatOverlayApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.config = load_config()
        self.control_window: ControlWindow | None = None
        self.overlay_window: OverlayWindow | None = None

    def do_activate(self):
        install_app_css()
        if self.control_window is None:
            self.control_window = ControlWindow(self)
            self.control_window.connect("close-request", self._on_control_close)
        self.control_window.present()

        if bool(self.config.get("auto_start", False)) and self.overlay_window is None:
            try:
                self.start_overlay(self.config, build_chat_url(self.config))
            except Exception as exc:
                print(exc, file=sys.stderr)

    def _on_control_close(self, *_args) -> bool:
        self.stop_overlay()
        return False

    def on_overlay_margins_changed(self, h_margin: int, v_margin: int, save: bool = False) -> None:
        self.config["horizontal_margin"] = h_margin
        self.config["vertical_margin"] = v_margin
        if self.control_window is not None:
            self.control_window.set_margin_controls(h_margin, v_margin)
        if save:
            save_config(self.config)

    def set_overlay_margins(self, h_margin: int, v_margin: int, save: bool = True) -> None:
        h_margin = clamp_int(h_margin, 0, 5000)
        v_margin = clamp_int(v_margin, 0, 5000)
        self.config["horizontal_margin"] = h_margin
        self.config["vertical_margin"] = v_margin
        if self.overlay_window is not None:
            self.overlay_window._set_overlay_margins(h_margin, v_margin)
        if self.control_window is not None:
            self.control_window.set_margin_controls(h_margin, v_margin)
        if save:
            save_config(self.config)

    def move_overlay_visual(self, dx: int, dy: int) -> None:
        # dx/dy are visual screen directions: +x = right, +y = down.
        corner = str(self.config.get("corner", DEFAULT_CONFIG["corner"]))
        h_margin = int(self.config.get("horizontal_margin", DEFAULT_CONFIG["horizontal_margin"]))
        v_margin = int(self.config.get("vertical_margin", DEFAULT_CONFIG["vertical_margin"]))

        if "Right" in corner:
            h_margin -= dx
        else:
            h_margin += dx

        if "Bottom" in corner:
            v_margin -= dy
        else:
            v_margin += dy

        self.set_overlay_margins(h_margin, v_margin, save=True)

    def start_overlay(self, config: Dict[str, Any], url: str) -> None:
        self.stop_overlay()
        self.overlay_window = OverlayWindow(self, config, url)
        self.overlay_window.present()

    def stop_overlay(self) -> None:
        if self.overlay_window is not None:
            self.overlay_window.destroy()
            self.overlay_window = None


def main() -> int:
    # This app is meant for Wayland. It may open on X11, but layer-shell is Wayland-specific.
    try:
        Gtk.Window.set_default_icon_name(APP_ID)
    except Exception:
        pass
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type and session_type.lower() != "wayland":
        print(f"Warning: XDG_SESSION_TYPE={session_type}. This app is designed for Wayland.", file=sys.stderr)

    app = StreamChatOverlayApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
