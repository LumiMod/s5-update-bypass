#!/usr/bin/env python3
"""Offline GUI smoke test: no camera, no USB.

Verifies that the GUI can read/apply/restore against an in-memory FakeDevice,
and that logging after the window is destroyed does not raise TclError.
"""
from __future__ import annotations

import tkinter as tk

from bypass_core import CODE_ECDSA_ONLY, CODE_STOCK, FakeDevice, UpdateBypass
from bypass_gui import App


def drain(app: App) -> None:
    app._drain_ui()


def main() -> int:
    root = tk.Tk()
    app = App(root)
    root.update_idletasks()

    app.dev = FakeDevice()
    app.bypass = UpdateBypass(app.dev)

    app._do_read()
    drain(app)
    assert app.bypass.status().code_raw == CODE_STOCK
    print("read ok:", app.code_var.get(), "|", app.switch_var.get())

    app._do_apply("ecdsa")
    drain(app)
    st = app.bypass.status()
    assert st.code_raw == CODE_ECDSA_ONLY, st
    print("apply ecdsa ok:", app.code_var.get())

    app._do_restore()
    drain(app)
    assert app.bypass.status().code_raw == CODE_STOCK
    print("restore ok:", app.code_var.get())

    app._do_apply("full")
    drain(app)
    assert app.bypass.status().switch_raw == 1
    print("apply full ok:", app.switch_var.get())

    app._do_restore()
    drain(app)
    assert app.bypass.status().switch_raw == 0
    print("restore full ok:", app.switch_var.get())

    # Simulate the user closing the window while a worker is still logging.
    app.on_close()
    app.log("this must not raise after destroy")
    app._post(app._set_status, "x", "#fff")
    drain(app)
    print("post-close logging ok")

    print("GUI OFFLINE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
