"""Finding a click spot by its picture across sizes, scaling and look-alikes.
Exact matching (default) and tolerant matching are both checked.   Expect: 0 of 48 failures"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_helpers.py")).read())
pick,(px,py)=draw_app(1.0,1280,800,100,80); fails=0; n=0
CASES=((1.0,(1280,800,100,80),False,96),(1.0,(1920,1080,600,300),False,96),(1.25,(1920,1080,400,200),False,120),(1.5,(2560,1440,300,250),False,144),(1.0,(1280,800,100,80),True,96),(1.25,(1920,1080,400,200),True,120),(1.1,(1920,1080,200,200),False,106),(1.75,(2560,1440,100,100),False,168))
for exact in (True, False):
    for size in ("Small","Medium","Large"):
        ac.grab_screen=lambda move_cursor=True:(pick,(0,0)); ac.system_dpi=lambda:96
        snap,spot,_=ac.capture_snapshot(px,py,size)
        job=ac.new_job(); job.update(x=px,y=py,use_image=True,snap_png=ac.img_to_b64(snap),snap_spot=list(spot),pick_dpi=96,exact_match=exact)
        for scale,(W,H,ox,oy),dup,dpi in CASES:
            img,(tx,ty)=draw_app(scale,W,H,ox,oy,dup); ac.grab_screen=lambda move_cursor=True,img=img:(img,(0,0)); ac.system_dpi=lambda dpi=dpi:dpi
            ok,x,y,msg,how=ac.locate_spot(job); err=((x-tx)**2+(y-ty)**2)**.5; n+=1
            # Exact: a Small picture that is on screen twice, identical, and neither copy is where
            # it was picked can't be told apart - it must refuse rather than guess.
            ambiguous = exact and size=="Small" and dup and (ox,oy)!=(100,80)
            good = (not ok and "times" in msg) if ambiguous else (ok and err<=5)
            fails+=not good
            if not good: print("FAIL", "exact" if exact else "tolerant", size, scale, dup, round(err,1), msg or how)
print("click-spot failures:",fails,"of",n)
sys.exit(1 if fails else 0)
