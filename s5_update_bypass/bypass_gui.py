#!/usr/bin/env python3
"""S5 更新验签 RAM 工具 —— macOS 图形界面

不刷 ROM、不改 .upd，只通过服务模式 USB 写相机 RAM。
"""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from bypass_core import (
    BypassError,
    CODE_ADDR,
    SWITCH_ADDR,
    S5ServiceUSB,
    UpdateBypass,
)

BG = "#1e1e1e"
FG = "#e0e0e0"
DIM = "#888888"
ACCENT = "#4a9eff"
WARN = "#ff9f43"
OK = "#2ecc71"
ERR = "#e74c3c"
RED = "#c0392b"
GREEN = "#27ae60"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.dev = None
        self.bypass = None
        self.busy = False
        self._closed = False
        self.ui_queue = queue.Queue()

        root.title("S5 更新验签 RAM 工具")
        root.geometry("720x700")
        root.configure(bg=BG)
        root.resizable(False, False)

        self._build()
        self.log("就绪。相机进入服务模式（PLAY + AF-ON 同时按住开机），点「连接相机」。")
        self.log("本工具只写 RAM，不刷 ROM、不改升级包；重启后恢复原状。")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(30, self._drain_ui)

    def _build(self):
        r = self.root
        for c in range(3):
            r.grid_columnconfigure(c, weight=1)

        tk.Label(r, text="S5 更新验签 RAM 工具", font=("Helvetica", 20, "bold"),
                 bg=BG, fg=FG).grid(row=0, column=0, columnspan=3, pady=(16, 2))
        tk.Label(r, text=f"code 0x{CODE_ADDR:08X}   switch 0x{SWITCH_ADDR:08X}",
                 font=("Menlo", 10), bg=BG, fg=DIM).grid(row=1, column=0, columnspan=3, pady=(0, 12))

        # status block
        self.status_var = tk.StringVar(value="未连接")
        self.layout_var = tk.StringVar(value="—")
        self.code_var = tk.StringVar(value="—")
        self.switch_var = tk.StringVar(value="—")
        self.eff_var = tk.StringVar(value="—")

        def row(label, var, row_idx, mono=False, color=FG):
            tk.Label(r, text=label, font=("Helvetica", 11), bg=BG, fg=DIM,
                     anchor="w").grid(row=row_idx, column=0, sticky="w", padx=(24, 0), pady=2)
            lab = tk.Label(r, textvariable=var, font=("Menlo" if mono else "Helvetica", 11, "bold"),
                           bg=BG, fg=color, anchor="e")
            lab.grid(row=row_idx, column=1, columnspan=2, sticky="e", padx=(0, 24), pady=2)
            return lab

        self.status_label = row("相机", self.status_var, 2)
        row("布局", self.layout_var, 3)
        self.code_label = row("代码", self.code_var, 4, mono=True)
        self.switch_label = row("开关", self.switch_var, 5, mono=True)
        row("当前效果", self.eff_var, 6)

        # connection buttons
        self.btn_connect = self._btn(r, "连接相机", self.on_connect, ACCENT)
        self.btn_connect.grid(row=7, column=0, sticky="ew", padx=(24, 4), pady=(14, 4))
        self.btn_read = self._btn(r, "读取状态", self.on_read, "#555")
        self.btn_read.grid(row=7, column=1, sticky="ew", padx=4, pady=(14, 4))
        self.btn_disconnect = self._btn(r, "断开", self.on_disconnect, "#555")
        self.btn_disconnect.grid(row=7, column=2, sticky="ew", padx=(4, 24), pady=(14, 4))

        # mode
        mode_frame = tk.Frame(r, bg=BG)
        mode_frame.grid(row=8, column=0, columnspan=3, sticky="ew", padx=24, pady=(10, 2))
        tk.Label(mode_frame, text="模式", font=("Helvetica", 11), bg=BG, fg=DIM).pack(side="left")
        self.mode_var = tk.StringVar(value="full")
        tk.Radiobutton(mode_frame, text="彻底关闭（官方开关，ECDSA + SHA 都跳过）",
                       variable=self.mode_var, value="full", bg=BG, fg=FG,
                       selectcolor=BG, activebackground=BG, activeforeground=FG,
                       font=("Helvetica", 11)).pack(side="left", padx=(12, 8))
        tk.Radiobutton(mode_frame, text="仅关 ECDSA（保留 SHA/CRC）",
                       variable=self.mode_var, value="ecdsa", bg=BG, fg=FG,
                       selectcolor=BG, activebackground=BG, activeforeground=FG,
                       font=("Helvetica", 11)).pack(side="left")

        # action buttons
        self.btn_apply = self._btn(r, "一键关闭验签", self.on_apply, RED,
                                   font=("Helvetica", 15, "bold"))
        self.btn_apply.grid(row=9, column=0, columnspan=2, sticky="ew",
                            padx=(24, 4), pady=(8, 4), ipady=8)
        self.btn_restore = self._btn(r, "恢复验签", self.on_restore, GREEN,
                                     font=("Helvetica", 13, "bold"))
        self.btn_restore.grid(row=9, column=2, sticky="ew", padx=(4, 24), pady=(8, 4), ipady=8)

        # log
        tk.Label(r, text="日志", font=("Helvetica", 10), bg=BG, fg=DIM,
                 anchor="w").grid(row=10, column=0, columnspan=3, sticky="w", padx=24)
        self.log_box = scrolledtext.ScrolledText(r, height=10, bg="#111", fg="#ccc",
                                                 font=("Menlo", 10), insertbackground=FG,
                                                 bd=0, wrap="word")
        self.log_box.grid(row=11, column=0, columnspan=3, sticky="nsew", padx=24, pady=(4, 8))
        self.log_box.configure(state="disabled")
        r.grid_rowconfigure(11, weight=1)

        tk.Label(
            r,
            text="⚠ 只写 RAM：重启即失效。full 模式最稳；ecdsa 模式改指令，可能受 I-cache 影响。"
                 "外层 CRC32 与 bootloader 层不在本工具范围内。",
            font=("Helvetica", 9), bg=BG, fg=DIM, wraplength=660, justify="left",
        ).grid(row=12, column=0, columnspan=3, pady=(0, 10), padx=24, sticky="w")

        self._set_buttons(False)

    def _btn(self, parent, text, cmd, color, font=("Helvetica", 11, "bold")):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         bd=0, font=font, cursor="hand2")

    def _set_buttons(self, connected: bool):
        state = "normal" if connected else "disabled"
        for b in (self.btn_read, self.btn_disconnect, self.btn_apply, self.btn_restore):
            b.configure(state=state)
        self.btn_connect.configure(state="disabled" if connected else "normal")

    def _post(self, fn, *args):
        if not self._closed:
            self.ui_queue.put((fn, args))

    def _drain_ui(self):
        if self._closed:
            return
        try:
            while True:
                fn, args = self.ui_queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        if not self._closed:
            self.root.after(30, self._drain_ui)

    def log(self, msg: str):
        self._post(self._append_log, msg)

    def _append_log(self, msg: str):
        if self._closed:
            return
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except tk.TclError:
            pass

    def _run(self, fn, *args):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)

        def worker():
            try:
                fn(*args)
            except Exception as e:
                msg = str(e)
                self.log(f"✗ 错误：{msg}")
                self._post(lambda m=msg: messagebox.showerror("错误", m))
            finally:
                self.busy = False
                self._post(self._set_buttons, self.dev is not None)

        threading.Thread(target=worker, daemon=True).start()

    # --- actions -------------------------------------------------------
    def on_connect(self):
        self._run(self._do_connect)

    def _do_connect(self):
        self.log("正在查找相机（04DA:2370）…")
        self.dev = S5ServiceUSB()
        self.bypass = UpdateBypass(self.dev)
        self.log("✓ 已连接")
        self._post(self._set_status, "已连接", OK)
        self._do_read()

    def on_disconnect(self):
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None
        self.bypass = None
        self._set_status("未连接", WARN)
        for var in (self.layout_var, self.code_var, self.switch_var, self.eff_var):
            var.set("—")
        self._set_buttons(False)
        self.log("已断开")

    def on_read(self):
        self._run(self._do_read)

    def _do_read(self):
        if not self.bypass:
            return
        st = self.bypass.status()
        self._post(self._show_status, st)
        self.log(
            f"code=0x{st.code_raw:04X} switch=0x{st.switch_raw:04X} "
            f"layout={st.layout} effective={st.effective}"
        )

    def _show_status(self, st):
        self.layout_var.set(st.layout)
        self.code_var.set(f"0x{st.code_raw:04X}  {st.code_state}")
        self.switch_var.set(f"0x{st.switch_raw:04X}  {st.switch_state}")
        self.eff_var.set(st.effective)

        color = OK if st.effective.startswith(("full-skip", "ecdsa-skip")) else (
            WARN if st.code_state == "stock" else ERR
        )
        self.code_label.configure(fg=color)
        self.switch_label.configure(fg=color)

    def on_apply(self):
        mode = self.mode_var.get()
        if mode == "full":
            text = (
                "将写 0x8631801A = 1：关闭 ECDSA 和逐组件 SHA-256。\n\n"
                "这是官方跳签开关，只写数据，最稳。\n"
                "只写 RAM，重启后失效。继续？"
            )
        else:
            text = (
                "将写 0x868C704E = 0xE023：跳过 ECDSA，但保留 SHA-256/CRC32。\n\n"
                "这是指令内存修改；如果 I-cache 没刷新，可能不生效。\n"
                "只写 RAM，重启后失效。继续？"
            )
        if not messagebox.askyesno("确认", text):
            return
        # Capture the Tk variable on the UI thread; worker threads must not touch Tk.
        self._run(self._do_apply, mode)

    def _do_apply(self, mode: str):
        if not self.bypass:
            return
        before = self.bypass.status()
        self.log(f"写入前：code=0x{before.code_raw:04X} switch=0x{before.switch_raw:04X}")
        after = self.bypass.apply(mode)
        self._post(self._show_status, after)
        if mode == "full":
            ok = after.switch_raw == 1
            expected = "0x8631801A = 1"
        else:
            ok = after.code_raw == 0xE023
            expected = "0x868C704E = 0xE023"
        if ok:
            self.log(f"✓ 已写入 {expected}，读回一致")
            self.log("现在去相机里触发 SD 更新；更新完重启即恢复原状。")
        else:
            self.log(f"✗ 写入后读回不符（code=0x{after.code_raw:04X} switch=0x{after.switch_raw:04X}）")

    def on_restore(self):
        if not messagebox.askyesno("确认", "恢复 RAM 里的验签状态？\n（开关写 0，代码写回 0xD021）"):
            return
        self._run(self._do_restore)

    def _do_restore(self):
        if not self.bypass:
            return
        after = self.bypass.restore("all")
        self._post(self._show_status, after)
        self.log(f"✓ 已恢复：code=0x{after.code_raw:04X} switch=0x{after.switch_raw:04X}")

    def on_close(self):
        self._closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_status(self, text: str, color: str):
        if self._closed:
            return
        self.status_var.set(text)
        self.status_label.configure(fg=color)


def main() -> int:
    # Dependency/frozen smoke test: works without a display or a camera.
    if "--self-test" in sys.argv:
        from bypass_core import (
            CODE_ECDSA_ONLY,
            CODE_STOCK,
            FakeDevice,
            SWITCH_OFF,
            UpdateBypass,
        )

        b = UpdateBypass(FakeDevice())
        assert b.status().code_raw == CODE_STOCK
        b.apply("ecdsa")
        assert b.status().code_raw == CODE_ECDSA_ONLY
        b.restore("all")
        assert b.status().switch_raw == SWITCH_OFF

        # Verify the bundled libusb is discoverable in the frozen app.
        try:
            import s5_unlock_core

            lib = s5_unlock_core._find_libusb()
        except Exception as e:  # pragma: no cover
            lib = None
            print(f"libusb check failed: {e}", file=sys.stderr)
        assert lib, "bundled libusb not found"
        print(f"libusb: {lib}")

        print("S5UpdateBypass self-test OK")
        return 0

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
