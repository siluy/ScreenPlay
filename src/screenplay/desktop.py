"""Desktop-only input provider. No imports of PyAutoGUI until actually needed."""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from .protocol import Click, Drag, Move, KeyPress, Wait


class DesktopPermissionError(RuntimeError):
    pass


def mac_activate_pid(pid: int) -> int:
    """Activate one known game process; no accessibility tree is read."""
    api = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    api.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
    api.AXUIElementCreateApplication.restype = ctypes.c_void_p
    api.AXUIElementSetAttributeValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    api.AXUIElementSetAttributeValue.restype = ctypes.c_int
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    app = api.AXUIElementCreateApplication(pid)
    attribute = cf.CFStringCreateWithCString(None, b"AXFrontmost", 0x08000100)
    try:
        truth = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        return api.AXUIElementSetAttributeValue(app, attribute, truth)
    finally:
        cf.CFRelease(attribute)
        cf.CFRelease(app)


def mac_frontmost_pid() -> int | None:
    """Read current focus directly; NSWorkspace can cache it without a main run loop."""
    api = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    api.AXUIElementCreateSystemWide.restype = ctypes.c_void_p
    api.AXUIElementCopyAttributeValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    api.AXUIElementCopyAttributeValue.restype = ctypes.c_int
    api.AXUIElementGetPid.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    api.AXUIElementGetPid.restype = ctypes.c_int
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    system = api.AXUIElementCreateSystemWide()
    attribute = cf.CFStringCreateWithCString(None, b"AXFocusedApplication", 0x08000100)
    app = ctypes.c_void_p()
    try:
        if api.AXUIElementCopyAttributeValue(system, attribute, ctypes.byref(app)) == 0 and app.value:
            pid = ctypes.c_int()
            if api.AXUIElementGetPid(app, ctypes.byref(pid)) == 0:
                return pid.value
    finally:
        if app.value: cf.CFRelease(app)
        cf.CFRelease(attribute)
        cf.CFRelease(system)
    # A read-only capture can have Screen Recording but not Accessibility access.
    if threading.current_thread() is threading.main_thread():
        import AppKit
        AppKit.NSRunLoop.currentRunLoop().runUntilDate_(AppKit.NSDate.dateWithTimeIntervalSinceNow_(.01))
        front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return front.processIdentifier() if front else None
    return None


def permissions() -> dict:
    if sys.platform != "darwin":
        return {"screen_capture": None, "input_control": None, "platform": sys.platform}
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    result = {"platform": "darwin"}
    for key, name in [("screen_capture", "CGPreflightScreenCaptureAccess"),
                      ("input_control", "CGPreflightPostEventAccess")]:
        method = getattr(cg, name)
        method.restype = ctypes.c_bool
        result[key] = bool(method())
    return result


def require_permissions(*, screen_capture=True, input_control=True):
    p = permissions()
    missing = []
    if sys.platform == "darwin":
        if screen_capture and not p["screen_capture"]:
            missing.append("Screen Recording")
        if input_control and not p["input_control"]:
            missing.append("Accessibility (keyboard/mouse control)")
    if missing:
        raise DesktopPermissionError(
            "Missing macOS permission: " + ", ".join(missing) + ". Enable it for the app running "
            "this command in System Settings > Privacy & Security, then restart "
            "that terminal/app and run screenplay doctor. No permission prompt is requested automatically."
        )


class PyAutoGUIDesktop:
    POINTER_SETTLE_SECONDS = 0.08
    def __init__(self, pid: int):
        require_permissions(input_control=False)
        import pyautogui
        self.gui = pyautogui
        self.gui.PAUSE = 0.03
        self.gui.FAILSAFE = True
        self.pid = pid

    def focus(self):
        if sys.platform == "darwin":
            import AppKit
            # A new Python/SDL app can publish its first frame before macOS has
            # registered it as an activatable app, especially on sequential resets.
            deadline = time.monotonic() + 4
            activation_status = None
            next_activation = time.monotonic() + .2
            while time.monotonic() < deadline:
                if mac_frontmost_pid() == self.pid:
                    return
                app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(self.pid)
                if app:
                    app.activateWithOptions_(AppKit.NSApplicationActivateAllWindows | AppKit.NSApplicationActivateIgnoringOtherApps)
                if time.monotonic() >= next_activation:
                    activation_status = mac_activate_pid(self.pid)
                    next_activation = time.monotonic() + .5
                if threading.current_thread() is threading.main_thread():
                    AppKit.NSRunLoop.currentRunLoop().runUntilDate_(AppKit.NSDate.dateWithTimeIntervalSinceNow_(.025))
                else:
                    time.sleep(.025)
            raise RuntimeError(f"Game is not foreground; target_pid={self.pid}, focused_pid={mac_frontmost_pid()}, activation_status={activation_status}; refusing desktop input")

    def capture(self, viewport: dict):
        self.focus()
        image = self.gui.screenshot()
        size = self.gui.size()
        sx, sy = image.width / size.width, image.height / size.height
        x, y, w, h = (int(round(viewport[k])) for k in ("x", "y", "width", "height"))
        if x < 0 or y < 0 or x + w > size.width or y + h > size.height:
            raise RuntimeError("Game viewport is outside the primary display")
        # Only the cropped game pixels leave this function or reach the disk.
        return image.crop((round(x*sx), round(y*sy), round((x+w)*sx), round((y+h)*sy))).resize((w, h))

    def execute(self, action, viewport: dict):
        require_permissions(screen_capture=False)
        self.focus()
        x0, y0 = int(round(viewport["x"])), int(round(viewport["y"]))
        if isinstance(action, Click):
            # Let the native UI process pointer entry before button events.
            # OpenTTD menus otherwise sometimes dismiss with no selected item.
            self.gui.moveTo(x0 + action.x, y0 + action.y)
            time.sleep(self.POINTER_SETTLE_SECONDS)
            self.gui.click(clicks=action.count,
                           interval=0.10 if action.count == 2 else 0, button=action.button)
        elif isinstance(action, Move):
            self.gui.moveTo(x0 + action.x, y0 + action.y)
        elif isinstance(action, Drag):
            self.gui.moveTo(x0 + action.from_[0], y0 + action.from_[1])
            time.sleep(self.POINTER_SETTLE_SECONDS)
            try:
                self.gui.dragTo(x0 + action.to[0], y0 + action.to[1],
                                duration=action.duration_ms / 1000, button=action.button)
            finally:
                self.gui.mouseUp(button=action.button)
        elif isinstance(action, KeyPress):
            try:
                self.gui.press(action.key)
            finally:
                self.gui.keyUp(action.key)
        elif isinstance(action, Wait):
            time.sleep(action.duration_ms / 1000)
        else:
            raise ValueError("Unsupported input action")
