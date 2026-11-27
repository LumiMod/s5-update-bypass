# -*- mode: python ; coding: utf-8 -*-
import os

# Prefer libusb-package (works on Windows/macOS/Linux and is the source of
# truth in CI). Fall back to the repo's bundled macOS dylib for local builds.
_libusb = os.path.abspath(os.path.join(SPECPATH, "..", "s5_unlock", "lib", "libusb-1.0.0.dylib"))
try:
    import libusb_package

    _libusb = str(libusb_package.get_library_path())
except Exception:
    pass


a = Analysis(
    ['bypass_gui.py'],
    pathex=['../s5_unlock'],
    binaries=[],
    datas=[(_libusb, 'lib')],
    hiddenimports=['s5_unlock_core', 'usb', 'usb.backend.libusb1'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='S5UpdateBypass',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='S5UpdateBypass',
)
app = BUNDLE(
    coll,
    name='S5UpdateBypass.app',
    icon='assets/icon.icns',
    bundle_identifier='com.local.s5updatebypass',
)
