"""Finding a click spot by its picture across sizes, scaling and look-alikes. Expect: 0 of 24 failures"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_helpers.py")).read())
pick,(px,py)=draw_app(1.0,1280,800,100,80); fails=0
for size in ("Small","Medium","Large"):
    ac.grab_screen=lambda move_cursor=True:(pick,(0,0)); ac.system_dpi=lambda:96
    snap,spot,_=ac.capture_snapshot(px,py,size)
    job=ac.new_job(); job.update(x=px,y=py,use_image=True,snap_png=ac.img_to_b64(snap),snap_spot=list(spot),pick_dpi=96)
    for scale,(W,H,ox,oy),dup,dpi in ((1.0,(1280,800,100,80),False,96),(1.0,(1920,1080,600,300),False,96),(1.25,(1920,1080,400,200),False,120),(1.5,(2560,1440,300,250),False,144),(1.0,(1280,800,100,80),True,96),(1.25,(1920,1080,400,200),True,120),(1.1,(1920,1080,200,200),False,106),(1.75,(2560,1440,100,100),False,168)):
        img,(tx,ty)=draw_app(scale,W,H,ox,oy,dup); ac.grab_screen=lambda move_cursor=True,img=img:(img,(0,0)); ac.system_dpi=lambda dpi=dpi:dpi
        ok,x,y,msg,how=ac.locate_spot(job); err=((x-tx)**2+(y-ty)**2)**.5; fails+=not(ok and err<=5)
        if not(ok and err<=5): print("FAIL", size, scale, round(err,1), msg or how)
print("click-spot failures:",fails,"of 24")
sys.exit(1 if fails else 0)
