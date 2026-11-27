#!/usr/bin/env python3
"""S5 更新验签 RAM 工具 —— 核心逻辑

只通过服务模式 USB 读写相机 RAM，不碰 NAND、不改 .upd、不刷 ROM。

两种模式：

1. full / switch
   物理地址 0x8631801A 写 halfword 1。
   这是固件自带的跳签开关：program 更新器会跳过 ECDSA 和逐组件 SHA-256。
   只写数据，不涉及指令缓存，最稳。

2. ecdsa / code
   物理地址 0x868C704E 写 halfword 0xE023。
   原值 0xD021 = beq 0x068C7094
   新值 0xE023 = b   0x068C7098
   所有更新容器都跳过 ECDSA，但 verify_enabled 仍为 1，
   逐组件 SHA-256 和外包 CRC32 继续强制校验。

注意：ecdsa 模式改的是指令内存；如果 CPU 已经缓存了那一行，
可能需要让更新器重新加载/重启后才看到新指令。full 模式没有这个问题。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Reuse the existing service-mode USB transport.
# - Frozen (PyInstaller): s5_unlock_core is bundled as a hidden import.
# - Development: it lives in ../s5_unlock.
try:
    from s5_unlock_core import S5ServiceUSB  # type: ignore
except Exception:  # pragma: no cover - only needed for real hardware
    sys.path.insert(0, str(HERE.parent / "s5_unlock"))
    try:
        from s5_unlock_core import S5ServiceUSB  # type: ignore
    except Exception:
        S5ServiceUSB = None  # type: ignore


# --- V2.9 program layout -------------------------------------------------
# VA 0x068C704E -> physical 0x868C704E
CODE_ADDR = 0x868C704E

# 21 D0  = beq #0x068C7094   (stock)
CODE_STOCK = 0xD021

# 23 E0  = b   #0x068C7098   (skip ECDSA, keep verify_enabled=1 -> SHA-256 runs)
CODE_ECDSA_ONLY = 0xE023

# 21 E0  = b   #0x068C7094   (skip ECDSA and SHA-256; not used by default)
CODE_ALL = 0xE021

# Global update control block: 0x8631801A, 0=verify, 1=skip.
SWITCH_ADDR = 0x8631801A
SWITCH_OFF = 0x0000
SWITCH_ON = 0x0001


class BypassError(RuntimeError):
    """User-facing error."""


@dataclass
class Status:
    code_raw: int
    switch_raw: int
    code_state: str
    switch_state: str
    effective: str
    layout: str

    def as_dict(self) -> dict:
        return asdict(self)


def _u16(data: bytes) -> int:
    if len(data) != 2:
        raise BypassError(f"expected 2 bytes, got {len(data)}")
    return int.from_bytes(data, "little")


class UpdateBypass:
    """High-level operations on a connected S5 service-mode device."""

    def __init__(self, dev):
        self.dev = dev

    # --- low level -----------------------------------------------------
    def read_u16(self, addr: int) -> int:
        return _u16(self.dev.read_mem(addr, 2))

    def write_u16(self, addr: int, value: int, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.dev.write_u16(addr, value & 0xFFFF, verify=True)

    # --- status --------------------------------------------------------
    def status(self) -> Status:
        code = self.read_u16(CODE_ADDR)
        switch = self.read_u16(SWITCH_ADDR)

        if code == CODE_STOCK:
            code_state = "stock"
            layout = "V2.9"
        elif code == CODE_ECDSA_ONLY:
            code_state = "ecdsa-skip"
            layout = "V2.9"
        elif code == CODE_ALL:
            code_state = "all-skip"
            layout = "V2.9"
        else:
            code_state = "unknown"
            layout = "unknown"

        if switch == SWITCH_ON:
            switch_state = "on"
        elif switch == SWITCH_OFF:
            switch_state = "off"
        else:
            switch_state = "unknown"

        if switch_state == "on":
            effective = "full-skip (ECDSA + SHA-256)"
        elif code_state == "ecdsa-skip":
            effective = "ecdsa-skip (SHA-256 + CRC32 still on)"
        elif code_state == "all-skip":
            effective = "code-all-skip (ECDSA + SHA-256 off)"
        elif code_state == "stock":
            effective = "stock (ECDSA on)"
        else:
            effective = "unknown"

        return Status(
            code_raw=code,
            switch_raw=switch,
            code_state=code_state,
            switch_state=switch_state,
            effective=effective,
            layout=layout,
        )

    # --- version guard -------------------------------------------------
    def _require_v29_layout(self) -> int:
        code = self.read_u16(CODE_ADDR)
        if code not in (CODE_STOCK, CODE_ECDSA_ONLY, CODE_ALL):
            raise BypassError(
                f"0x{CODE_ADDR:08X} 当前是 0x{code:04X}，不是已知的 V2.9 布局；"
                "版本/地址不匹配，拒绝写入。"
            )
        return code

    # --- apply ---------------------------------------------------------
    def apply(self, mode: str, dry_run: bool = False) -> Status:
        mode = mode.lower()
        if mode in ("full", "switch"):
            self._require_v29_layout()
            cur = self.read_u16(SWITCH_ADDR)
            if cur == SWITCH_ON:
                return self.status()
            if cur != SWITCH_OFF:
                raise BypassError(
                    f"0x{SWITCH_ADDR:08X} 当前是 0x{cur:04X}，不是预期的 0x0000；"
                    "版本/地址不匹配，拒绝写入。"
                )
            self.write_u16(SWITCH_ADDR, SWITCH_ON, dry_run=dry_run)
            return self.status()

        if mode == "ecdsa":
            cur = self.read_u16(CODE_ADDR)
            if cur == CODE_ECDSA_ONLY:
                return self.status()
            if cur not in (CODE_STOCK, CODE_ALL):
                raise BypassError(
                    f"0x{CODE_ADDR:08X} 当前是 0x{cur:04X}，不是 V2.9 的 0xD021/0xE021；"
                    "版本/地址不匹配，拒绝写入。"
                )
            self.write_u16(CODE_ADDR, CODE_ECDSA_ONLY, dry_run=dry_run)
            return self.status()

        raise BypassError(f"unknown mode: {mode}")

    # --- restore -------------------------------------------------------
    def restore(self, mode: str = "all", dry_run: bool = False) -> Status:
        mode = mode.lower()
        if mode not in ("all", "switch", "full", "ecdsa", "code"):
            raise BypassError(f"unknown mode: {mode}")
        cur_code = self._require_v29_layout()
        if mode in ("all", "switch", "full"):
            if self.read_u16(SWITCH_ADDR) == SWITCH_ON:
                self.write_u16(SWITCH_ADDR, SWITCH_OFF, dry_run=dry_run)
        if mode in ("all", "ecdsa", "code"):
            if cur_code in (CODE_ECDSA_ONLY, CODE_ALL):
                self.write_u16(CODE_ADDR, CODE_STOCK, dry_run=dry_run)
        return self.status()

    # --- dump ----------------------------------------------------------
    def dump(self) -> dict:
        return {
            "code_addr": CODE_ADDR,
            "code_context": self.dev.read_mem(CODE_ADDR - 8, 16).hex(),
            "switch_addr": SWITCH_ADDR,
            "switch_context": self.dev.read_mem(SWITCH_ADDR - 8, 16).hex(),
            "status": self.status().as_dict(),
        }


class FakeDevice:
    """In-memory device used by --self-test; no hardware/USB required."""

    def __init__(self, code: int = CODE_STOCK, switch: int = SWITCH_OFF):
        self.mem = {
            CODE_ADDR: bytearray(code.to_bytes(2, "little")),
            SWITCH_ADDR: bytearray(switch.to_bytes(2, "little")),
        }

    def read_mem(self, addr: int, size: int) -> bytes:
        out = bytearray()
        for i in range(size):
            a = addr + i
            if a in self.mem:
                out.append(self.mem[a][0])
            elif a - 1 in self.mem and a % 2 == 1:
                out.append(self.mem[a - 1][1])
            else:
                out.append(0)
        return bytes(out)

    def write_u16(self, addr: int, value: int, verify: bool = True) -> None:
        if addr not in self.mem:
            raise BypassError(f"FakeDevice: unmapped 0x{addr:08X}")
        self.mem[addr][:] = (value & 0xFFFF).to_bytes(2, "little")
        if verify and self.read_mem(addr, 2) != (value & 0xFFFF).to_bytes(2, "little"):
            raise BypassError("FakeDevice: verify failed")


def format_status(st: Status) -> str:
    return (
        f"layout       : {st.layout}\n"
        f"code @0x{CODE_ADDR:08X}   : 0x{st.code_raw:04X}  ({st.code_state})\n"
        f"switch @0x{SWITCH_ADDR:08X}: 0x{st.switch_raw:04X}  ({st.switch_state})\n"
        f"effective    : {st.effective}"
    )
