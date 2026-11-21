"""Fixed selection of development examples and rate/feasibility figures from actual PM31 bytes."""
import json
import zipfile
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,font_manager
from matplotlib.patches import Rectangle,Patch
from .full_data import ROOT,OUT,MANIFEST,REC
from poly02.data import rows,read_mask,save_rows
from .full_verify import parse,paint,components
from .maskcodec import extract,digital
from .allocation import hierarchy

font=Path("C:/Windows/Fonts/msyh.ttc")
if font.is_file():
    font_manager.fontManager.addfont(str(font));plt.rcParams["font.family"]=font_manager.FontProperties(fname=font).get_name()
plt.rcParams["axes.unicode_minus"]=False
BG=(249,248,242);FG=(51,66,68);FP=(207,88,47);FN=(28,137,172)


def rgb(raw,pred):
    im=np.full((*raw.shape,3),BG,np.uint8)
    im[(raw!=0)&(pred!=0)]=FG;im[pred>raw]=FP;im[pred<raw]=FN
    return im


def bitmap(blob):
    shape,rings,_=parse(blob)
    p=np.zeros(shape,np.uint8)
    for r in rings:p^=paint(shape,r)
    return p


def locator(changed,side):
    ii=cv2.integral(np.uint8(changed))
    a=ii[side:,side:]+ii[:-side,:-side]-ii[:-side,side:]-ii[side:,:-side]
    y,x=np.unravel_index(np.argmax(a),a.shape)
    return int(x),int(y)


