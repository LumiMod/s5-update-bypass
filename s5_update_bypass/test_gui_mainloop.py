#!/usr/bin/env python3
"""Offline GUI test that runs the real Tk mainloop with a worker thread.

This reproduces the original failure mode: a background worker logs while the
UI is alive, then the window is closed mid-flight.
"""
from __future__ import annotations

import tkinter as tk

from bypass_core import CODE_ECDSA_ONLY, CODE_STOCK, FakeDevice, UpdateBypass
from bypass_gui import App


def main() -> int:
    root = tk.Tk()
    app = App(root)
    app.dev = FakeDevice()
    app.bypass = UpdateBypass(app.dev)

    results: list[str] = []

    def step1() -> None:
        app._run(app._do_apply, "ecdsa")

    def step2() -> None:
        st = app.bypass.status()
        results.append(f"ecdsa={st.code_raw:04X}")
        app._run(app._do_restore)

    def step3() -> None:
        st = app.bypass.status()
        results.append(f"restore={st.code_raw:04X}")
        app._run(app._do_apply, "full")

    def step4() -> None:
        st = app.bypass.status()
        results.append(f"full={st.switch_raw:04X}")
        # Close the window while the worker may still be finishing.
        app.on_close()

    root.after(100, step1)
    root.after(400, step2)
    root.after(700, step3)
    root.after(1000, step4)
    root.after(1600, lambda: root.quit())

    root.mainloop()

    print("results:", results)
    assert results == ["ecdsa=E023", "restore=D021", "full=0001"], results
    print("GUI MAINLOOP TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
