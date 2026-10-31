"""Exercise the visible installed WinForms dialog. The caller supplies its verified tray PID."""

import ctypes
import time

import win32con
import win32gui
import win32process


def wait(find, label):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        value = find()
        if value:
            return value
        time.sleep(0.15)
    raise RuntimeError("XT did not expose " + label)


def find_window(pid, caption):
    matches = []

    def visit(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[
            1
        ] == pid and win32gui.IsWindowVisible(hwnd):
            if win32gui.GetWindowText(hwnd) == caption:
                matches.append(hwnd)
        return True

    win32gui.EnumWindows(visit, None)
    return next(iter(matches), None)


def controls(window):
    children = []
    win32gui.EnumChildWindows(
        window, lambda hwnd, _: children.append(hwnd) or True, None
    )
    return [h for h in children if win32gui.IsWindowVisible(h)]


def caption(hwnd):
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.SendMessageW(
        hwnd, win32con.WM_GETTEXT, len(buffer), ctypes.byref(buffer)
    )
    return buffer.value


def foreground(hwnd):
    user = ctypes.windll.user32
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() != hwnd:
        current = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[
            0
        ]
        thread = ctypes.windll.kernel32.GetCurrentThreadId()
        joined = user.AttachThreadInput(thread, current, True)
        try:
            user.SetForegroundWindow(hwnd)
        finally:
            if joined:
                user.AttachThreadInput(thread, current, False)
    wait(
        lambda: win32gui.GetForegroundWindow() == hwnd and not win32gui.IsIconic(hwnd),
        "a foreground dialog",
    )


def click(window, name):
    button = wait(
        lambda: next(
            (
                h
                for h in controls(window)
                if caption(h) == name and win32gui.IsWindowEnabled(h)
            ),
            None,
        ),
        name,
    )
    win32gui.PostMessage(button, win32con.BM_CLICK, 0, 0)


def open_services(pid):
    panel = find_window(pid, "Tlachihuani · Services")
    if not panel:
        main = wait(lambda: find_window(pid, "Tlachihuani"), "Show panel")
        foreground(main)
        click(main, "Services…")
        panel = wait(lambda: find_window(pid, "Tlachihuani · Services"), "Services")
    foreground(panel)
    wait(
        lambda: any("Web · ready" in caption(h) for h in controls(panel)),
        "a healthy installed provider",
    )
    return panel


def approve(pid, code):
    panel = open_services(pid)
    fields = [
        h for h in controls(panel) if ".EDIT." in win32gui.GetClassName(h).upper()
    ]
    field = next(h for h in fields if win32gui.SendMessage(h, 0x00D5, 0, 0) == 8)
    ctypes.windll.user32.SendMessageW(
        field, win32con.WM_SETTEXT, 0, ctypes.c_wchar_p(code)
    )
    click(panel, "Approve code")
    receipt = wait(
        lambda: find_window(pid, "Pairing approved"), "the native approval receipt"
    )
    foreground(receipt)
    click(receipt, "OK")
    print(
        "PASS installed XT Show panel, Services, engine/web readiness and visible code approval",
        flush=True,
    )
