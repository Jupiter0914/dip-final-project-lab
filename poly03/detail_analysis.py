"""Summaries, real cases and independent decoded-pixel checks for the detail experiment."""
import argparse
import json
from pathlib import Path
import zipfile

import cv2
import numpy as np
from scipy import ndimage as ndi
from poly02.core import exterior,disk
from poly02.data import ROOT,CFG,rows,save_rows,sha
from poly02.verify import IndependentScore,reference
from src.codec import decode
from .detail_probe import BASE,DetailReference,compare,known_sources,thinning,edt,legacy_blob,read_mask
from .detail_guard import execute

LABEL={"geometry":"返回几何起点","post_xor":"无保护 XOR","post_guard":"BF2","global_only":"全局骨架",
       "site_only":"具体位置","global_skeleton":"BF2 + 全局骨架","site_skeleton":"BF2 + 具体位置"}
PAIRS=[("post_xor","geometry"),("post_guard","geometry"),("global_only","post_xor"),("site_only","global_only"),
       ("site_only","geometry"),("global_skeleton","post_guard"),("site_skeleton","post_guard"),
       ("site_skeleton","global_skeleton"),("site_skeleton","geometry")]
FIELDS=["xor","fp","fn","iou","relative_xor_saved","bf1","bf2","bf3","bf2_2x","bf4_2x","skeleton_lost",
        "skeleton_gained","terminal_lost","terminal_gained","flank_fn","flank_lost","notch_fp","necks_thinner","encode_ms"]


def independent_clearance(support,radius,pair):
    a,b,corridor=pair
    if not (support[a] and support[b]): return -2
    distance=ndi.distance_transform_edt(np.pad(support,1))[1:-1,1:-1]
    obtained=-1
    for level in range(radius+1):
        labels,_=ndi.label((distance>level)&corridor,structure=np.ones((3,3)))
        if labels[a]==0 or labels[a]!=labels[b]: break
        obtained=level
    return obtained


def collect(folder):
    sources={s["id"]:s for s in known_sources()}
    all_rows=[]
    for path in [folder,folder/"standalone"]:
        table=rows(path/"guards.csv")
        with zipfile.ZipFile(path/"polygons.zip") as archive:
            assert archive.testzip() is None and len(archive.namelist())==len(table)
            for name in sources:
                target=reference(read_mask(sources[name]))
                scorer=IndependentScore(target)
                ref=DetailReference(target)
                ref_skel=ref.skeleton
                flank=ndi.binary_dilation(ref.terminal,structure=disk(2)) & (target!=0) & ~ref_skel
                for r in [t for t in table if t["id"]==name]:
                    k=int(r["k"]);method=r["method"]
                    data=archive.read(f"{name}/{k}-{method}.poly")
                    assert sha(data)==r["sha256"] and len(data)==int(r["bytes"])==10+4*k
                    pred=decode(data)
                    vals=scorer.measure(pred)
                    for metric in ("xor","bf1","bf2","bf3"):
                        assert np.isclose(vals[metric],float(r[metric]),rtol=0,atol=1e-12),(name,k,method,metric)
                    gblob=legacy_blob(name,k,"geometry")
                    before=decode(gblob)
                    old=before!=0
                    now=pred!=0
                    lost=old & ~now
                    assert int(lost[ref.skeleton].sum())==int(r["skeleton_lost"])
                    assert int(lost[ref.terminal].sum())==int(r["terminal_lost"])
                    assert int(np.count_nonzero(flank & ~now))==int(r["flank_fn"])
                    assert int(np.count_nonzero(flank & lost))==int(r["flank_lost"])
                    assert sum(int(now[p].sum()) for p in ref.pockets)==int(r["notch_fp"])
                    if ref.necks:
                        weak=broken=0
                        for pg in ref.necks:
                            bval=independent_clearance(target & before,ref.neck_r,pg)
                            aval=independent_clearance(target & pred,ref.neck_r,pg)
                            weak+=bval>=0 and 0<=aval<bval
                            broken+=bval>=0 and aval==-1
                        assert weak==int(r["necks_thinner"]) and broken==int(r["necks_broken"])
                    if method.startswith("site"):
                        assert np.all(pred[ref_skel & (before!=0)]!=0)
                    if method.startswith("global"):
                        assert pred[ref_skel].sum()>=before[ref_skel].sum()
                    if method in ("geometry","post_xor","post_guard"):
                        assert legacy_blob(name,k,method)==data
                    comp=cv2.connectedComponents(pred,connectivity=8)[0]-1
                    holes=cv2.connectedComponents(1-np.pad(pred,1),connectivity=4)[0]-2
                    all_rows.append({**r,"fp":vals["fp"],"fn":vals["fn"],"iou":vals["iou"],"decoded_components":comp,
                                     "decoded_holes":holes,"status":"success"})
    assert len(all_rows)==504
    return all_rows


