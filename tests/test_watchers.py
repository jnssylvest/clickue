"""Screen-watcher scenarios (seen/gone/flicker/scaling/look-alikes/retries). Expect: RESULT 21/21"""
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
print(f"RESULT {sum(res)}/{len(res)}")
