# S5 更新验签 RAM 工具

不刷 ROM、不改 `.upd`、不碰 NAND。  
只通过服务模式 USB 读写相机 RAM，把 program 更新器的验签关掉。

> 实验性工具。写 RAM 有风险，先确认相机型号/版本，先用 `status` 读，再写。

## 两种模式

### full / 官方开关（推荐，最稳）

```text
物理地址 0x8631801A
0x0000 -> 0x0001
```

这是固件自带的跳签开关。program 更新器读到 1 后：

- 跳过 ECDSA；
- 跳过逐组件 SHA-256；
- 外层 CRC32 仍由包本身决定，不在这个开关里。

只写数据，不涉及指令缓存，所以最稳。

### ecdsa / 只关 ECDSA（保留 SHA-256 + CRC32）

```text
物理地址 0x868C704E
0xD021 -> 0xE023
```

反汇编：

```asm
; 原始
068c704e: 21 d0    beq #0x068c7094
; 修改后
068c704e: 23 e0    b   #0x068c7098
```

效果：

- 所有更新容器都跳过 ECDSA；
- `verify_enabled` 仍为 1；
- 逐组件 SHA-256 继续强制校验；
- 外层 CRC32 路径不动。

注意：这是改指令内存。如果 CPU 已经缓存了那一行，可能需要让更新器重新加载/重启后才看到新指令。full 模式没有这个问题。

## 连接

1. 相机进入服务模式：`PLAY + AF-ON` 同时按住开机；
2. USB 连接 Mac；
3. 确认系统能看到 `04DA:2370`；
4. 运行工具。

## GUI

双击 `run_gui.command`，或者：

```bash
cd /Users/lixiuqi/相机功能验证/s5_update_bypass
python3 bypass_gui.py
```

## CLI

```bash
cd /Users/lixiuqi/相机功能验证/s5_update_bypass

# 读状态
python3 bypass_cli.py status

# 彻底关闭：官方开关（ECDSA + SHA）
python3 bypass_cli.py apply --mode full

# 只关 ECDSA，保留 SHA/CRC
python3 bypass_cli.py apply --mode ecdsa

# 恢复
python3 bypass_cli.py restore

# 看地址上下文
python3 bypass_cli.py dump

# 离线自检，不需要相机
python3 bypass_cli.py self-test
```

写之前会确认；脚本里可以加 `--yes`。`--dry-run` 只读不写。

## 恢复

```bash
python3 bypass_cli.py restore
```

等价于：

- `0x8631801A` 写回 `0x0000`；
- `0x868C704E` 写回 `0xD021`。

重启相机也会恢复原状，因为只改 RAM。

## 版本保护

工具会先读目标地址：

- `0x868C704E` 不是 `0xD021` / `0xE021` / `0xE023` 时，拒绝写 `ecdsa` 模式；
- `0x8631801A` 不是 `0x0000` / `0x0001` 时，拒绝写 `full` 模式。

这样版本/地址不匹配时不会盲写。

## 边界

- 只覆盖 **program 更新器** 这一层；
- 如果 bootloader/loader 还有独立验签，本工具管不到；
- 外层 CRC32 不是签名，工具不关它；改包后仍要重算 CRC32；
- `full` 模式连逐组件 SHA-256 一起跳过，`ecdsa` 模式保留；
- 只写 RAM，**重启失效**，不会持久化到 NAND。

## 文件

| 文件 | 用途 |
|---|---|
| `bypass_core.py` | 地址、状态、读写逻辑 |
| `bypass_cli.py` | 命令行工具 |
| `bypass_gui.py` | 图形界面 |
| `run_gui.command` | macOS 双击启动 GUI |
| `README.md` | 本文件 |

## 自检

```bash
python3 bypass_cli.py self-test
```

不连接相机，用内存假设备验证状态机、写入、恢复、版本拒绝。

## 离线测试

不需要相机：

```bash
cd /Users/lixiuqi/相机功能验证/s5_update_bypass
python3 bypass_cli.py self-test
python3 test_gui_offline.py
python3 test_gui_mainloop.py
```

三个都通过才说明状态机、GUI 读写、关窗后日志都正常。

## 打包

### macOS .app

```bash
cd s5_update_bypass
python3 -m venv .build-venv
.build-venv/bin/pip install pyinstaller pyusb libusb-package
PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache" \
  .build-venv/bin/python -m PyInstaller --noconfirm --clean S5UpdateBypass.spec
```

产物：`dist/S5UpdateBypass.app`

### Windows .exe

不能在 macOS 上交叉编译。把 `s5_update_bypass/` 和 `s5_unlock/` 一起放到 Windows，双击：

```text
s5_update_bypass\build_windows.bat
```

产物：`s5_update_bypass\dist\S5UpdateBypass.exe`

或者用 GitHub Actions：`.github/workflows/build-s5-update-bypass.yml`，手动运行后下载 `S5UpdateBypass-Windows` artifact。

### 发布包

`release/` 里已有：

- `S5UpdateBypass.app` / `S5UpdateBypass-macOS-arm64.zip`
- `S5UpdateBypass.exe`（Windows x86-64 单文件）
- `S5UpdateBypass-Windows-build.zip`（Windows 构建包）
- `README.md`（发布说明）
