"""Writes build/version_info.txt for PyInstaller (--version-file), so Windows shows
"Clickue" and the right version in the exe's Properties, Task Manager and the tray settings.

    python scripts/make_version_file.py        -> build/version_info.txt
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
with open(os.path.join(ROOT, "src", "clickue.py"), encoding="utf-8") as f:
    version = re.search(r'^VERSION = "([0-9.]+)"', f.read(), re.M).group(1)
parts = [int(p) for p in version.split(".")][:4]
parts += [0] * (4 - len(parts))
nums = ", ".join(str(p) for p in parts)
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Clickue'),
      StringStruct('FileDescription', 'Clickue'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Clickue'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'Clickue.exe'),
      StringStruct('ProductName', 'Clickue'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
out = os.path.join(ROOT, "build", "version_info.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(text)
print(out)
