"""Shared helpers for the headless tests: loads src/clickue.py with tkinter stubbed out
(so it runs without a display) and draws fake app screens for picture matching."""
import os, sys, types
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "clickue.py")
for m in ("tkinter","tkinter.ttk","tkinter.messagebox","tkinter.filedialog","tkinter.font"):
    sys.modules[m]=types.ModuleType(m)
tk=sys.modules["tkinter"]; tk.Toplevel=object; sys.modules["tkinter.ttk"].Frame=object; tk.ttk=sys.modules["tkinter.ttk"]; tk.font=sys.modules["tkinter.font"]
tk.messagebox=sys.modules["tkinter.messagebox"]; tk.filedialog=sys.modules["tkinter.filedialog"]
import importlib.util
spec=importlib.util.spec_from_file_location("ac",SRC); ac=importlib.util.module_from_spec(spec); spec.loader.exec_module(ac)
ac.IS_WIN=False  # the tests fake the screen, mouse and keyboard on every OS (also on Windows CI)
from PIL import Image, ImageDraw, ImageFont
def _font_path():
    for p in ("DejaVuSans.ttf", "arial.ttf", "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            ImageFont.truetype(p, 12)
            return p
        except Exception:
            pass
    raise RuntimeError("no TrueType font found for the test screens")
_FONT = _font_path()
F=lambda sz: ImageFont.truetype(_FONT, max(6,sz))
def draw_app(scale, W, H, ox, oy, dup=False, bg=(32,34,38)):
    img=Image.new("RGB",(W,H),bg); d=ImageDraw.Draw(img); f=lambda v:int(round(v*scale))
    d.rectangle((ox,oy,ox+f(700),oy+f(420)),fill=(240,240,240))
    d.rectangle((ox,oy,ox+f(700),oy+f(30)),fill=(30,90,200)); d.text((ox+f(10),oy+f(6)),"Inventory Manager",fill="white",font=F(f(14)))
    for i,l in enumerate(["New","Open","Save","Refresh","Export","Help"]):
        x=ox+f(10+i*110); y=oy+f(45)
        d.rounded_rectangle((x,y,x+f(100),y+f(32)),radius=f(5),fill=(220,225,235),outline=(150,150,160))
        d.text((x+f(14),y+f(7)),l,fill=(20,20,20),font=F(f(14)))
    for r in range(8):
        d.text((ox+f(15),oy+f(100+r*35)),f"Row {r}: item {r*37%91}  qty {r*13%29}",fill=(60,60,60),font=F(f(13)))
    if dup:
        x=ox+f(340); y=oy+f(370)
        d.rounded_rectangle((x,y,x+f(100),y+f(32)),radius=f(5),fill=(220,225,235),outline=(150,150,160))
        d.text((x+f(14),y+f(7)),"Refresh",fill=(20,20,20),font=F(f(14)))
    return img,(ox+f(10+3*110+50), oy+f(45+16))