def figures():
    folder=OUT/"figures";folder.mkdir(exist_ok=True)
    src={s["id"]:s for s in rows(MANIFEST)}
    main=rows(OUT/"per_image.csv")
    tab={(r["id"],int(r["budget"]),r["method"]):r for r in main}
    gains=[]
    for id_ in src:
        a,b=tab[id_,256,"feasible_add"],tab[id_,256,"exchange_whole"]
        if a["status"]==b["status"]=="success" and int(a["xor"])>int(b["xor"]):
            gains.append(((int(a["xor"])-int(b["xor"]))/max(1,int(a["xor"])),id_))
    med=np.median([g for g,_ in gains])
    typical=min(gains,key=lambda s:(abs(s[0]-med),s[1]))[1]
    fail=next(r for r in main if r["method"]=="independent_dp" and r["digital_check"]=="digital_counts" and
              tab[r["id"],int(r["budget"]),"feasible_add"]["status"]=="success")
    selections=[("典型改善",typical,256,"feasible_add","exchange_whole","可行 DP","联合删插"),
                ("整图重排无收益","havanese_26",128,"feasible_add","allocation_whole","可加排序","整图排序"),
                ("原分配丢失结构",fail["id"],int(fail["budget"]),"independent_dp","feasible_add","独立 DP","有序试配")]
    fig,axes=plt.subplots(3,4,figsize=(11,7.2),gridspec_kw={"width_ratios":[1.55,1,1,1]})
    for ax,t in zip(axes[0],["源图与实际文件","完整参考 / 局部位置","对照误差 · 放大","比较方法误差 · 相同坐标"]):ax.set_title(t,fontsize=11)
    cases=[]
    with zipfile.ZipFile(OUT/"outputs.zip") as z:
        for line,(title,name,budget,m1,m2,n1,n2) in enumerate(selections):
            raw=read_mask(src[name]);a,b=tab[name,budget,m1],tab[name,budget,m2]
            old,new=[bitmap(z.read("results/"+r["blob"])) for r in (a,b)]
            weighted=old!=new
            if not np.any(weighted):weighted=raw!=old
            if a["status"]!="success":
                fg,holes,n,h,_=components(raw)
                og,oh,_,_,_=components(old)
                lost=[(fg==i)[1:-1,1:-1] for i in range(1,n+1) if not np.any(og[fg==i])]
                lost.extend((holes==i)[1:-1,1:-1] for i in range(2,h+2) if not np.any(oh[holes==i]>1))
                # Locate the native split: restrict to a missing bridge beside the
                # smaller of two decoded siblings overlapping one reference component.
                for idx in range(1,n+1):
                    overlap=[int(j) for j in np.unique(og[fg==idx]) if j]
                    if len(overlap)>1:
                        piece=min(overlap,key=lambda j:np.count_nonzero(og==j))
                        missing=(cv2.dilate((og==piece).astype(np.uint8),np.ones((5,5),np.uint8))!=0)&(fg==idx)&(og==0)
                        if missing.any():lost.insert(0,missing[1:-1,1:-1])
                if lost:weighted=lost[0]
            side=min(min(raw.shape),max(26,min(raw.shape)//4))
            x,y=locator(weighted,side)
            if a["status"]!="success" and weighted.any():
                yy,xx=np.nonzero(weighted)
                x=int(np.clip(np.median(xx)-side/2,0,raw.shape[1]-side))
                y=int(np.clip(np.median(yy)-side/2,0,raw.shape[0]-side))
            ax=axes[line,0];ax.text(0,.82,title,weight="bold",fontsize=12)
            ax.text(0,.63,f"{name} · 上限 {budget} B",fontsize=9)
            ax.text(0,.46,f"{n1} → {n2}",fontsize=9)
            ax.text(0,.28,f"错分 {a['attempt_xor']} → {b['xor']}",fontsize=9)
            ax.text(0,.10,f"部件/孔 {a['decoded_fg']}/{a['decoded_holes']} → {b['decoded_fg']}/{b['decoded_holes']}",fontsize=9)
            axes[line,1].imshow(rgb(raw,raw),interpolation="nearest")
            axes[line,1].add_patch(Rectangle((x-.5,y-.5),side,side,fill=False,color="#bf642b",lw=1.5))
            for col,p in [(2,old),(3,new)]:axes[line,col].imshow(rgb(raw,p)[y:y+side,x:x+side],interpolation="nearest")
            for aa in axes[line]:aa.axis("off")
            cases.append(dict(reason=title,id=name,budget=budget,baseline=m1,method=m2,base_status=a["status"],status=b["status"],
                       bytes_attempt=a["attempt_bytes"],file_bytes=b["file_bytes"],reference_fg=a["reference_fg"],reference_holes=a["reference_holes"],
                       base_fg=a["decoded_fg"],base_holes=a["decoded_holes"],xor_attempt=a["attempt_xor"],xor=b["xor"],crop_x=x,crop_y=y,crop_side=side))
    fig.legend(handles=[Patch(color=np.array(c)/255,label=s) for c,s in [(FG,"正确前景"),(FP,"多填"),(FN,"漏填")]],loc="lower center",ncol=3,frameon=False)
    fig.tight_layout(rect=(0,.048,1,1));fig.savefig(folder/"full-cases.png",dpi=148);plt.close(fig)
    save_rows(OUT/"cases.csv",cases)
    # Exactly the one structurally admissible nonadditive allocation in the evaluated pool.
    interesting=[r for r in rows(OUT/"allocation_candidates.csv") if r["valid"]=="1" and int(r["cancellation"])>0]
    if interesting:
        c=max(interesting,key=lambda r:int(r["cancellation"]))
        name=c["id"];raw=read_mask(src[name]);dense,par=extract(raw)
        ks=list(map(int,c["counts"].split(",")));error=[]
        for p,k in zip(dense,ks):
            v=next(q for n,q in hierarchy(p,k) if n==k)
            error.append(paint(raw.shape,p)^paint(raw.shape,v))
        mult=np.sum(error,axis=0)
        over=mult>=2;side=min(min(raw.shape),max(42,min(raw.shape)//6))
        yy,xx=np.nonzero(over)
        x=int(np.clip(np.median(xx)-side/2,0,raw.shape[1]-side))
        y=int(np.clip(np.median(yy)-side/2,0,raw.shape[0]-side))
        fig,ax=plt.subplots(1,4,figsize=(9.2,3))
        ax[0].imshow(rgb(raw,raw),interpolation="nearest")
        ax[0].add_patch(Rectangle((x-.5,y-.5),side,side,fill=False,color="#bb6c39",lw=1.5))
        for j,p in enumerate([error[0],error[1],over],1):
            im=np.full((*p.shape,3),BG,np.uint8)
            im[p!=0]=[66,119,133] if j!=3 else [188,72,45]
            ax[j].imshow(im[y:y+side,x:x+side],interpolation="nearest")
        for aa,title in zip(ax,["原始蒙版","外圈错分位置","孔圈错分位置",f"重叠 {int(over.sum())} 个像素"]):aa.set_title(title,fontsize=11);aa.axis("off")
        fig.suptitle(f"{name} · 逐圈合计 {c['additive_xor']}，整图 {c['whole_xor']}",fontsize=14)
        fig.tight_layout(rect=(0,0,1,.9));fig.savefig(folder/"cancellation.png",dpi=150);plt.close(fig)


def transfer_figure():
    from .atomic import replace_vertex
    from .maskcodec import pack,decode
    moves=[r for r in json.loads((OUT/"moves.json").read_text()) if r["method"]=="exchange_whole"]
    chosen=max([r for r in moves if r["donor"]!=r["receiver"]],key=lambda r:r["before"]-r["after"])
    name,b=chosen["id"],chosen["budget"]
    data=next(r for r in rows(OUT/"per_image.csv") if (r["id"],int(r["budget"]),r["method"])==(name,b,"feasible_add"))
    source=next(r for r in rows(MANIFEST) if r["id"]==name)
    raw=read_mask(source)
    with zipfile.ZipFile(OUT/"outputs.zip") as z:
        shape,rings,par=parse(z.read("results/"+data["blob"]))
    for move in [r for r in moves if r["id"]==name and r["budget"]==b]:
        dr,dj,rr,rj,xy=[move[k] for k in ("donor","donor_vertex","receiver","receiver_edge","insert")]
        next_state=replace_vertex(rings,dr,dj,rr,rj,xy)
        if move["round"]==chosen["round"]:break
        rings=next_state
    b0=pack(shape,rings,par);b1=pack(shape,next_state,par)
    masks=[decode(b0),decode(b1)]
    errors=[int((raw!=m).sum()) for m in masks]
    assert errors==[chosen["before"],chosen["after"]] and len(b0)==len(b1)
    donors=np.asarray(rings[dr][dj])/4-1
    receiver=np.asarray(xy)/4-1
    out=OUT/"figures"
    (out/"transfer-before.pm3").write_bytes(b0);(out/"transfer-after.pm3").write_bytes(b1)
    counts=[list(map(len,p)) for p in (rings,next_state)]
    info=dict(id=name,budget=b,bytes=len(b0),counts_before=counts[0],counts_after=counts[1],
              foreground=source["components"],holes=source["holes"],selection="largest strict cross-ring move",**{k:v for k,v in chosen.items() if k not in ("id","budget")})
    (OUT/"transfer.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    fig,axes=plt.subplots(1,3,figsize=(10.5,3.55))
    yy,xx=np.nonzero(raw)
    for i,(ax,ps,title) in enumerate(zip(axes,[None,rings,next_state],["原始完整前景",f"转移前 · 错分 {errors[0]}",f"转移后 · 错分 {errors[1]}"])):
        ax.imshow(np.where(raw,.75,1.),cmap="gray",vmin=0,vmax=1,interpolation="nearest")
        if ps is not None:
            for j,ring in enumerate(ps):
                coords=np.vstack([ring,ring[0]])/4-1
                color="#087866" if j==rr else "#b06036" if j==dr else "#686f71"
                ax.plot(coords[:,0],coords[:,1],color=color,lw=1)
                ax.scatter(coords[:-1,0],coords[:-1,1],s=6,c=color)
        ax.scatter(*donors,marker="x",s=38,c="#af3339",linewidths=1.7)
        ax.scatter(*receiver,marker="o",s=42,facecolors="none",edgecolors="#217247",linewidths=1.5)
        ax.set_xlim(max(-3,xx.min()-12),min(shape[1]+2,xx.max()+12))
        ax.set_ylim(min(shape[0]+2,yy.max()+12),max(-3,yy.min()-12))
        ax.set_title(title,fontsize=10)
        ax.axis("off")
    fig.suptitle(f"{name} · 从一个部件转出一个点，两份文件均为 {len(b0)} 字节",fontsize=13)
    fig.text(.5,.045,f"红叉为删点，绿圈为插点。各圈顶点数 {counts[0]} → {counts[1]}。此例按单次跨圈改善最大选取。",ha="center",fontsize=9)
    fig.subplots_adjust(left=.015,right=.985,bottom=.14,top=.82,wspace=.06)
    fig.savefig(out/"vertex-transfer.png",dpi=160);plt.close(fig)


if __name__=="__main__":
    figures()
    transfer_figure()
