"""Two real examples: improving point continuation and the cheapest observed failed transfer."""
import json
import zipfile
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
import cv2
import numpy as np
from matplotlib import font_manager
from pathlib import Path

if Path("C:/Windows/Fonts/msyh.ttc").exists():
    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams["font.family"]=font_manager.FontProperties(fname="C:/Windows/Fonts/msyh.ttc").get_name()
from src.codec import encode,decode
from poly02.data import REC,rows,save_rows,read_mask,sha
from poly02.verify import reference
from .single import OUT,source_set


def colors(mask,pred):
    rgb=np.empty((*mask.shape,3),np.uint8)
    rgb[:]=(246,246,240)
    rgb[(mask!=0)&(pred!=0)]=(52,72,70)
    rgb[pred>mask]=(213,101,54)
    rgb[pred<mask]=(40,144,176)
    return rgb


def move_figure(folder,catalog):
    r=json.loads((folder/"largest-move.json").read_text(encoding="utf-8"))
    mask=reference(read_mask(catalog[r["id"]]))
    p=np.frombuffer((folder/"largest-before.poly").read_bytes(),offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
    q=np.frombuffer((folder/"largest-after.poly").read_bytes(),offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
    middle=np.delete(p,r["donor"],0)
    old=np.array([r["old_x"],r["old_y"]])
    new=np.array([r["new_x"],r["new_y"]])
    fig,axes=plt.subplots(3,3,figsize=(9.5,8.6),gridspec_kw={"height_ratios":[1.55,1,1]})
    labels=["单点停滞输出","仅删除后的中间状态","删除与插入一起完成"]
    xor=[r["before_xor"],r["deletion_only_xor"],r["after_xor"]]
    for col,v in enumerate((p,middle,q)):
        pred=np.zeros_like(mask)
        cv2.fillPoly(pred,[v],1,lineType=cv2.LINE_8)
        assert np.count_nonzero(mask!=pred)==xor[col]
        ax=axes[0,col]
        ax.imshow(np.where(mask,0.74,1.),cmap="gray",vmin=0,vmax=1,interpolation="nearest")
        closed=np.vstack([v,v[0]])
        ax.plot(closed[:,0],closed[:,1],color="#30474e",lw=1.25)
        ax.scatter(v[:,0],v[:,1],s=9,color="#30474e")
        ax.scatter(*old,s=56,marker="x",color="#b33728",linewidths=2.1,zorder=3)
        ax.scatter(*new,s=65,facecolors="none",edgecolors="#08765f",linewidths=2.1,zorder=3)
        ax.set_xlim(-5,mask.shape[1]+4)
        ax.set_ylim(mask.shape[0]+4,-5)
        ax.set_title(f"{labels[col]}\n{len(v)} 点，错分 {xor[col]} 像素",fontsize=11)
        for row,(pos,caption) in enumerate(((old,"被删顶点附近"),(new,"新插顶点附近")),1):
            side=29
            x=max(0,min(mask.shape[1]-side,int(pos[0])-side//2))
            y=max(0,min(mask.shape[0]-side,int(pos[1])-side//2))
            a=axes[row,col]
            a.imshow(colors(mask,pred)[y:y+side,x:x+side],interpolation="nearest")
            a.set_title(caption,fontsize=8.5,color="#495759")
        for a in axes[:,col]:a.axis("off")
    fig.suptitle(f"真实固定码长删插 · {r['id']} / K={r['k']}",fontsize=15,y=.984)
    fig.text(.5,.078,f"红叉为删除位置 ({old[0]}, {old[1]})，绿圈为插入位置 ({new[0]}, {new[1]})。两端 POL1 都是 {10+4*r['k']} 字节。",ha="center",fontsize=9.5)
    fig.text(.5,.043,f"橙色多填，蓝色漏填。错分按整图统计；最终 BF2 为 {r['after_bf2']:.4f}，几何下限为 {r['floor']:.4f}。",ha="center",fontsize=9)
    fig.subplots_adjust(left=.035,right=.965,top=.89,bottom=.12,hspace=.3,wspace=.1)
    fig.savefig(folder/"device5-move.png",dpi=155,facecolor="white")
    plt.close(fig)


def main():
    catalog={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"] in ("dev","cross")}
    measurements=rows(OUT/"quota/per_image.csv")
    positive=[r for r in measurements if r["method"]=="point" and int(r["saved"])>0]
    median=np.median([float(r["saved"])/int(r["start_xor"]) for r in positive])
    typical=min(positive,key=lambda r:(abs(float(r["saved"])/int(r["start_xor"])-median),r["id"],int(r["k"])))
    keep=next(r for r in measurements if r["method"]=="keep" and r["id"]==typical["id"] and r["k"]==typical["k"])
    audit=OUT/"cost_audit"
    real=json.loads((audit/"real_case.json").read_text())
    shape=tuple(real["shape"])
    before=encode(shape,np.array(real["stationary"],np.int32))
    after=encode(shape,np.array(real["final_trial"],np.int32))
    (audit/"real-stationary.poly").write_bytes(before)
    (audit/"real-rejected-trial.poly").write_bytes(after)
    with zipfile.ZipFile(OUT/"polygons.zip") as z:
        records=[dict(title="Continuing point descent",id=typical["id"],k=int(typical["k"]),
                      before=z.read(keep["file"]),after=z.read(typical["file"]),status="accepted point search"),
                 dict(title="Best enumerated atomic transfer",id=real["id"],k=real["k"],before=before,after=after,status="rejected atomic trial")]
    winner_records=[]
    mpeg=OUT/"mpeg"
    with zipfile.ZipFile(OUT/"polygons.zip") as pack:
        for r in rows(mpeg/"per_image.csv"):
            if not int(r["saved"]): continue
            mask=reference(read_mask(catalog[r["id"]]))
            b=pack.read(r["stationary_file"]); a=pack.read(r["file"])
            p=np.frombuffer(b,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            q=np.frombuffer(a,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            prev={tuple(v) for v in p}; nxt={tuple(v) for v in q}
            removed=next(iter(prev-nxt)); added=next(iter(nxt-prev))
            i=next(i for i,v in enumerate(p) if tuple(v)==removed)
            pos=next(j for j,v in enumerate(q) if tuple(v)==added)
            e=next(j for j,v in enumerate(p) if tuple(v)==tuple(q[pos-1]))
            cut=np.delete(p,i,axis=0)
            intermediate=np.zeros_like(mask)
            cv2.fillPoly(intermediate,[cut],1,lineType=cv2.LINE_8)
            insert=np.insert(p,e+1,added,axis=0)
            alone=np.zeros_like(mask);cv2.fillPoly(alone,[insert],1,lineType=cv2.LINE_8)
            from .atomic import replace_vertex
            assert np.array_equal(replace_vertex([p],0,i,0,e,added)[0],q)
            winner_records.append(dict(id=r["id"],k=int(r["k"]),donor=i,edge=e,old_x=int(removed[0]),old_y=int(removed[1]),new_x=int(added[0]),new_y=int(added[1]),
                      before_xor=int(r["stationary_xor"]),deletion_only_xor=int(np.count_nonzero(mask!=intermediate)),insertion_only_xor=int(np.count_nonzero(mask!=alone)),after_xor=int(r["final_xor"]),saved=int(r["saved"]),
                      floor=float(r["bf2_floor"]),after_bf2=float(r["bf2"]),before_sha=sha(b),after_sha=sha(a)))
        first=winner_records[0]
        strict=next((r for r in winner_records if r["deletion_only_xor"]>r["before_xor"]),None)
        top=max(winner_records,key=lambda r:r["saved"])
        chosen=[(first,"first certified exchange"),(top,"largest observed exchange gain")]
        if strict and strict not in (first,top): chosen.append((strict,"worse deletion, improved pair"))
        for record,reason in chosen:
            r=next(r for r in rows(mpeg/"per_image.csv") if r["id"]==record["id"] and int(r["k"])==record["k"])
            records.append(dict(title=reason,id=r["id"],k=int(r["k"]),before=pack.read(r["stationary_file"]),after=pack.read(r["file"]),status="accepted atomic transfer"))
            name=reason.split()[0].strip(",")
            (mpeg/(name+"-before.poly")).write_bytes(pack.read(r["stationary_file"]))
            (mpeg/(name+"-after.poly")).write_bytes(pack.read(r["file"]))
        from .single_profile import independent_scan
        from .single_search import prepare
        from poly02.data import CFG
        cfg=json.loads(CFG.read_text())
        for key,record in (("largest",top),("worse_deletion",strict)):
            if record is None: continue
            r=next(r for r in rows(mpeg/"per_image.csv") if r["id"]==record["id"] and int(r["k"])==record["k"])
            raw=read_mask(catalog[r["id"]])
            mask,_,_,_,floor,_=prepare(raw,int(r["k"]),cfg)
            q=np.frombuffer(pack.read(r["stationary_file"]),offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            certificate=independent_scan(mask,q,floor)
            save_rows(mpeg/(key+"-point-certificate.csv"),certificate)
            (mpeg/(key+"-move.json")).write_text(json.dumps({**record,"certified_slots":len(certificate),
                      "floor_numerator":floor.numerator,"floor_denominator":floor.denominator,
                      "remaining_eligible_point_moves":sum(t["status"]=="eligible" for t in certificate)},indent=2),encoding="utf-8")
            if key=="largest" and strict==top: break
        save_rows(mpeg/"winners.csv",winner_records)
    figure,axes=plt.subplots(len(records),3,figsize=(10,2.8*len(records)))
    case_data=[]
    for line,entry in enumerate(records):
        name,k=entry["id"],entry["k"]
        mask=reference(read_mask(catalog[name]))
        pred1,pred2=decode(entry["before"]),decode(entry["after"])
        side=max(24,min(mask.shape)//5)
        ii=cv2.integral(np.uint8(pred1!=pred2),sdepth=cv2.CV_32S)
        a=ii[side:,side:]+ii[:-side,:-side]-ii[side:,:-side]-ii[:-side,side:]
        y,x=map(int,np.unravel_index(a.argmax(),a.shape))
        axes[line,0].imshow(colors(mask,mask),interpolation="nearest")
        axes[line,0].add_patch(Rectangle((x-.5,y-.5),side,side,fill=False,edgecolor="#ae5928",lw=1.6))
        axes[line,0].set_title(f"{name} / K={k}",fontsize=10)
        label_cn={"accepted point search":"单点后续结果","rejected atomic trial":"被拒绝的删插","accepted atomic transfer":"接受的删插"}
        for col,pred,label in [(1,pred1,"操作前"),(2,pred2,label_cn[entry["status"]])]:
            axes[line,col].imshow(colors(mask,pred)[y:y+side,x:x+side],interpolation="nearest")
            axes[line,col].set_title(f"{label} · 全图错分 {np.count_nonzero(mask!=pred)} 像素",fontsize=10)
        for ax in axes[line]: ax.axis("off")
        case_data.append(dict(id=name,k=k,case=entry["title"],status=entry["status"],
                    before_xor=int(np.count_nonzero(mask!=pred1)),after_xor=int(np.count_nonzero(mask!=pred2)),
                    before_sha=sha(entry["before"]),after_sha=sha(entry["after"]),crop_x=x,crop_y=y,crop_side=side))
    figure.suptitle("单圈开发样例：继续单点、被拒绝的删插与成功的删插",fontsize=14)
    figure.text(.5,.018,"深灰为正确前景，橙色为多填，蓝色为漏填。各行只放大同一位置，错分数量统计整幅图。",ha="center",fontsize=9)
    figure.tight_layout(rect=[0,.05,1,.95])
    figure.savefig(OUT/"cases.png",dpi=150)
    plt.close(figure)
    save_rows(OUT/"cases.csv",case_data)
    move_figure(mpeg,catalog)


if __name__=="__main__":
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.output: OUT=args.output.resolve()
    main()
