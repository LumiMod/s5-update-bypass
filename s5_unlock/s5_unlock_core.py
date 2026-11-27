#!/usr/bin/env python3
"""S5 验签开关工具 —— macOS 核心传输层

对应 Windows 版 lumix_ml/usb_link.py 的 libusb 实现。
协议（来自 usb_link.py 真机实证）：
  - 设备：VID 0x04DA / PID 0x2370（服务模式）
  - 控制传输：bmRequestType=0x40, bRequest=0, wIndex=0/1
  - 写管道 EP 0x01，读管道 EP 0x82
  - 读 1 KiB：opcode 0x5C，帧 1030 字节
  - 写半字：opcode 0x9C，帧 16 字节

验签开关（静态分析确认）：
  物理地址 0x8631801A，halfword，0=验签开启，1=跳过验签
"""
import os
import sys
import time

import usb.core
import usb.backend.libusb1

VID = 0x04DA
PID = 0x2370
EP_OUT = 0x01
EP_IN = 0x82
BLOCK_SIZE = 1024
FRAME_5C = 1030

SWITCH_ADDR = 0x8631801A
SWITCH_OFF = 0x0000
SWITCH_ON = 0x0001

DRAM_LO = 0x80000000
DRAM_HI = 0xA0000000


def _libusb_names():
    """Platform-specific libusb shared-library file names."""
    if sys.platform == "win32":
        return ("libusb-1.0.dll", "libusb-1.0-0.dll")
    if sys.platform == "darwin":
        return ("libusb-1.0.dylib", "libusb-1.0.0.dylib")
    return ("libusb-1.0.so.0", "libusb-1.0.so")


def _search_dirs():
    """Directories that may hold a bundled libusb, in priority order."""
    dirs = []
    # PyInstaller onefile/onedir: resources are unpacked next to the executable
    # or under sys._MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs += [os.path.join(meipass, "lib"), meipass]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        dirs += [os.path.join(exe_dir, "lib"), exe_dir]
        # macOS .app: Contents/MacOS/../Resources
        dirs += [os.path.join(exe_dir, "..", "Resources", "lib"),
                 os.path.join(exe_dir, "..", "Resources")]
    here = os.path.dirname(os.path.abspath(__file__))
    dirs += [os.path.join(here, "lib"), here]
    return dirs


def _find_libusb():
    # libusb-package ships a platform-correct DLL/dylib and is the easiest
    # cross-platform source for the Windows build.
    try:
        import libusb_package  # type: ignore

        p = libusb_package.get_library_path()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass

    names = _libusb_names()
    for d in _search_dirs():
        for name in names:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p

    # System-wide fallbacks (development runs).
    if sys.platform == "darwin":
        candidates = [
            "/tmp/libusb-install/lib/libusb-1.0.dylib",
            "/opt/homebrew/lib/libusb-1.0.dylib",
            "/usr/local/lib/libusb-1.0.dylib",
            "/usr/lib/libusb-1.0.dylib",
        ]
    elif sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "libusb-1.0.dll"),
        ]
    else:
        candidates = ["/usr/lib/x86_64-linux-gnu/libusb-1.0.so.0",
                      "/usr/lib/aarch64-linux-gnu/libusb-1.0.so.0"]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def get_backend():
    lib = _find_libusb()
    if lib:
        return usb.backend.libusb1.get_backend(find_library=lambda x: lib)
    return usb.backend.libusb1.get_backend()


