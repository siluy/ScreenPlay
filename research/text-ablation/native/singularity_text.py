"""Trusted native UI serializer. GPL-2.0-or-later, matching the linked game.

Uses the prepared original dialog loop and callbacks with an offscreen SDL surface.
Only widget text is exposed; fixture goals and private scorer state stay in the host.
"""
import json
import sys

import pygame
import screenplay_adapter as native
import screenplay.native_bridge as bridge
import singularity
from singularity.code import dirs, g
from singularity.code.graphics import button, dialog, scrollbar, slider, text

ACTION_EVENT = pygame.USEREVENT + 51
pending = None
controls = {}
revision = 0
initial = True
original_handle = dialog.Dialog.handle


def snapshot():
    global controls, revision
    revision += 1
    controls = {}
    current = dialog.Dialog.current_dialog
    lines = ["Current panel: " + type(current).__name__ + "."]
    blocked = {getattr(g.map_screen, key, None) for key in ("menu_button", "cheat_button")}

    def visit(w, depth=0):
        if not w.visible or w in blocked:
            return
        if isinstance(w, dialog.Dialog) and w is not current:
            return
        rect = getattr(w, "collision_rect", None)
        if rect is not None and (rect.width <= 0 or rect.height <= 0):
            return
        label = str(getattr(w, "text", "") or "").strip()
        rows = getattr(w.parent, "display_elements", [])
        if w in rows:
            row_index = rows.index(w) + w.parent.scrollbar.scroll_pos
            if row_index >= len(w.parent.list):
                return
        if isinstance(w, scrollbar._ArrowButton):
            label = "scroll " + (("left" if w.first else "right") if w.horizontal else ("up" if w.first else "down"))
        if isinstance(w, slider.Slider):
            kind = "slider"
        elif isinstance(w, text.EditableText):
            kind = "entry"
        elif isinstance(w, button.Button):
            kind = "button"
        elif w in getattr(w.parent, "display_elements", []):
            label = label or " | ".join(str(getattr(child, "text", "") or "").strip()
                                       for child in w.children if child.visible and getattr(child, "text", None))
            if not label:
                return
            kind = "row"
        else:
            kind = None
        prefix = "  " * min(depth, 4)
        if kind:
            ident = f"u{revision}_{len(controls)+1}"
            enabled = bool(getattr(w, "enabled", True))
            controls[ident] = (kind, w, enabled)
            description = f"{prefix}[{ident}] {kind}: {label}"
            if kind == "slider":
                description += f" value={int(w.slider_pos)}, range=0..{int(w.slider_max)}"
            if hasattr(w, "active"):
                description += f"; active={bool(w.active)}"
            if kind == "row":
                description += f"; selected={bool(getattr(w, 'selected', False))}"
                if hasattr(w, "progress"):
                    description += f"; progress={float(w.progress):.1%}"
            if not enabled:
                description += "; disabled"
            lines.append(description)
            if kind in {"slider", "entry", "button"}:
                return
        elif label:
            lines.append(prefix + label)
        for child in w.children:
            visit(child, depth+1)
    visit(current)
    lines.append(f"Simulation update opportunities remaining: {bridge.parameters['max_updates']-bridge.processed}.")
    return "\n".join(lines)


def dispatch(self, event):
    global pending
    if event.type != ACTION_EVENT:
        return original_handle(self, event)
    request = event.request
    pending = request
    pending["action_error"] = False
    action = request["action"]
    if action["type"] == "wait":
        pass
    else:
        control = controls.get(action.get("control"))
        if control is None or not control[2]:
            pending["action_error"] = True
        else:
            kind, w, _ = control
            if action["type"] == "set_value" and kind == "slider" and 0 <= action["value"] <= w.slider_max:
                w.slider_pos = action["value"]
            elif action["type"] == "type_text" and kind == "entry" and len(action["text"]) <= 100:
                value = action["text"]
                if any(c in value for c in "\n\r\x00") or (w.allowed_characters and any(c not in w.allowed_characters for c in value)):
                    pending["action_error"] = True
                else:
                    w.text = value
                    w.cursor_pos = len(value)
            elif action["type"] == "click" and kind in {"button", "row"}:
                # Keep the normal native event dispatch, including nested dialogs and confirmation.
                self.last_click = (0, (0, 0), -1)
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=w.collision_rect.center)
                return original_handle(self, event)
            else:
                pending["action_error"] = True
    if pending["action_error"]:
        pending["target"] = bridge.processed
        (bridge.private / "advance.txt").write_text(f"{request['sequence']} {bridge.processed}\n")
    return native_dialog_constants.NO_RESULT


def pump():
    global pending, initial
    if not native.active or dialog.Dialog.current_dialog is None:
        return
    if pending is not None:
        target = pending["target"]
        if bridge.processed < target:
            native_pump()
            return
    if initial or pending is not None:
        native_pump()
        dialog.Dialog.top.maybe_update()
        state = json.loads((bridge.private / "state.json").read_text())
        state["text"] = snapshot()
        state["action_error"] = bool(pending and pending["action_error"])
        sys.stdout.write("GWSTATE " + json.dumps(state) + "\n")
        sys.stdout.flush()
        initial = False
        pending = None
        line = sys.stdin.readline()
        if not line:
            raise SystemExit
        request = json.loads(line)
        request["target"] = bridge.processed + request["updates"]
        (bridge.private / "advance.txt").write_text(f"{request['sequence']} {request['target']}\n")
        pygame.event.post(pygame.event.Event(ACTION_EVENT, request=request))


if __name__ == "__main__":
    from singularity.code.graphics import constants as native_dialog_constants
    from singularity.code.screens.main_menu import MainMenu
    from singularity.code.screens.map import GameMenuDialog
    native_pump = native.pump
    native.pump = pump
    dialog.Dialog.handle = dispatch
    dirs.create_directories = native.isolated_directories
    MainMenu.show = native.start
    GameMenuDialog.load_game = native.forbidden
    g.debug = False
    sys.argv = [sys.argv[0], "--windowed", "--nosound", "--resolution", "1000x700", "--language", "en_US"]
    singularity.main()
