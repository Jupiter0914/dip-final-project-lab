"""Render POLY04 frozen statistics and selected decoded examples after serial timing finishes."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import zipfile

import cv2
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np

from .analysis import read_rows, write_rows
from .analysis_regions import RegionReference, Layout, independent_decode
from poly02.data import ROOT, read_mask

INK = "#263842"
GREEN = "#167765"
BLUE = "#24729b"
RUST = "#b35735"
MUTED = "#697880"
SOFT = "#c9d4d4"
BG = np.array([248,248,243],np.uint8)
HIT = np.array([56,72,76],np.uint8)
OVER = np.array([212,97,49],np.uint8)
MISS = np.array([40,137,167],np.uint8)
REGION = np.array([159,62,131],np.uint8)
LABEL = {"seed":"合法起点", "within_full":"加强圈内", "cross":"允许跨圈",
         "cgal":"CGAL squared", "cgal_within":"CGAL + 圈内细调",
         "within_old":"旧圈内", "within_full_oldtri":"扩候选/旧三角规则", "exact":"精确整图"}


def style():
    for path in ("C:/Windows/Fonts/msyh.ttc","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(path).is_file():
            font_manager.fontManager.addfont(path)
            plt.rcParams["font.family"]=font_manager.FontProperties(fname=path).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus":False,"axes.labelcolor":INK,"axes.titlecolor":INK,
                         "xtick.color":INK,"ytick.color":INK,"axes.spines.top":False,"axes.spines.right":False,
                         "font.size":10})


def domains(values):
    return sorted(set(values),key=lambda s:(s!="Oxford",s))


def primary(r):
    return (int(r["budget"]),int(r["deadline_ms"]),r["method"],r["baseline"])==(256,100,"cross","within_full")


def signed(v):
    if abs(float(v))<5e-4:return "0"
    return f"{float(v):+.2f}".rstrip("0").rstrip(".")


def primary_figure(output, analysis):
    src=[r for r in read_rows(analysis/"source_pairs.csv")
         if primary(r) and int(r["rings"])>=2 and r["xor_saved"]!=""]
    stability=[r for r in read_rows(analysis/"stability.csv") if primary(r) and r["mean"]!=""]
    deletion=read_rows(analysis/"leave_one_source.csv")
    categories=read_rows(analysis/"category_sensitivity.csv")
    cluster=read_rows(analysis/"cluster.csv")
    dslist=domains(r["dataset"] for r in read_rows(analysis/"coverage.csv"))
    fig,axes=plt.subplots(len(dslist),2,figsize=(11.4,max(3.5,3.55*len(dslist))),squeeze=False,
                          gridspec_kw={"width_ratios":[1.22,1]})
    for i,ds in enumerate(dslist):
        left,right=axes[i]
        rs=sorted((r for r in src if r["dataset"]==ds),key=lambda r:(float(r["xor_saved"]),r["id"]))
        left.set_title(f"{ds}  ·  {len(rs)} 个共同成功多圈源",loc="left",fontsize=12,fontweight="bold")
        left.axhline(0,color=INK,lw=.8)
        if rs:
            score=np.asarray([float(r["xor_saved"]) for r in rs])
            x=np.arange(1,len(score)+1)
            left.vlines(x,0,score,colors=[GREEN if v>0 else RUST for v in score],lw=1.15)
            left.scatter(x,score,s=12 if len(rs)>30 else 29,c=[GREEN if v>0 else RUST if v<0 else MUTED for v in score],zorder=3)
            left.axhline(score.mean(),color=BLUE,lw=1,ls="--")
            left.text(.02,.96,f"源均值 {signed(score.mean())} px",transform=left.transAxes,va="top",color=BLUE,
                      bbox=dict(facecolor="white",edgecolor="none",alpha=.85,pad=1.5))
            left.set_xlim(.35,len(score)+.65)
            if len(score)<=12:left.set_xticks(x)
        else:
            left.text(.5,.52,"无共同成功的多圈源",ha="center",transform=left.transAxes)
        left.set_ylabel("圈内错分 − 跨圈错分（像素）")
        left.set_xlabel("原始源，按源内平均差值排序")
        left.grid(axis="y",alpha=.15)
        by={r["analysis"]:r for r in stability if r["dataset"]==ds}
        entries=[]
        def add_interval(title,r,color=INK):
            if r and r.get("mean","")!="":
                entries.append((title+"  n="+str(r.get("n",r.get("sources",""))),
                                float(r["mean"]),float(r["lo"]),float(r["hi"]),color))
        add_interval("全部配对",by.get("all_common"),GREEN)
        for tag in sorted(v for v in by if v.startswith("session/")):add_interval(tag.split("/",1)[1],by[tag],BLUE)
        add_interval("全重复成功",by.get("fully_paired_repeats"),MUTED)
        c=[float(r["mean_without"]) for r in deletion if r["dataset"]==ds]
        if c:entries.append(("删一源均值范围",None,min(c),max(c),RUST))
        if ds!="Oxford":
            cl=next((r for r in cluster if r["dataset"]==ds),None)
            if cl:add_interval(f"整类重抽（{cl['categories']} 类）",cl,"#76508c")
            drop=[float(r["mean_without_category"]) for r in categories if r["dataset"]==ds and r["mean_without_category"]!=""]
            if drop:entries.append(("删一类均值范围",None,min(drop),max(drop),"#76508c"))
        right.axvline(0,color=INK,lw=.8)
        for j,(label,mean,lo,hi,color) in enumerate(entries):
            right.hlines(j,lo,hi,lw=1.7,color=color)
            right.plot([lo,hi],[j,j],ls="none",marker="|",color=color,ms=7)
            if mean is not None:right.plot(mean,j,"o",color=color,ms=5)
        right.set_yticks(range(len(entries)),[z[0] for z in entries],fontsize=9)
        right.set_ylim(max(1,len(entries))-.5,-.55)
        right.set_xlabel("源均值与配对 95% 区间（像素）")
        right.set_title("按会话及删除单个源的稳定性",loc="left",fontsize=11)
        right.grid(axis="x",alpha=.15)
    fig.suptitle("跨圈操作的源级增量  ·  256 字节上限 / 实收 100 ms / R≥2",
                 fontsize=15,fontweight="bold",color=INK)
    fig.text(.06,.012,"正值表示允许跨圈时少错。点是一份原始源；仅横线的删减项表示实测敏感性范围。",fontsize=9,color=MUTED)
    fig.tight_layout(rect=(0,.044,1,.945),h_pad=2.05,w_pad=2.2)
    fig.savefig(output/"primary-source-sessions.png",dpi=160,facecolor="white");plt.close(fig)


def coverage_figure(output,analysis):
    coverage=read_rows(analysis/"coverage.csv")
    paired=read_rows(analysis/"paired_summary.csv")
    dslist=domains(r["dataset"] for r in coverage)
    order=("seed","within_full","cross","cgal","cgal_within")
    cov={(r["dataset"],int(r["budget"]),int(r["deadline_ms"]),r["method"]):r for r in coverage if r["scope"]=="all"}
    effects={(r["dataset"],int(r["deadline_ms"]),r["baseline"]):r for r in paired if int(r["budget"])==256 and
             r["scope"]=="R2+" and r["method"]=="cross" and r["metric"]=="xor_saved"}
    fig,axes=plt.subplots(len(dslist),2,figsize=(11.4,max(3.7,3.45*len(dslist))),squeeze=False,
                          gridspec_kw={"width_ratios":[1,1.25]})
    for idx,ds in enumerate(dslist):
        ax,bx=axes[idx]
        shown=[m for m in order if any((ds,256,t,m) in cov for t in (100,200))]
        for y,m in enumerate(shown):
            ends=[float(cov[ds,256,t,m]["coverage_pct"]) if (ds,256,t,m) in cov else np.nan for t in (100,200)]
            ax.plot(ends,[y-.10,y+.10],color=SOFT,lw=1.5,zorder=1)
            for t,v,dy,col,mark in zip((100,200),ends,(-.10,.10),(BLUE,GREEN),("o","D")):
                if np.isfinite(v):
                    ax.plot(v,y+dy,ls="",marker=mark,color=col,ms=5.5,zorder=2)
        ax.set_yticks(range(len(shown)),[LABEL[m] for m in shown]);ax.invert_yaxis()
        observed=[float(cov[ds,256,t,m]["coverage_pct"]) for m in shown for t in (100,200) if (ds,256,t,m) in cov]
        if observed:
            low=max(0,min(92,np.floor(min(observed)/5)*5-3));ax.set_xlim(low,101)
        number=next((r["sources"] for r in coverage if r["dataset"]==ds and r["method"]=="cross" and
                     int(r["budget"])==256 and r["scope"]=="all"),"0")
        ax.set_title(f"{ds}  ·  全部 {number} 个源的交付率",loc="left",fontsize=12,fontweight="bold")
        ax.set_xlabel("截止前收到合格文件（%）");ax.grid(axis="x",alpha=.17)
        comparison=[m for m in ("within_full","seed","cgal","cgal_within") if any((ds,t,m) in effects for t in (100,200))]
        positions=[];yt=[]
        for y,m in enumerate(comparison):
            counts=[]
            for t,dy,col,mark in [(100,-.12,BLUE,"o"),(200,.12,GREEN,"D")]:
                row=effects.get((ds,t,m))
                if row is None:
                    counts.append("—");continue
                mean,lo,hi=map(float,(row["mean"],row["lo"],row["hi"]))
                counts.append(row["n_sources"]);positions.extend((mean,lo,hi))
                bx.hlines(y+dy,lo,hi,color=col,lw=1.4)
                bx.plot(mean,y+dy,ls="",marker=mark,color=col,ms=5)
            yt.append(f"{LABEL[m]}  {counts[0]}/{counts[1]}")
        largest=max((abs(v) for v in positions),default=0)
        if largest>=90:bx.set_xscale("symlog",linthresh=10,linscale=1.0)
        bx.axvline(0,lw=.9,color=INK)
        bx.set_yticks(range(len(comparison)),yt,fontsize=9);bx.invert_yaxis()
        bx.set_title("跨圈相对各对照的面积误差",loc="left",fontsize=11)
        bx.set_xlabel("对照 XOR − 跨圈 XOR（像素）"+("，对称对数轴" if largest>=90 else ""))
        bx.grid(axis="x",alpha=.16)
    fig.legend(handles=[Line2D([],[],ls="none",marker="o",color=BLUE,label="100 ms"),
                        Line2D([],[],ls="none",marker="D",color=GREEN,label="200 ms")],
               ncol=2,frameon=False,loc="lower center",bbox_to_anchor=(.50,.035))
    fig.suptitle("完整方法的交付率与条件质量  ·  256 字节上限",fontsize=15,fontweight="bold",color=INK)
    fig.text(.05,.011,"右图只比较共同成功的 R≥2 源。对照名后的两个数为 100/200 ms 的共同源数；线段为源级配对 95% 区间。",fontsize=9,color=MUTED)
    fig.tight_layout(rect=(0,.095,1,.948),h_pad=2,w_pad=2.3)
    fig.savefig(output/"delivery-and-baselines.png",dpi=160,facecolor="white");plt.close(fig)
    byrate=sorted({int(r["budget"]) for r in coverage})
    if len(byrate)<=1:return
    fig,axes=plt.subplots(len(dslist),len(byrate),figsize=(4.1*len(byrate),max(3,2.95*len(dslist))),squeeze=False)
    for i,ds in enumerate(dslist):
        for j,b in enumerate(byrate):
            ax=axes[i,j]
            methods=[m for m in order if any((ds,b,t,m) in cov for t in (100,200))]
            for y,m in enumerate(methods):
                for t,dy,col,mark in [(100,-.10,BLUE,"o"),(200,.10,GREEN,"D")]:
                    r=cov.get((ds,b,t,m))
                    if r:ax.plot(float(r["coverage_pct"]),y+dy,marker=mark,ls="",color=col,ms=5)
            ax.set_yticks(range(len(methods)),[LABEL[m] for m in methods],fontsize=8);ax.invert_yaxis()
            ax.set_xlim(-2,102);ax.set_xlabel("源等权交付率（%）")
            denom={r["sources"] for key,r in cov.items() if key[0]==ds and key[1]==b and key[3] in methods}
            ax.set_title(f"{ds}  ·  {b} B  ·  n={'/'.join(sorted(denom,key=int))}",fontsize=11)
            ax.grid(axis="x",alpha=.17)
    fig.legend(handles=[Line2D([],[],marker="o",ls="",color=BLUE,label="100 ms"),Line2D([],[],marker="D",ls="",color=GREEN,label="200 ms")],
               loc="lower center",ncol=2,frameon=False)
    fig.tight_layout(rect=(0,.065,1,1),w_pad=1.2,h_pad=1.8)
    fig.savefig(output/"coverage-by-rate.png",dpi=150,facecolor="white");plt.close(fig)


def error_map(raw,pred):
    img=np.empty((*raw.shape,3),np.uint8)
    img[:]=BG;img[(raw!=0)&(pred!=0)]=HIT;img[pred>raw]=OVER;img[pred<raw]=MISS
    return img


def max_window(signal,side):
    h,w=signal.shape
    side=max(1,min(int(side),h,w))
    integral=cv2.integral(signal.astype(np.uint8),sdepth=cv2.CV_32S)
    all_windows=integral[side:,side:]+integral[:-side,:-side]-integral[side:,:-side]-integral[:-side,side:]
    y,x=np.unravel_index(all_windows.argmax(),all_windows.shape)
    if not signal.any():x,y=(w-side)//2,(h-side)//2
    return int(x),int(y),side


def region_window(region,signal):
    y,x=np.nonzero(region)
    if not len(x):raise ValueError("Reference region unavailable for case")
    h,w=region.shape
    extent=max(int(x.max()-x.min()+1),int(y.max()-y.min()+1))
    if extent<.50*min(h,w):
        side=min(h,w,max(20,round(1.35*extent)))
        cx=(int(x.min())+int(x.max()))//2;cy=(int(y.min())+int(y.max()))//2
        return int(np.clip(cx-side//2,0,w-side)),int(np.clip(cy-side//2,0,h-side)),side
    if not np.any(signal):signal=region
    return max_window(signal,min(h,w,max(30,min(h,w)//3)))


def contour_overlay(image,region):
    padded=(region.astype(np.uint8))
    edge=cv2.morphologyEx(padded,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8)).astype(bool)
    out=image.copy();out[edge]=REGION
    return out


def structure_case(ds,region_cases,source_worst,per,absolute=False):
    available=[r for r in region_cases if r["dataset"]==ds]
    for tag in ("severe_new_small_and_lower_coverage","lower_small_region_coverage","lower_region_coverage"):
        row=next((r for r in available if r["reason"]==tag),None)
        if row and not absolute:return {**row,"why":"structure_conflict"}
    # With no paired conflict, the previously specified worst absolute area ratio is a diagnostic only.
    worst=[r for r in available if r["reason"]=="worst_observed_reference_area_ratio"]
    if not worst:return None
    row=min(worst,key=lambda r:(float(r["method_area_ratio"]),r["id"],r["kind"]))
    if absolute and float(row["method_area_ratio"])>=.5:return None
    full=next((r for r in source_worst if r["dataset"]==ds and r["id"]==row["id"] and r["kind"]==row["kind"]
               and r["method"]=="cross" and (int(r["budget"]),int(r["deadline_ms"]))==(256,100)),None)
    if full is None:return None
    a=next((z for z in per if z["dataset"]==ds and z["id"]==row["id"] and z["method"]=="cross"
            and (int(z["budget"]),int(z["deadline_ms"]))==(256,100) and z["status"]=="success"
            and z["sha256"]==full["worst_ratio_file"]),None)
    if a is None:raise ValueError("Worst structure source trace missing")
    b=next((z for z in per if z["dataset"]==ds and z["id"]==row["id"] and z["method"]=="within_full" and
            (int(z["budget"]),int(z["deadline_ms"]),z["session"],z["rep"])==(256,100,a["session"],a["rep"])),None)
    return dict(**{k:row[k] for k in ("dataset","id","kind","reference_id","reference_area")},why="absolute_structure",
                method="cross",baseline="within_full",session=a["session"],rep=a["rep"],method_sha256=a["sha256"],
                baseline_sha256=(b["sha256"] if b is not None and b["status"]=="success" else ""),actual_bytes=a["actual_bytes"])


def largest_source_case(ds,published,per):
    scores=next((r for r in published if primary(r) and r["dataset"]==ds and r["scope"]=="R2+" and r["metric"]=="xor_saved"),None)
    if not scores or float(scores["best"])<=0:return None
    source=scores["best_id"];avg=float(scores["best"])
    subset={(r["session"],r["rep"],r["method"]):r for r in per if r["dataset"]==ds and r["id"]==source and
            (int(r["budget"]),int(r["deadline_ms"]))==(256,100) and r["status"]=="success"}
    valid=[]
    for (session,rep,method),a in subset.items():
        b=subset.get((session,rep,"within_full"))
        if method=="cross" and b:
            valid.append((abs(int(b["xor"])-int(a["xor"])-avg),session,rep,a,b))
    if not valid:raise ValueError("Maximum source has no shared delivery")
    _,session,rep,a,b=min(valid,key=lambda x:x[:3])
    return dict(why="largest_supplement",dataset=ds,id=source,source_mean_xor_gain=avg,session=session,rep=rep,
                method_sha256=a["sha256"],baseline_sha256=b["sha256"])


def case_figures(output,analysis,folder,stage,settings,archive_path,additional=False):
    if stage=="dev":
        load=read_mask
    else:
        from .data import read_binary as load
    manifest_path=Path(settings["manifest"])
    if not manifest_path.is_absolute():manifest_path=ROOT/manifest_path
    catalog={(r["dataset"],r["id"]):r for r in read_rows(manifest_path)}
    per=read_rows(folder/"per_run.csv")
    metrics={(r["dataset"],r["id"],r["sha256"]):r for r in read_rows(folder/"blob_metrics.csv")}
    case_rows=read_rows(analysis/"cases.csv")
    summaries=read_rows(analysis/"paired_summary.csv")
    region_rows=read_rows(analysis/"regions_cases.csv")
    source_worst=read_rows(analysis/"regions_by_source.csv")
    case_manifest=[]
    with zipfile.ZipFile(archive_path) as archive:
        def fetch(digest):
            if not digest:return None
            b=archive.read(digest+".pm3")
            if hashlib.sha256(b).hexdigest()!=digest:raise ValueError("Case bytes mismatch")
            return independent_decode(b)
        for ds in domains(ds for ds,_ in catalog):
            selected=[]
            by_output={}
            for row in case_rows:
                if row["dataset"]!=ds:continue
                key=(row["id"],row["method_sha256"],row["baseline_sha256"])
                if key in by_output:
                    by_output[key]["why"]+="+"+row["reason"]
                else:
                    record={**row,"why":row["reason"]}
                    selected.append(record);by_output[key]=record
            structural=structure_case(ds,region_rows,source_worst,per)
            if structural:selected.append(structural)
            if additional:
                base_keys={(r["id"],r["method_sha256"],r.get("baseline_sha256","")) for r in selected}
                extra=[]
                winner=largest_source_case(ds,summaries,per)
                if winner and (winner["id"],winner["method_sha256"],winner["baseline_sha256"]) not in base_keys:
                    extra.append(winner)
                severe=structure_case(ds,region_rows,source_worst,per,absolute=True)
                if severe and (not structural or (severe["id"],severe["kind"],severe["reference_id"])!=(structural["id"],structural["kind"],structural["reference_id"])):
                    extra.append(severe)
                selected=extra
            if not selected:continue
            fig,axes=plt.subplots(len(selected),4,figsize=(12,2.35*len(selected)+1.0),squeeze=False,
                               gridspec_kw={"width_ratios":[1.64,1,1,1]})
            for i,heading in enumerate(("源图与该次真实输出","参考前景 / 放大位置","加强圈内 · 解码误差","允许跨圈 · 同一局部")):
                axes[0,i].set_title(heading,fontsize=11,fontweight="bold",color=INK)
            for j,row in enumerate(selected):
                name=row["id"];raw=load(catalog[ds,name]);da=row["method_sha256"];db=row.get("baseline_sha256","")
                a=fetch(da);b=fetch(db)
                ma=metrics[ds,name,da];mb=metrics.get((ds,name,db))
                assert a.shape==raw.shape and int(np.count_nonzero(a!=raw))==int(ma["xor"])
                if b is not None:assert int(np.count_nonzero(b!=raw))==int(mb["xor"])
                global_diff=int(mb["xor"])-int(ma["xor"]) if mb else None
                raw_rgb=error_map(raw,raw)
                source_mean=row.get("source_mean_xor_gain","")
                why=row["why"]
                kinds=why.split("+")
                names={"typical_positive":"典型改善","nearest_zero":"无收益" if source_mean!="" and abs(float(source_mean))<1e-12 else "最接近零",
                       "worst":"最差退化" if source_mean!="" and float(source_mean)<0 else "最小源级变化",
                       "absolute_structure":"最小结构面积比","structure_conflict":"全图少错，局部覆盖下降",
                       "largest_supplement":"源均值改善最大（附例）"}
                title=" / ".join(names[k] for k in kinds)
                card=dict(figure=("cases-additional-" if additional else "cases-")+ds+".png",reason=why,dataset=ds,id=name,budget=256,deadline_ms=100,session=row["session"],rep=row["rep"],
                          method_sha256=da,baseline_sha256=db,actual_bytes=ma["actual_bytes"],
                          method_xor=ma["xor"],baseline_xor=mb["xor"] if mb else "",method_fp=ma["fp"],method_fn=ma["fn"],
                          source_mean_xor_gain=source_mean)
                labels=[(title,True),(f"{name} · {row['session']} / 重复 {row['rep']}",False)]
                if "structure" in why:
                    ref=RegionReference(raw)
                    kind=row["kind"];ri=int(row["reference_id"])
                    layer=ref.layout.fg if kind=="foreground" else ref.layout.bg
                    region=(layer.labels==ri)[1:-1,1:-1]
                    ra=next(v for v in ref.evaluate(a)["components"] if (v["kind"],v["reference_id"])==(kind,ri))
                    rb=next((v for v in ref.evaluate(b)["components"] if (v["kind"],v["reference_id"])==(kind,ri)),None) if b is not None else None
                    la=Layout(a);ma_region=((la.fg if kind=="foreground" else la.bg).labels==ra["decoded_id"])[1:-1,1:-1]
                    if b is not None:
                        lb=Layout(b);mb_region=((lb.fg if kind=="foreground" else lb.bg).labels==rb["decoded_id"])[1:-1,1:-1]
                        change=region & mb_region & ~ma_region
                    else:change=region & ~ma_region
                    x,y,side=region_window(region,change)
                    raw_rgb=contour_overlay(raw_rgb,region)
                    label="前景部件" if kind=="foreground" else "有限孔"
                    labels.append((f"{label} {ri} · 参考面积 {ra['reference_area']} px",False))
                    size_b="未交付" if rb is None else str(rb["decoded_area"])
                    rec_b="—" if rb is None else f"{100*rb['recall']:.3f}%"
                    labels.extend([(f"解码面积 {size_b} → {ra['decoded_area']} px",False),
                                   (f"参考覆盖 {rec_b} → {100*ra['recall']:.3f}%",False)])
                    card.update(kind=kind,reference_id=ri,reference_area=ra["reference_area"],method_region_area=ra["decoded_area"],
                                baseline_region_area=rb["decoded_area"] if rb else "",method_recall=ra["recall"],
                                baseline_recall=rb["recall"] if rb else "")
                else:
                    signal=a!=b if b is not None else a!=raw
                    if not signal.any():signal=a!=raw
                    x,y,side=max_window(signal,max(22,min(raw.shape)//3))
                    labels.append((f"源均值少错 {signed(source_mean)} px",False))
                    if global_diff==0 and abs(float(source_mean))>1e-12:labels.append(("所示重复的错分持平",False))
                labels.append((f"全图错分 {mb['xor'] if mb else '未交付'} → {ma['xor']} px",False))
                desc=axes[j,0]
                for pos,(line,bold) in enumerate(labels):
                    desc.text(0,.86-pos*(.74/max(len(labels)-1,1)),line,transform=desc.transAxes,
                              fontsize=11.4 if bold else 9.2,fontweight="bold" if bold else "normal",color=INK)
                ax=axes[j,1];ax.imshow(raw_rgb,interpolation="nearest")
                ax.add_patch(Rectangle((x-.5,y-.5),side,side,facecolor="none",edgecolor="#a55c35",lw=1.7))
                for col,pred in [(2,b),(3,a)]:
                    ax=axes[j,col]
                    if pred is None:ax.text(.5,.5,"截止前未交付",ha="center",va="center",transform=ax.transAxes)
                    else:ax.imshow(error_map(raw,pred)[y:y+side,x:x+side],interpolation="nearest")
                for ax in axes[j]:ax.axis("off")
                card.update(crop_x=x,crop_y=y,crop_side=side)
                case_manifest.append(card)
            main_title="最大源改善与绝对结构缩水附例" if additional else "固定规则选择的真实解码案例"
            fig.suptitle(f"{ds} · {main_title}",fontsize=15,fontweight="bold",color=INK,y=.991)
            legend=[Patch(color=c/255,label=s) for c,s in [(HIT,"正确前景"),(OVER,"多填 FP"),(MISS,"漏填 FN"),(REGION,"指定参考区域边界")]]
            fig.legend(handles=legend,loc="lower center",bbox_to_anchor=(.54,.006),ncol=4,frameon=False,fontsize=9)
            fig.tight_layout(rect=(0,.047,1,.947),h_pad=.9,w_pad=1.0)
            fig.savefig(output/(("cases-additional-" if additional else "cases-")+ds+".png"),dpi=150,facecolor="white");plt.close(fig)
    return case_manifest


def generate(stage,folder=None,output=None,archive=None,settings=None):
    folder=Path(folder) if folder else ROOT/"results/poly04"/stage
    output=Path(output) if output else folder/"figures"
    archive=Path(archive) if archive else ROOT/"local/poly04"/stage/"outputs.zip"
    if settings is None:settings=json.loads((ROOT/"configs/poly04"/(stage+".json")).read_text(encoding="utf-8"))
    elif not isinstance(settings,dict):settings=json.loads(Path(settings).read_text(encoding="utf-8"))
    analysis=folder/"analysis"
    receipt=json.loads((folder/"receipt.json").read_text(encoding="utf-8"))
    h=hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    if h.hexdigest()!=receipt["outputs_sha256"]:raise ValueError("Whole checkpoint archive differs from gather receipt")
    style();output.mkdir(parents=True,exist_ok=True)
    primary_figure(output,analysis)
    coverage_figure(output,analysis)
    cases=case_figures(output,analysis,folder,stage,settings,archive)
    cases.extend(case_figures(output,analysis,folder,stage,settings,archive,additional=True))
    write_rows(output/"figure-cases.csv",cases)
    print("Figures and case crops saved in",output)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=["dev","confirm"])
    p.add_argument("--folder",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--archive",type=Path)
    p.add_argument("--settings",type=Path)
    a=p.parse_args();generate(a.stage,a.folder,a.output,a.archive,a.settings)
