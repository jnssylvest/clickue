"""Screen-watcher scenarios (seen/gone/flicker/scaling/look-alikes/retries). Expect: RESULT 61/61"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_helpers.py")).read())
import time, threading, queue, tempfile, random
d=tempfile.mkdtemp(); ac.DATA_DIR=d; ac.SETTINGS_PATH=d+"/s.json"; ac.JOBS_PATH=d+"/j.json"; ac.LOG_PATH=d+"/a.log"
A=object.__new__(ac.App); A.lock=threading.RLock(); A.logq=queue.Queue(); A.wait_msgs={}; A.res_warned=set(); A.tray=None; A.uninstalled=False
A.settings=dict(ac.DEFAULT_SETTINGS); A.jobs=[]; A.setup_logging(); A.own_visible=False
ac.screen_available=lambda:True; ac.idle_seconds=lambda:100; ac.system_dpi=lambda:96
clicks=[]; ac.do_click=lambda x,y,*a,**k:(clicks.append((x,y)) or (True,"ok"))
def scene(scale=1.0, kind="ok", W=1920, H=1080, ox=200, oy=150):
    img,_=draw_app(scale,W,H,ox,oy); dd=ImageDraw.Draw(img); f=lambda v:int(round(v*scale))
    bx,by=ox+f(520),oy+f(380)
    col,txt={"ok":((22,163,74),"● CONNECTED"),"red":((200,40,40),"✖ OFFLINE"),"text":((22,163,74),"● CONNECTING"),"gone":(None,None)}[kind]
    if col: dd.rounded_rectangle((bx,by,bx+f(160),by+f(30)),radius=f(6),fill=col); dd.text((bx+f(12),by+f(6)),txt,fill="white",font=F(f(13)))
    return img,(bx+f(80),by+f(15))
img,(cx,cy)=scene(); crop=img.crop((cx-90,cy-20,cx+90,cy+20))
ac.grab_screen=lambda move_cursor=True:(img,(0,0))
_,(rx,ry)=draw_app(1.0,1920,1080,200,150)
snap,spot,_=ac.capture_snapshot(rx,ry,"Medium")
w=ac.new_watch(1); w.update(watch_png=ac.img_to_b64(crop),x=rx,y=ry,snap_png=ac.img_to_b64(snap),snap_spot=list(spot),pick_dpi=96,watch_delay_min_s=0,watch_delay_max_s=0)
A.jobs.append(w); A.start_job(w)
def show(img): ac.grab_screen=lambda move_cursor=True,img=img:(img,(0,0))
def check(): w["next_check"]=0; A.watch_check(w)
def tick():
    if w.get("pending_click_at"): w["pending_click_at"]=0; A.watch_click(w)
res=[]
def expect(name,cond,info=""): res.append(cond); print(f"{'PASS' if cond else 'FAIL'}  {name}  {info}")
show(scene()[0]); check(); expect("1 badge visible -> seen", w["watch_state"]=="seen", w["watch_note"])
show(scene(kind="gone")[0]); check(); expect("2 badge gone, 1st check -> not clicking yet", w["watch_state"]=="missing" and not w["pending_click_at"], w["watch_note"])
show(scene()[0]); check(); expect("3 came back (flicker) -> counter reset", w["miss_count"]==0)
A.own_visible=True; show(scene(kind="gone")[0]); check(); expect("4 AutoClicker window open -> not counted", w["watch_state"]=="unknown", w["watch_note"])
A.own_visible=False; check(); check(); expect("5 missing 2 checks -> click pending", bool(w["pending_click_at"]))
tick(); _,(trx,try_)=draw_app(1.0,1920,1080,200,150); expect("6 clicked the Refresh button", clicks and clicks[-1]==(trx,try_), f"{clicks[-1] if clicks else None} vs {(trx,try_)}")
check(); check(); check(); expect("7 still gone -> no repeat clicks (once-only)", len(clicks)==1 and not w["pending_click_at"], w["watch_note"])
show(scene()[0]); check(); expect("8 picture back -> re-armed", w["armed"] and w["watch_state"]=="seen")
show(scene(kind="gone")[0]); check(); check(); tick(); expect("9 gone again -> clicks again", len(clicks)==2)
show(scene(kind="red")[0]); w["miss_count"]=0; check(); expect("10 replaced by RED 'OFFLINE' badge -> missing", w["watch_state"]=="missing", w["watch_note"])
show(scene(kind="text")[0]); w["miss_count"]=0; check(); expect("11 text changed to 'CONNECTING' (same size) -> missing", w["watch_state"]=="missing", w["watch_note"])
for sc,W,H in ((1.25,1920,1080),(1.5,2560,1440)):
    show(scene(sc,"ok",W,H)[0]); w["miss_count"]=0; check(); expect(f"12 RDP {sc:.0%} badge visible -> seen", w["watch_state"]=="seen", w["watch_note"])
    show(scene(sc,"red",W,H)[0]); w["miss_count"]=0; check(); expect(f"13 RDP {sc:.0%} red badge -> missing", w["watch_state"]=="missing", w["watch_note"])
    show(scene(sc,"gone",W,H)[0]); w["miss_count"]=0; check(); expect(f"14 RDP {sc:.0%} badge gone -> missing", w["watch_state"]=="missing", w["watch_note"])
show(scene(1.0,"ok",1920,1080,700,500)[0]); check(); expect("15 app window moved -> seen", w["watch_state"]=="seen")
# false positives across unrelated screens
fp=0
for seed in range(10):
    rnd=random.Random(seed); im=Image.new("RGB",(1920,1080),(32,34,38)); dd=ImageDraw.Draw(im)
    for k in range(5):
        x0,y0=rnd.randint(0,1400),rnd.randint(0,700); dd.rectangle((x0,y0,x0+500,y0+350),fill=(240,240,240))
        bx,by=x0+rnd.randint(10,300),y0+rnd.randint(40,300)
        dd.rounded_rectangle((bx,by,bx+160,by+30),radius=6,fill=rnd.choice([(22,163,74),(200,40,40),(40,90,200)])); dd.text((bx+12,by+6),rnd.choice(["● ONLINE","● READY","✖ ERROR","● CONNECTING"]),fill="white",font=F(13))
    show(im); w["miss_count"]=0; check(); fp+=w["watch_state"]=="seen"
expect("16 unrelated screens with similar badges never 'seen'", fp==0, f"{fp}/10")
# click fails then gives up
show(scene(kind="gone")[0]); w["armed"]=True; w["miss_count"]=5; check()
ac.screen_available=lambda:False; tick(); expect("17 can't click (locked) -> waits & retries", bool(w["pending_click_at"]), w["last_result"])
w["pending_since"]=time.time()-99999; tick(); expect("18 gives up after retry time", w["pending_click_at"] is None and "FAILED" in w["last_result"])
ac.screen_available=lambda:True
show(scene()[0]); t=time.time(); check(); t1=time.time()-t
show(scene(1.25)[0]); w["watch_scale"]=None; t=time.time(); check(); t2=time.time()-t; t=time.time(); check(); t3=time.time()-t
print(f"check time: same size {t1:.2f}s; new size first time {t2:.2f}s, after that {t3:.2f}s")
A.v_filter=type("V",(),{"get":lambda s:"all"})()
print("grid row:", A.build_rows(time.time())[0][1][:7])

# ---- 4.5.3: search-area margin, partial matching, mouse pointer on the picture
def ticker(price="123.45", badge="ok", W=1920, H=1080):
    img,_=draw_app(1.0,W,H,200,150); dd=ImageDraw.Draw(img)
    bx,by=720,530
    dd.rectangle((bx-10,by-10,bx+330,by+40),fill=(250,250,250),outline=(180,180,180))
    if badge=="ok": dd.rounded_rectangle((bx,by,bx+160,by+30),radius=6,fill=(22,163,74)); dd.text((bx+12,by+6),"● CONNECTED",fill="white",font=F(13))
    if badge=="red": dd.rounded_rectangle((bx,by,bx+160,by+30),radius=6,fill=(200,40,40)); dd.text((bx+12,by+6),"✖ OFFLINE",fill="white",font=F(13))
    if badge=="hover": dd.rounded_rectangle((bx,by,bx+160,by+30),radius=6,fill=(225,245,230),outline=(22,163,74)); dd.text((bx+12,by+6),"● CONNECTED",fill=(22,163,74),font=F(13))
    dd.text((bx+175,by+6),price,fill=(20,20,20),font=F(14))
    return img,(bx-6,by-6,bx+326,by+36)
im0,box=ticker(); pic=im0.crop(box)
w2=ac.new_watch(2); w2.update(watch_png=ac.img_to_b64(pic),use_image=False,x=5,y=5,watch_delay_min_s=0,watch_delay_max_s=0,watch_random_on=False)
A.jobs.append(w2); A.start_job(w2)
def check2(): w2["next_check"]=0; w2["miss_count"]=0; A.watch_check(w2)
show(im0); check2(); expect("19 ticker box visible (exact) -> seen", w2["watch_state"]=="seen", w2["watch_note"])
w2["watch_area"]=[box[0],box[1],box[2]-box[0],box[3]-box[1]]; w2["watch_area_screen"]=None
check2(); expect("20 search area drawn exactly around the picture -> still seen (margin)", w2["watch_state"]=="seen", w2["watch_note"])
w2["watch_area"]=[box[0]+6,box[1]+4,box[2]-box[0]-12,box[3]-box[1]-8]
check2(); expect("21 search area slightly smaller than the picture -> still seen", w2["watch_state"]=="seen", w2["watch_note"])
show(ticker("98.10")[0]); check2(); expect("22 number inside the box changed, exact -> missing", w2["watch_state"]=="missing", w2["watch_note"])
w2["watch_match"]="partial"; w2["watch_partial_pct"]=75
check2(); expect("23 number changed, partial 75% -> seen", w2["watch_state"]=="seen", w2["watch_note"])
show(ticker("98.10","gone")[0]); check2(); expect("24 badge gone, partial -> missing", w2["watch_state"]=="missing", w2["watch_note"])
show(ticker("123.45","red")[0]); check2(); expect("25 badge turned red, partial -> missing", w2["watch_state"]=="missing", w2["watch_note"])
fp2=0
for seed in range(6):
    rnd=random.Random(100+seed); im=Image.new("RGB",(1920,1080),(32,34,38)); dd=ImageDraw.Draw(im)
    for k in range(5):
        x0,y0=rnd.randint(0,1400),rnd.randint(0,700); dd.rectangle((x0,y0,x0+500,y0+350),fill=(240,240,240))
        bx,by=x0+rnd.randint(10,300),y0+rnd.randint(40,300)
        dd.rounded_rectangle((bx,by,bx+160,by+30),radius=6,fill=rnd.choice([(200,40,40),(40,90,200)])); dd.text((bx+12,by+6),rnd.choice(["● ONLINE","✖ ERROR"]),fill="white",font=F(13))
    show(im); check2(); fp2+=w2["watch_state"]=="seen"
expect("26 partial: unrelated screens never 'seen'", fp2==0, f"{fp2}/6")
w2["watch_match"]="exact"; w2["watch_area"]=None
# mouse pointer resting on the picture: hover look while the pointer is there
hov=ticker(badge="hover")[0]; plain=im0
ac.grab_screen=lambda move_cursor=True:((plain if move_cursor else hov),(0,0))
ac.current_pointer=lambda:(box[0]+40,box[1]+20)
ac.idle_seconds=lambda:0
check2(); expect("27 pointer on the picture, user active -> not counted as gone", w2["watch_state"]=="unknown" and "pointer" in w2["watch_note"], w2["watch_note"])
ac.idle_seconds=lambda:100
check2(); expect("28 pointer on the picture, computer idle -> re-checked without hover -> seen", w2["watch_state"]=="seen", w2["watch_note"])
r=A.watcher_dry_run(dict(w2, main_click=False))
expect("29 dry run re-checks with the pointer moved aside", r["picture"][0] and "moved aside" in r["note"], r["note"])
ac.current_pointer=lambda:(10,1000)
check2(); expect("30 pointer elsewhere, hover look not involved -> normal check", w2["watch_state"]=="missing", w2["watch_note"])
ac.current_pointer=lambda:None; ac.idle_seconds=lambda:100
j3=ac.sanitize_job(dict(ac.new_watch(3), watch_match="fuzzy", watch_partial_pct=3))[0]
expect("31 import: bad match mode/percent cleaned", j3["watch_match"]=="exact" and j3["watch_partial_pct"]==ac.PARTIAL_MIN_PCT, (j3["watch_match"], j3["watch_partial_pct"]))

# ---- 4.5.4: every copy on screen, pixel-exact matching, small pictures, noisy screens
import io as _io, numpy as _np
def card(d,x,y,price,col=(22,163,74),badge="● LIVE"):
    d.rectangle((x,y,x+300,y+70),fill=(250,250,250),outline=(200,200,200))
    d.text((x+10,y+8),"Account card",fill=(20,20,20),font=F(15))
    d.rounded_rectangle((x+10,y+36,x+90,y+60),radius=5,fill=col); d.text((x+18,y+40),badge,fill="white",font=F(12))
    d.text((x+200,y+38),price,fill=(20,20,20),font=F(15))
CPOS=[(100,100),(500,300),(1200,150),(300,700),(1500,800)]
def cards(prices, red=None):
    im=Image.new("RGB",(1920,1080),(32,34,38)); d=ImageDraw.Draw(im)
    for i,((x,y),p) in enumerate(zip(CPOS,prices)):
        card(d,x,y,p,*(((200,40,40),"✖ DOWN") if red==i else ()))
    return im
base=cards(("101.25","98.40","77.10","101.25","5"))
cpic=ac.img_to_b64(base.crop((100,100,401,171)))
def look(im, part=None, hint=None):
    rep=[]; r=ac.picture_on_screen(cpic,hint,shot=(im,(0,0)),report=rep,partial=part)
    return r, sorted((x[0],x[1]) for x in rep if x[6])
r,m=look(base)
expect("32 exact: both identical copies found, never the ones with another number",
       r[0] and m==[(100,100),(300,700)], m)
r,m=look(cards(("55.55","98.40","77.10","12.05","5")))
expect("33 exact: one changed digit anywhere in the box -> not found", not r[0] and not m, (r, m))
r,m=look(base, 0.75)
expect("34 partial 75%: every card found wherever it is, numbers differing", len(m)==5, m)
r,m=look(cards(("101.25","98.40","77.10","101.25","5"), red=2), 0.75)
expect("35 partial: the card whose badge turned red is not counted", (1200,150) not in m and len(m)==4, m)
def jpeg(im,q):
    b=_io.BytesIO(); im.save(b,"JPEG",quality=q); return Image.open(_io.BytesIO(b.getvalue())).convert("RGB")
noisy=Image.fromarray(_np.clip(_np.asarray(base).astype(_np.int16)+_np.random.RandomState(1).normal(0,5,_np.asarray(base).shape).astype(_np.int16),0,255).astype(_np.uint8))
r1,m1=look(jpeg(base,75)); r2,m2=look(noisy)
expect("36 exact copies still found on a compressed or noisy screen (remote sessions)", m1==[(100,100),(300,700)] and m2==m1, (m1,m2))
for scl in (1.25,1.5):
    big=base.resize((int(1920*scl),int(1080*scl)),Image.LANCZOS)
    r,m=look(big)
    expect(f"37 exact at {scl:.0%} display scaling: only the identical copies", r[0] and len(m)==2, m)
icons=Image.new("RGB",(1920,1080),(240,240,240)); di=ImageDraw.Draw(icons); rr=random.Random(3)
for k in range(60):
    x,y=rr.randint(0,1900),rr.randint(0,1060); kind=rr.choice(["down","dot","sq"])
    if kind=="down": di.polygon([(x,y),(x+5,y+10),(x+10,y)],fill=(200,40,40))
    elif kind=="dot": di.ellipse((x,y,x+10,y+10),fill=(22,163,74))
    else: di.rectangle((x,y,x+10,y+10),fill=(22,163,74))
for x,y in ((400,400),(1000,600),(1500,200)): di.polygon([(x,y+10),(x+5,y),(x+10,y+10)],fill=(22,163,74))
ipic=ac.img_to_b64(icons.crop((398,398,413,413)))
rep=[]; r=ac.picture_on_screen(ipic,None,shot=(icons,(0,0)),report=rep)
expect("38 a tiny 15x15 icon: all three copies, none of the 60 other icons", sorted((x[0],x[1]) for x in rep if x[6])==[(398,398),(998,598),(1498,198)], [x[:2] for x in rep if x[6]])

# ---- 4.5.6: pending click re-checked, screen change settles, issues logged every check
logs=[]; _orig_log=A.log
def cap(msg, level="info"):
    logs.append((level,msg)); _orig_log(msg, level)
A.log=cap
show(scene()[0]); w.update(watch_random_on=True, watch_delay_min_s=300, watch_delay_max_s=300, watch_once=False, armed=True, miss_count=0, pending_click_at=None)
show(scene(kind="gone")[0]); check(); check()
expect("39 gone twice -> click pending with a 5 min delay", bool(w["pending_click_at"]) and w["pending_click_at"]-time.time()>250)
n0=len(clicks); show(scene()[0]); check()
expect("40 picture back during the delay -> click cancelled", w["pending_click_at"] is None and "cancelled" in w["last_result"].lower() and len(clicks)==n0, w["last_result"])
show(scene(kind="gone")[0]); check(); check(); w["pending_click_at"]=0
show(scene()[0]); A.watch_click(w)
expect("41 picture back right before the click -> nothing clicked", len(clicks)==n0 and w["pending_click_at"] is None, w["last_result"])
w.update(watch_random_on=False, watch_delay_min_s=0, watch_delay_max_s=0)
_vs=ac.virtual_screen
ac.virtual_screen=lambda:(0,0,1920,1080); show(scene()[0]); check()
ac.virtual_screen=lambda:(0,0,1280,800); show(scene(kind="gone")[0]); check()
expect("42 screen size changed (RDP -> console) -> not counted, settling", w["watch_state"]=="unknown" and w["miss_count"]==0 and "changed" in w["watch_note"], w["watch_note"])
check(); expect("43 still settling -> still not counted", w["miss_count"]==0)
w["settle_until"]=time.time()-1; check()
expect("44 after settling, checks count again", w["miss_count"]==1, w["watch_note"])
ac.virtual_screen=lambda:(0,0,1920,1080); show(scene()[0]); w["miss_count"]=0; check()
expect("44b screen changed back and the picture is there -> 'seen' on the very next check (4.6.1)",
       w["watch_state"]=="seen" and not w.get("settle_until"), (w["watch_state"], w["watch_note"]))
ac.virtual_screen=lambda:(0,0,1280,800); show(scene(1.25,"ok",1920,1080)[0]); check()
expect("44c screen changed and the picture shows at another scale -> seen right away", w["watch_state"]=="seen", w["watch_note"])
ac.virtual_screen=_vs; w["screen_sig"]=None; w["settle_until"]=None
logs.clear(); _sa=ac.screen_available; ac.screen_available=lambda:False
w["issue_count"]=0; check(); check(); check()
cant=[m for l,m in logs if "can't watch" in m.lower()]
expect("45 every check that can't tell is logged (first with what to do)", len(cant)==3 and "What to do" in cant[0], cant[:2])
ac.screen_available=_sa; show(scene()[0]); logs.clear(); check()
expect("46 recovery is logged", any("watching again" in m for l,m in logs), logs)
row=[r for r in A.build_rows(time.time()) if r[0]==w["id"]]
ac.screen_available=lambda:False; check(); row=[r for r in A.build_rows(time.time()) if r[0]==w["id"]][0]
expect("47 a watcher that can't tell shows as a problem in the list", row[2]=="warn" and "Can't" in row[1].cells["status"], (row[2], row[1].cells["status"]))
ac.screen_available=_sa
show(scene(kind="gone")[0]); w["miss_count"]=0; logs.clear(); check()
expect("48 a missing picture is logged with the closest place", any("closest place at (" in m for l,m in logs), logs)
expect("49 log levels: quiet keeps problems, drops routine lines; detailed keeps details",
       ac.log_wanted("quiet","info","[x] CAN'T WATCH: y") and not ac.log_wanted("quiet","info","[x] watching for its picture every 30s")
       and not ac.log_wanted("normal","detail","x") and ac.log_wanted("detailed","detail","x"))
A.log=_orig_log

# ---- 4.6: a watcher that clicks in a window watches the window; Clickue's own windows; times
logs.clear(); A.log=cap
w.update(target_mode="window", window_title="Example App", watch_random_on=True, watch_delay_min_s=300, watch_delay_max_s=300,
         armed=True, miss_count=0, pending_click_at=None, issue_count=0, screen_sig=None, settle_until=None)
_ww=ac.watch_window
ac.watch_window=lambda job:("minimized", None, "Example App")
show(scene(kind="gone")[0]); check(); check()
expect("50 window minimized -> can't watch, NOT 'picture gone', no click", w["watch_state"]=="unknown" and not w["pending_click_at"] and "minimized" in w["watch_note"], w["watch_note"])
ac.watch_window=lambda job:("ok", (0,0,1920,1080), "Example App")
w["issue_count"]=0; check(); check()
expect("51 window back, picture gone twice -> click scheduled", bool(w["pending_click_at"]))
gl=[m for l,m in logs if "click scheduled for" in m]
expect("52 the log says when it was first seen, confirmed and when the click is scheduled", gl and "first seen" in gl[-1] and "confirmed" in gl[-1], gl[-1:] )
ac.watch_window=lambda job:("missing", None, "Example App")
check()
expect("53 window closed during the delay -> click cancelled, nothing clicked", w["pending_click_at"] is None and "cancelled" in w["last_result"].lower(), w["last_result"])
ac.watch_window=lambda job:("ok", (0,0,1920,1080), "Example App")
w["issue_count"]=0; check(); check(); w["pending_click_at"]=0
ac.watch_window=lambda job:("minimized", None, "Example App")
n0=len(clicks); A.watch_click(w)
expect("54 window minimized right before the click -> nothing clicked", len(clicks)==n0 and w["pending_click_at"] is None, w["last_result"])
ac.watch_window=lambda job:("none", None, "")
w.update(target_mode="screen", watch_random_on=False, armed=True, miss_count=0, pending_click_at=None, issue_count=0)
show(scene(kind="gone")[0]); check(); check(); A.watch_click(w)
okl=[m for l,m in logs if "- OK ·" in m]
expect("55 a watcher click logs when it was gone, scheduled and clicked", okl and "gone" in okl[-1] and "clicked" in okl[-1], okl[-1:])
# Clickue's own window over the place: never "found" there
img_own,_=scene(); show(img_own)
_,(ccx,ccy)=scene()
A.own_rects=[(ccx-120, ccy-60, 240, 120)]
r=ac.watched_picture(dict(w, _exclude=A.own_rects))[0]
expect("56 a picture inside Clickue's own window doesn't count as found", not r[0], r)
r=ac.watched_picture(dict(w, _exclude=[(1500,900,100,100)]))[0]
expect("57 Clickue's window elsewhere doesn't hide the real picture", r[0], r)
# 4.6.1: a Clickue window counts only where it is really in front (Windows z-order)
_win,_oot=ac.IS_WIN,ac.own_on_top
ac.IS_WIN=True; ac.own_on_top=lambda x,y:False          # the browser is in front of Clickue
A.own_rects=[(0,0,1920,1080)]                            # Clickue maximized behind it
r=ac.watched_picture(dict(w, _exclude=A.own_rects))[0]
expect("58 Clickue maximized BEHIND the browser doesn't hide the picture", r[0], r)
ac.own_on_top=lambda x,y:True
r=ac.watched_picture(dict(w, _exclude=A.own_rects))[0]
expect("59 Clickue in front of the picture still hides it", not r[0], r)
A.own_visible=True
ac.own_on_top=lambda x,y:False
expect("60 Clickue open behind: a missing picture is counted (not 'can't tell')", not A.own_covers(dict(w, found_xy=[ccx,ccy])))
ac.own_on_top=lambda x,y:True
expect("61 Clickue in front of it: not counted", A.own_covers(dict(w, found_xy=[ccx,ccy])))
show(scene(kind="gone")[0]); w.update(miss_count=0, issue_count=0, found_xy=[ccx,ccy]); check()
expect("62 the problem says Clickue is in front of the picture", w["watch_state"]=="unknown" and "in front" in w["watch_note"], w["watch_note"])
ac.own_on_top=lambda x,y:False; w["issue_count"]=0; check()
expect("63 browser brought back in front: the missing picture counts again", w["watch_state"]=="missing" and w["miss_count"]>=1, w["watch_note"])
ac.IS_WIN,ac.own_on_top=_win,_oot; A.own_visible=False
A.own_rects=[]; ac.watch_window=_ww; A.log=_orig_log
print(f"RESULT {sum(res)}/{len(res)}")