class S5ServiceUSB:
    def __init__(self, timeout_ms=2000):
        backend = get_backend()
        if backend is None:
            raise RuntimeError("找不到 libusb。请把 libusb-1.0.dylib 放到 lib/ 目录。")
        self.dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)
        if self.dev is None:
            raise RuntimeError(
                "未找到相机（04DA:2370）。\n"
                "请确认：\n"
                "  1. 相机已进入服务模式（PLAY + AF-ON 同时按住开机）\n"
                "  2. USB 线已连接\n"
                "  3. 相机没有进入普通 USB 模式"
            )
        self.timeout_ms = timeout_ms
        self._claimed = False
        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            pass
        try:
            self.dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass
        try:
            self.dev.claim_interface(0)
            self._claimed = True
        except usb.core.USBError as e:
            raise RuntimeError(f"无法占用 USB 接口：{e}")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        if self._claimed:
            try:
                self.dev.release_interface(0)
            except usb.core.USBError:
                pass
            self._claimed = False

    def _ctrl(self, wIndex):
        self.dev.ctrl_transfer(0x40, 0x00, 0, wIndex, 0, timeout=self.timeout_ms)

    def _write(self, data):
        return self.dev.write(EP_OUT, data, timeout=self.timeout_ms)

    def _read(self, size):
        return bytes(self.dev.read(EP_IN, size, timeout=self.timeout_ms))

    def read_block(self, addr, delay=0.0, retries=4):
        last = None
        for attempt in range(retries):
            try:
                return self._read_block_once(addr, delay)
            except (usb.core.USBError, RuntimeError) as e:
                last = e
                time.sleep(0.05 * (attempt + 1))
        raise RuntimeError(f"0x5C 读 0x{addr:08X} 失败（重试 {retries} 次）：{last}")

    def _read_block_once(self, addr, delay=0.0):
        p = bytearray(FRAME_5C)
        p[0] = 0x01
        p[1] = 0x00
        p[2] = 0xFF
        p[3] = 0x5C
        p[4:8] = (addr & 0xFFFFFFFF).to_bytes(4, "little")
        p[8:12] = ((addr + BLOCK_SIZE) & 0xFFFFFFFF).to_bytes(4, "little")
        p[FRAME_5C - 2] = sum(p[1:FRAME_5C - 2]) & 0xFF
        p[FRAME_5C - 1] = 0x00

        self._ctrl(0)
        self._write(bytes(p))
        if delay > 0:
            time.sleep(delay)
        self._ctrl(1)
        t = self._read(1)
        if t != b"\x01":
            raise RuntimeError(f"0x5C 类型字节异常：{t.hex()}")
        self._ctrl(1)
        rx = self._read(FRAME_5C)
        if len(rx) != FRAME_5C:
            raise RuntimeError(f"0x5C 帧长度异常：{len(rx)}")
        chk = sum(rx[1:FRAME_5C - 2]) & 0xFF
        if rx[3] != 0x05 or rx[-2] != chk or rx[-1] != 0:
            raise RuntimeError(f"0x5C 回复异常：op={rx[3]:#04x}")
        return rx[4:4 + BLOCK_SIZE]

    def read_mem(self, addr, size):
        start_blk = addr & ~0x3FF
        end_addr = addr + size
        buf = bytearray()
        for b_addr in range(start_blk, end_addr, BLOCK_SIZE):
            buf += self.read_block(b_addr)
        offset = addr - start_blk
        return bytes(buf[offset:offset + size])

    def write_u16(self, addr, val_u16, delay=0.02, verify=True):
        if addr & 1:
            raise ValueError(f"地址 0x{addr:08X} 必须 2 字节对齐")
        if not (DRAM_LO <= addr < DRAM_HI):
            raise ValueError(f"地址 0x{addr:08X} 不在 DRAM 安全窗口内")

        p = bytearray(16)
        p[0] = 0x08
        p[1] = 0x00
        p[2] = 0xFF
        p[3] = 0x9C
        p[4:8] = addr.to_bytes(4, "little")
        p[8:10] = (val_u16 & 0xFFFF).to_bytes(2, "little")
        p[14] = sum(p[1:14]) & 0xFF
        p[15] = 0x00

        self._ctrl(0)
        self._write(bytes(p))
        if delay > 0:
            time.sleep(delay)
        self._ctrl(1)
        t = self._read(1)
        if t != b"\x08":
            raise RuntimeError(f"0x9C 类型字节异常：{t.hex()}")
        self._ctrl(1)
        rx = self._read(16)
        chk = sum(rx[1:14]) & 0xFF
        if len(rx) != 16 or rx[3] != 0x01 or rx[4] != 0x00 or rx[14] != chk:
            raise RuntimeError(f"0x9C 写入被拒绝：rx={rx.hex()}")

        if verify:
            rb = self.read_mem(addr, 2)
            got = int.from_bytes(rb, "little")
            if got != (val_u16 & 0xFFFF):
                raise RuntimeError(
                    f"0x9C 校验失败 @0x{addr:08X}：写入 {val_u16:#06x}，读回 {got:#06x}"
                )

    def read_switch(self):
        raw = self.read_mem(SWITCH_ADDR, 2)
        return int.from_bytes(raw, "little")

    def set_switch(self, on):
        val = SWITCH_ON if on else SWITCH_OFF
        self.write_u16(SWITCH_ADDR, val, verify=True)
        return val

    def read_switch_context(self):
        base = SWITCH_ADDR & ~0x3FF
        blk = self.read_block(base)
        off = SWITCH_ADDR - base
        return blk[max(0, off - 16):off + 16]
