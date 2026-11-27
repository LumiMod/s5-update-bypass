#!/usr/bin/env python3
"""S5 更新验签 RAM 工具 —— 命令行版

用法：
  python3 bypass_cli.py status
  python3 bypass_cli.py apply --mode full
  python3 bypass_cli.py apply --mode ecdsa
  python3 bypass_cli.py restore
  python3 bypass_cli.py dump
  python3 bypass_cli.py self-test

full  = 写 0x8631801A=1，跳过 ECDSA + 逐组件 SHA-256（官方开关，最稳）
ecdsa = 写 0x868C704E=0xE023，只跳过 ECDSA，保留 SHA-256/CRC32
"""
from __future__ import annotations

import argparse
import json
import sys

from bypass_core import (
    BypassError,
    CODE_ADDR,
    CODE_ECDSA_ONLY,
    CODE_STOCK,
    SWITCH_ADDR,
    SWITCH_OFF,
    SWITCH_ON,
    S5ServiceUSB,
    FakeDevice,
    UpdateBypass,
    format_status,
)


def _require_usb():
    if S5ServiceUSB is None:
        raise BypassError(
            "无法导入 s5_unlock_core（pyusb/libusb 不可用）。"
            "请确认 s5_unlock/lib/libusb-1.0.dylib 存在，且已安装 pyusb。"
        )


def _confirm(prompt: str, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise BypassError("非交互环境，请加 --yes")
    ans = input(prompt + " [y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        raise BypassError("已取消")


def _print_status(st) -> None:
    print(format_status(st))


def cmd_status(_args) -> int:
    _require_usb()
    with S5ServiceUSB() as dev:
        _print_status(UpdateBypass(dev).status())
    return 0


def cmd_apply(args) -> int:
    _require_usb()
    mode = args.mode
    if mode == "full":
        prompt = (
            "将写 0x8631801A = 1：关闭 ECDSA 和逐组件 SHA-256。\n"
            "这是 RAM 修改，重启后失效。继续？"
        )
    else:
        prompt = (
            "将写 0x868C704E = 0xE023：跳过 ECDSA，但保留 SHA-256/CRC32。\n"
            "这是指令内存修改；若 I-cache 未刷新可能不生效。重启后失效。继续？"
        )
    if not args.dry_run:
        _confirm(prompt, args.yes)

    with S5ServiceUSB() as dev:
        b = UpdateBypass(dev)
        before = b.status()
        print("--- before ---")
        _print_status(before)
        after = b.apply(mode, dry_run=args.dry_run)
        print("--- after ---")
        _print_status(after)
        if args.dry_run:
            print("(dry-run：未写入)")
        else:
            print("完成。现在去相机里触发 SD 更新；更新完重启即恢复原状。")
    return 0


def cmd_restore(args) -> int:
    _require_usb()
    if not args.dry_run:
        _confirm(
            "将恢复 RAM 里的验签状态（开关写 0，代码写回 0xD021）。继续？",
            args.yes,
        )
    with S5ServiceUSB() as dev:
        b = UpdateBypass(dev)
        print("--- before ---")
        _print_status(b.status())
        after = b.restore(args.mode, dry_run=args.dry_run)
        print("--- after ---")
        _print_status(after)
        if args.dry_run:
            print("(dry-run：未写入)")
    return 0


def cmd_dump(_args) -> int:
    _require_usb()
    with S5ServiceUSB() as dev:
        print(json.dumps(UpdateBypass(dev).dump(), indent=2, ensure_ascii=False))
    return 0


def cmd_self_test(_args) -> int:
    dev = FakeDevice()
    b = UpdateBypass(dev)

    st = b.status()
    assert st.code_raw == CODE_STOCK and st.switch_raw == SWITCH_OFF, st

    b.apply("ecdsa")
    st = b.status()
    assert st.code_raw == CODE_ECDSA_ONLY and st.switch_raw == SWITCH_OFF, st
    assert st.effective.startswith("ecdsa-skip"), st

    b.restore("ecdsa")
    st = b.status()
    assert st.code_raw == CODE_STOCK and st.switch_raw == SWITCH_OFF, st

    b.apply("full")
    st = b.status()
    assert st.switch_raw == SWITCH_ON, st
    assert st.effective.startswith("full-skip"), st

    b.restore("all")
    st = b.status()
    assert st.code_raw == CODE_STOCK and st.switch_raw == SWITCH_OFF, st

    # unknown layout must be refused in all write/restore modes
    bad = UpdateBypass(FakeDevice(code=0x1234, switch=SWITCH_OFF))
    for op_name, op in (
        ("apply ecdsa", lambda: bad.apply("ecdsa")),
        ("apply full", lambda: bad.apply("full")),
    ):
        try:
            op()
        except BypassError:
            pass
        else:
            raise AssertionError(f"unknown code layout was not refused by {op_name}")

    bad_on = UpdateBypass(FakeDevice(code=0x1234, switch=SWITCH_ON))
    try:
        bad_on.restore("switch")
    except BypassError:
        pass
    else:
        raise AssertionError("unknown code layout was not refused by restore switch")

    print("self-test OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="S5 更新验签 RAM 工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="读取当前状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("apply", help="关闭验签")
    p.add_argument("--mode", choices=["full", "ecdsa"], default="full",
                   help="full=官方开关(ECDSA+SHA)，ecdsa=只关ECDSA(保留SHA/CRC)")
    p.add_argument("--dry-run", action="store_true", help="只读，不写")
    p.add_argument("--yes", action="store_true", help="跳过确认")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("restore", help="恢复验签")
    p.add_argument("--mode", choices=["all", "switch", "ecdsa"], default="all")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("dump", help="打印地址上下文")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("self-test", help="离线自检（不需要相机）")
    p.set_defaults(func=cmd_self_test)

    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    try:
        return args.func(args)
    except BypassError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as e:
        # e.g. RuntimeError from S5ServiceUSB when the camera is absent
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