def summaries(folder,data):
    table={(r["id"],int(r["k"]),r["method"]):r for r in data}
    ids=sorted({r["id"] for r in data})
    summary=[]
    pair_rows=[]
    for key in [16,32,"all"]:
        budgets=(16,32) if key=="all" else (key,)
        for m in LABEL:
            rr=[table[i,k,m] for i in ids for k in budgets]
            v=lambda f:np.array([float(r.get(f) or 0) for r in rr])
            row=dict(k=key,method=m,sources=len(ids),settings=len(rr),bytes_per_setting="74/138" if key=="all" else 10+4*key)
            for field in FIELDS:
                row[field]=float(v(field).mean())
            for field in ("zero_move","branches_long_loss","necks_broken","anchors_disappeared","necks_thinner","skeleton_lost","terminal_lost","skeleton_gained","flank_fn","flank_lost","flank_gained","notch_fp","skeleton_rejected","tile_drops","notches_net4"):
                row["total_"+field]=int(v(field).sum())
                row["settings_"+field]=int((v(field)>0).sum())
                row["sources_"+field]=len({r["id"] for r in rr if float(r.get(field) or 0)>0})
            row.update(bf2_lower=int((v("delta_bf2")< -1e-12).sum()),
                       fixed2_on_2x_lower=int((v("delta_bf2_2x")< -1e-12).sum()),
                       scaled4_on_2x_lower=int((v("delta_bf4_2x")< -1e-12).sum()),
                       changed_settings=sum(r["sha256"]!=table[r["id"],int(r["k"]),"geometry"]["sha256"] for r in rr),
                       median_encode_ms=float(np.median(v("encode_ms"))),p95_encode_ms=float(np.quantile(v("encode_ms"),.95)),
                       mean_setup_ms=float(np.mean(v("setup_ms"))),mean_decode_ms=float(np.mean(v("decode_ms"))))
            summary.append(row)
        bw=np.random.default_rng(3012).integers(len(ids),size=(10000,len(ids)))
        for m,base in PAIRS:
            for field in FIELDS:
                values=np.array([np.mean([float(table[i,k,m][field])-float(table[i,k,base][field]) for k in budgets]) for i in ids])
                lo,hi=np.quantile(values[bw].mean(1),[.025,.975])
                pair_rows.append(dict(k=key,method=m,base=base,metric=field,sources=len(ids),mean=values.mean(),ci_low=lo,ci_high=hi,
                                      lower=int((values< -1e-12).sum()),tied=int((abs(values)<=1e-12).sum()),higher=int((values>1e-12).sum()),
                                      largest_decrease=ids[np.argmin(values)],largest_increase=ids[np.argmax(values)]))
    save_rows(folder/"summary.csv",summary)
    save_rows(folder/"source_paired.csv",pair_rows)


def decode_saved(folder,name,k,m):
    path=folder/"standalone" if m in ("global_only","site_only") else folder
    with zipfile.ZipFile(path/"polygons.zip") as z: return decode(z.read(f"{name}/{k}-{m}.poly"))


