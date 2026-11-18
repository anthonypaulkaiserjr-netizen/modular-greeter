#!/usr/bin/env python3
import json, os, socket, struct, subprocess, sys
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk
from ansi_bg import AnsiCanvas

BASE = Path(__file__).resolve().parent


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


class GreetdClient:
    def __init__(self):
        path = os.environ.get("GREETD_SOCK")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) if path else None
        if self.sock:
            self.sock.connect(path)

    def send(self, payload, wait_reply=True):
        if not self.sock:
            return {"type": "test"}
        raw = json.dumps(payload).encode("utf-8")
        self.sock.sendall(struct.pack("=I", len(raw)) + raw)
        if not wait_reply:
            return {"type": "sent"}
        length, = struct.unpack("=I", self.sock.recv(4))
        return json.loads(self.sock.recv(length).decode("utf-8"))


class GreeterWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Modular Greeter")
        self.fullscreen()

        ucfg = load_json(BASE / "users.json", {"users": ["user"], "bg_mode": "ly", "bg_path": "", "block_size": 18})
        scfg = load_json(BASE / "sessions.json", {"sessions": [{"name": "TTY", "cmd": ["bash", "-l"]}]})

        self.users = ucfg.get("users", ["user"])
        self.sessions = scfg.get("sessions", [{"name": "TTY", "cmd": ["bash", "-l"]}])
        self.bg_mode = ucfg.get("bg_mode", "ly")
        self.bg_path = ucfg.get("bg_path", "")
        self.u_idx = self.s_idx = 0
        self.confirm_action = None
        self.client = GreetdClient()

        overlay = Gtk.Overlay()
        self.set_child(overlay)

        pic = Gtk.Picture()
        pic.set_content_fit(Gtk.ContentFit.COVER)
        if self.bg_path and os.path.exists(self.bg_path):
            pic.set_filename(self.bg_path)

        self.stack = Gtk.Stack()
        self.stack.add_named(pic, "image")
        self.stack.add_named(AnsiCanvas(self.bg_path, ucfg.get("block_size", 18)), "ly")
        self.stack.set_visible_child_name(self.bg_mode)
        overlay.set_child(self.stack)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("login-card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(card)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title = Gtk.Label(label="ARCH LINUX", hexpand=True, halign=Gtk.Align.START)
        title.add_css_class("title-label")
        self.mode_btn = Gtk.Button(label=f"[BG: {self.bg_mode.upper()}]")
        self.mode_btn.add_css_class("cycle-btn")
        self.mode_btn.connect("clicked", self.toggle_bg)
        top.append(title)
        top.append(self.mode_btn)
        card.append(top)

        self.s_lbl, self.u_lbl = Gtk.Label(hexpand=True), Gtk.Label(hexpand=True)
        card.append(self.make_row("SESSION", self.s_lbl, lambda d: self.cycle("s", d)))
        card.append(self.make_row("USER", self.u_lbl, lambda d: self.cycle("u", d)))

        self.pw = Gtk.PasswordEntry(placeholder_text="Password")
        self.pw.connect("activate", self.submit)
        card.append(self.pw)

        self.status = Gtk.Label(label="")
        self.status.add_css_class("status-label")
        card.append(self.status)

        power_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.reboot_btn = Gtk.Button(label="[REBOOT]", hexpand=True)
        self.power_btn = Gtk.Button(label="[POWEROFF]", hexpand=True)
        for btn, act in ((self.reboot_btn, "reboot"), (self.power_btn, "poweroff")):
            btn.add_css_class("cycle-btn")
            btn.connect("clicked", lambda _b, a=act: self.handle_power(a))
            power_row.append(btn)
        card.append(power_row)

        # D-pad spatial focus navigation with arrow keys + Enter activation
        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", self.on_key)
        self.add_controller(kc)

        self.refresh()
        self.pw.grab_focus()

    def on_key(self, _ctrl, keyval, _keycode, _state):
        focused = self.get_focus()
        in_pw = focused is self.pw or (focused and focused.get_parent() is self.pw)

        if keyval == Gdk.KEY_Up:
            self.move_focus(Gtk.DirectionType.UP)
            return True
        if keyval == Gdk.KEY_Down:
            self.move_focus(Gtk.DirectionType.DOWN)
            return True
        if keyval == Gdk.KEY_Left and not (in_pw and self.pw.get_text()):
            self.move_focus(Gtk.DirectionType.LEFT)
            return True
        if keyval == Gdk.KEY_Right and not (in_pw and self.pw.get_text()):
            self.move_focus(Gtk.DirectionType.RIGHT)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and isinstance(focused, Gtk.Button):
            focused.activate()
            return True
        if keyval == Gdk.KEY_Escape and not self.client.sock:
            self.close()
            return True
        return False

    def handle_power(self, action):
        if self.confirm_action != action:
            self.confirm_action = action
            self.status.set_text(f"Press Enter / click [{action.upper()}] again to confirm")
            return
        if not self.client.sock:
            self.status.set_text(f"[TEST MODE] Would run: systemctl {action}")
            self.confirm_action = None
            return
        subprocess.run(["systemctl", action], check=False)

    def make_row(self, tag, lbl, cb):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("cycler-row")
        t = Gtk.Label(label=f"{tag}:")
        t.add_css_class("muted-label")
        b1, b2 = Gtk.Button(label="<"), Gtk.Button(label=">")
        b1.add_css_class("cycle-btn")
        b2.add_css_class("cycle-btn")
        b1.connect("clicked", lambda _: cb(-1))
        b2.connect("clicked", lambda _: cb(1))
        for w in (t, b1, lbl, b2):
            row.append(w)
        return row

    def refresh(self):
        self.u_lbl.set_text(self.users[self.u_idx])
        self.s_lbl.set_text(self.sessions[self.s_idx]["name"])

    def cycle(self, kind, d):
        self.confirm_action = None
        if kind == "u":
            self.u_idx = (self.u_idx + d) % len(self.users)
        else:
            self.s_idx = (self.s_idx + d) % len(self.sessions)
        self.refresh()

    def toggle_bg(self, _):
        self.bg_mode = "image" if self.bg_mode == "ly" else "ly"
        self.stack.set_visible_child_name(self.bg_mode)
        self.mode_btn.set_label(f"[BG: {self.bg_mode.upper()}]")

    def submit(self, _):
        user, cmd = self.users[self.u_idx], self.sessions[self.s_idx]["cmd"]
        if not self.client.sock:
            self.status.set_text(f"[TEST] {user} -> {' '.join(cmd)}")
            return
        res = self.client.send({"type": "create_session", "username": user})
        if res.get("type") == "auth_message":
            res = self.client.send({"type": "post_auth_message_response", "response": self.pw.get_text()})
        if res.get("type") == "success":
            self.client.send({"type": "start_session", "cmd": cmd, "env": []}, wait_reply=False)
            sys.exit(0)
        self.client.send({"type": "cancel_session"})
        self.pw.set_text("")
        self.status.set_text(res.get("description", "Auth failed"))


def on_activate(app):
    disp = Gdk.Display.get_default()
    if disp and (BASE / "style.css").exists():
        css = Gtk.CssProvider()
        css.load_from_path(str(BASE / "style.css"))
        Gtk.StyleContext.add_provider_for_display(disp, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win = GreeterWindow(app)
    win.present()


if __name__ == "__main__":
    app = Gtk.Application(application_id="org.arch.modulargreeter")
    app.connect("activate", on_activate)
    app.run(None)
