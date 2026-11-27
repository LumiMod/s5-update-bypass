# S5UpdateBypass

Panasonic DC-S5（MC801，V2.9）服务模式 RAM 工具：通过 USB 写 RAM，临时关闭固件更新器的 ECDSA 验签。

> **只写 RAM，不刷 ROM、不改 `.upd`、不碰 NAND。** 重启后恢复原状。  
> 实验性工具，未做真机批量验证。用前先读状态，确认地址值再写。

## 两种模式

| 模式 | 写哪里 | 效果 |
|---|---|---|
| `full`（默认） | `0x8631801A: 0x0000 -> 0x0001` | 官方跳签开关，跳过 ECDSA + 逐组件 SHA-256 |
| `ecdsa` | `0x868C704E: 0xD021 -> 0xE023` | 所有容器跳过 ECDSA，保留 SHA-256/CRC32 |

`ecdsa` 模式改的是指令内存，可能受 I-cache 影响；`full` 只写数据，最稳。

## 下载

在 Releases 里下载：

- `S5UpdateBypass-macOS-arm64.zip` — macOS Apple Silicon
- `S5UpdateBypass.exe` — Windows x86-64 单文件 EXE（已在 Windows runner 上构建并自检）
- `S5UpdateBypass-Windows-build.zip` — Windows 构建包（需要自己构建时的备用）

## 使用

1. 相机进服务模式：`PLAY + AF-ON` 同时按住开机；
2. USB 连接电脑；
3. 打开工具，点「连接相机」；
4. 确认状态：`layout = V2.9`、`code = 0xD021`、`switch = 0x0000`；
5. 选模式，点「一键关闭验签」；
6. 去相机里触发 SD 更新；
7. 更新完点「恢复验签」，或重启。

## 从源码构建

### macOS

```bash
cd s5_update_bypass
python3 -m venv .build-venv
.build-venv/bin/pip install pyinstaller pyusb libusb-package
PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache" \
  .build-venv/bin/python -m PyInstaller --noconfirm --clean S5UpdateBypass.spec
```

产物：`dist/S5UpdateBypass.app`

### Windows

在 Windows 上解压源码，进入 `s5_update_bypass`，双击 `build_windows.bat`。
产物：`dist\S5UpdateBypass.exe`

## 离线自检

不需要相机：

```bash
cd s5_update_bypass
python3 bypass_cli.py self-test
python3 test_gui_offline.py
python3 test_gui_mainloop.py
```

打包后的 app 也可以：

```bash
./dist/S5UpdateBypass.app/Contents/MacOS/S5UpdateBypass --self-test
```

## 边界

- 只覆盖 program 更新器这一层；如果 bootloader/loader 还有独立验签，管不到。
- 外层 CRC32 不是签名，工具不关它；改包后仍要重算 CRC32。
- 只写 RAM，重启失效，不会持久化到 NAND。
- 不包含任何 Panasonic 固件、密钥或签名材料。

## 目录

```text
s5_update_bypass/   工具源码、GUI、CLI、macOS spec、Windows 构建脚本
s5_unlock/          服务模式 USB 传输层（s5_unlock_core.py）
ci/                 GitHub Actions 构建模板（启用时复制到 .github/workflows/）
```

## 说明

- 协议和地址来自对官方固件和真机 RAM 的静态分析；工具只做 RAM 读写。
- 与 Panasonic 无关，非官方工具。
- 使用风险自负；请先备份、先只读、再写。
