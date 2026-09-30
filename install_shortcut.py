"""Add the app to the Start Menu so it can be searched for and pinned.

Usage: python install_shortcut.py [--desktop] [--remove]

The shortcut runs main.py with pythonw.exe (no console window) from this
folder, so code and config.py edits take effect the next time it starts.
Pin it by right-clicking it in the Start Menu (or on the running app's
taskbar button) and choosing "Pin to taskbar".
"""
import argparse
import os
import sys
from pathlib import Path

import pythoncom
from win32com.shell import shell
from win32comext.propsys import propsys, pscon

import config
from window import APP_ID, APP_NAME, ICON_FILE


def shortcut_paths(desktop):
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    paths = [start_menu / f"{APP_NAME}.lnk"]
    if desktop:
        paths.append(Path(shell.SHGetFolderPath(0, 0x10, None, 0)) / f"{APP_NAME}.lnk")  # CSIDL_DESKTOPDIRECTORY
    return paths


def create_shortcut(path):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise FileNotFoundError(f"pythonw.exe not found next to {sys.executable}")

    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                      shell.IID_IShellLink)
    link.SetPath(str(pythonw))
    link.SetArguments(f'"{config.BASE_DIR / "main.py"}"')
    link.SetWorkingDirectory(str(config.BASE_DIR))
    link.SetIconLocation(str(ICON_FILE), 0)
    link.SetDescription("Prices Path of Exile 2 Expedition rewards")

    # Same ID the running app sets on itself, so its taskbar button and a pin
    # of this shortcut are the same thing.
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()

    path.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desktop", action="store_true", help="also put a shortcut on the desktop")
    parser.add_argument("--remove", action="store_true", help="delete the shortcuts instead")
    args = parser.parse_args()

    for path in shortcut_paths(args.desktop or args.remove):
        if args.remove:
            if path.is_file():
                path.unlink()
                print(f"Removed {path}")
        else:
            create_shortcut(path)
            print(f"Created {path}")


if __name__ == "__main__":
    main()