def examples(folder,data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle,Patch
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=font).get_name()
    tbl={(r["id"],int(r["k"]),r["method"]):r for r in data}
    sel=[r for r in data if r["method"]=="post_guard"]
    branch=max(sel,key=lambda r:int(r["terminal_run"]))
    notch=max(sel,key=lambda r:int(r["notch_lost"])-int(r["notch_gained"]))
    necktab=[r for r in rows(folder/"features.csv") if r["method"]=="post_guard" and r["kind"]=="neck" and int(r["new_clearance"])>=0]
    neck=max(necktab,key=lambda r:int(r["old_clearance"])-int(r["new_clearance"]))
    choices=[("branch",branch),("notch",notch),("neck",neck)]
    src={r["id"]:r for r in known_sources()}
    out=[]
    fig,axes=plt.subplots(3,5,figsize=(12.7,6.6),gridspec_kw={"width_ratios":[1.21,1,1,1,1]})
    methods=["geometry","post_guard","global_skeleton","site_skeleton"]
    for q,title in zip(axes[0],["输入外圈和位置"]+[LABEL[m] for m in methods]):
        q.set_title(title,fontsize=10)
    for i,(why,r) in enumerate(choices):
        name,k=r["id"],int(r["k"])
        mask,_=exterior(read_mask(src[name]),k)
        ref=DetailReference(mask)
        preds={m:decode_saved(folder,name,k,m) for m in methods}
        target=np.zeros_like(mask,dtype=bool)
        geom,base=preds["geometry"],preds["post_guard"]
        y,x=mask.shape
        neckid=None
        if why=="branch":
            lost=(geom!=0)&(base==0)&ref.terminal
            labs,n=ndi.label(lost,structure=np.ones((3,3)))
            count=np.bincount(labs.ravel());count[0]=0
            yy,xx=np.where(labs==np.argmax(count))
            target=ref.terminal
            radius=7
            message="端枝 / 紫色为参考骨架"
        elif why=="notch":
            for pocket in ref.pockets: target[pocket]=True
            lost=(geom==0)&(base!=0)&target
            score=ndi.uniform_filter(lost.astype(float),size=21)
            loc=np.unravel_index(np.argmax(score),mask.shape)
            yy=np.array([loc[0]]);xx=np.array([loc[1]])
            radius=16
            message="凹口 / 黄色为误填"
        else:
            neckid=int(r["feature"]);a,b,corridor=ref.necks[neckid]
            yy=np.array([a[0],b[0]]);xx=np.array([a[1],b[1]])
            radius=8
            message="细颈 / 同一腐蚀半径"
        side=max(21,int(np.ptp(yy))+2*radius+1,int(np.ptp(xx))+2*radius+1)
        x0=int(np.clip((xx.min()+xx.max()-side)//2,0,max(0,x-side)))
        y0=int(np.clip((yy.min()+yy.max()-side)//2,0,max(0,y-side)))
        sl=(slice(y0,min(y,y0+side)),slice(x0,min(x,x0+side)))
        axes[i,0].imshow(mask,cmap="Greys",vmin=0,vmax=1,interpolation="nearest")
        axes[i,0].add_patch(Rectangle((x0-.5,y0-.5),side,side,fill=False,ec="#ce6b27",lw=1))
        axes[i,0].set_xlabel(name+" · K"+str(k)+"\n"+message,fontsize=8)
        details={}
        for j,m in enumerate(methods,1):
            pred=preds[m]
            rgb=np.zeros((*mask.shape,3),np.uint8)
            rgb[:]=(248,248,242);rgb[(mask==1)&(pred==1)]=(71,86,91)
            rgb[(mask==0)&(pred==1)]=(221,115,56);rgb[(mask==1)&(pred==0)]=(48,147,185)
            if why=="branch":
                rgb[target & (pred!=0)]=(139,65,160)
                rgb[target & (pred==0)]=(238,183,229)
                details[m]=dict(terminal_lost=int(tbl[name,k,m]["terminal_lost"]),flank_fn=int(tbl[name,k,m]["flank_fn"]))
                txt=f"旧端枝点丢失 {details[m]['terminal_lost']}\n侧带漏填 {details[m]['flank_fn']}"
            elif why=="notch":
                rgb[target & (pred!=0)]=(228,155,37)
                details[m]=dict(notch_fp=int(tbl[name,k,m]["notch_fp"]))
                txt=f"全部参考凹口误填 {details[m]['notch_fp']}"
            else:
                a,b,corridor=ref.necks[neckid]
                support=mask&pred
                dt=edt(support)
                level=int(r["old_clearance"])
                eroded=corridor&(dt>level)
                rgb[:]=(248,248,242);rgb[corridor]=(214,219,214);rgb[eroded]=(48,114,95)
                for cy,cx in (a,b): cv2.circle(rgb,(int(cx),int(cy)),3,(166,47,139),-1)
                width=ref.clearance(support,dt,ref.necks[neckid])
                details[m]=dict(max_supported_radius=width,radius_shown=level)
                txt=f"可连接半径 {width} px\n图示腐蚀 {level} px"
            axes[i,j].imshow(rgb[sl],interpolation="nearest")
            axes[i,j].set_xlabel(txt,fontsize=8.1)
        for a in axes[i]:
            a.set_xticks([]);a.set_yticks([])
            for s in a.spines.values(): s.set_visible(False)
        out.append(dict(reason=why,id=name,k=k,x=x0,y=y0,side=side,measures=json.dumps(details,ensure_ascii=False)))
    fig.suptitle("同一全局边界下限下的局部变化",fontsize=14)
    legend=[((71,86,91),"重合前景"),((221,115,56),"多填"),((48,147,185),"漏填"),
            ((139,65,160),"已覆盖参考骨架"),((238,183,229),"未覆盖参考骨架")]
    fig.legend(handles=[Patch(facecolor=np.asarray(color)/255,label=label) for color,label in legend],
               loc="lower center",ncol=5,frameon=False,fontsize=8)
    fig.tight_layout(rect=[0,.045,1,.955],w_pad=.8,h_pad=1.1)
    fig.savefig(folder/"examples.png",dpi=155,bbox_inches="tight")
    plt.close(fig)
    save_rows(folder/"examples.csv",out)


def main():
    p=argparse.ArgumentParser();p.add_argument("--folder",type=Path,default=BASE)
    p.add_argument("--verify-only",action="store_true",help="Check all archived byte streams, key local probes and representative refits without writing")
    a=p.parse_args()
    data=collect(a.folder)
    if not a.verify_only:
        save_rows(a.folder/"decoded.csv",data)
        summaries(a.folder,data)
        examples(a.folder,data)
    chosen=next(s for s in known_sources() if s["id"]=="Sphynx_103")
    cfg=json.loads(CFG.read_text())
    for method in LABEL:
        archive=a.folder/("standalone/polygons.zip" if method in ("global_only","site_only") else "polygons.zip")
        with zipfile.ZipFile(archive) as z:
            expected=z.read(f"{chosen['id']}/16-{method}.poly")
        regenerated,_,_=execute(read_mask(chosen),16,method,cfg)
        assert regenerated==expected
    rows_summary=rows(a.folder/"summary.csv")
    for method in LABEL:
        subset=[r for r in data if r["method"]==method]
        reported=next(r for r in rows_summary if r["method"]==method and r["k"]=="all")
        for key in ("flank_fn","skeleton_lost","xor","necks_thinner"):
            assert abs(np.mean([float(r[key]) for r in subset])-float(reported[key]))<1e-12
    checks=dict(decoded_outputs=len(data),old_geometry_free_bf2_byte_matches=216,originals=36,
                record_sets=["36 Oxford trainval x K16/32"],method_count=len(LABEL),
                scoring="Independent POLY02 numpy masks, independent Euclidean distances vs exact disk dilation",
                protected_sites_redecoded=all(int(r["skeleton_lost"])==0 for r in data if r["method"] in ("site_only","site_skeleton")))
    # Neck detector and width metric must see a true disconnect on a known shape.
    toy=np.zeros((65,100),np.uint8)
    for px in (22,77): cv2.circle(toy,(px,32),15,1,-1)
    toy[30:35,22:78]=1
    ref=DetailReference(toy)
    assert len(ref.necks)>=1
    severed=toy.copy();severed[:,50]=0
    old=ref.clearance(toy,edt(toy),ref.necks[0])
    cut=ref.clearance(severed,edt(severed),ref.necks[0])
    assert old>=1 and cut==-1
    checks.update(synthetic_neck=dict(initial=old,cut=cut),fresh_case_refits=len(LABEL),
                  independent_flank_dilation=True,independent_neck_clearance="SciPy EDT + 8-connected component labels")
    if not a.verify_only:
        (a.folder/"verification.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    print(json.dumps(checks))


if __name__=="__main__": main()
