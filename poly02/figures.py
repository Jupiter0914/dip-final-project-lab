"""Source-balanced rate curves, timing comparison and prescribed failure illustrations."""
import json
from pathlib import Path
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,font_manager
from matplotlib.patches import Rectangle,Patch
from src.codec import decode
from .core import exterior
from .demo import display,FG,FP,FN
from .data import ROOT,OUT,REC,CFG,rows,save_rows,read_mask

FONT=Path("C:/Windows/Fonts/msyh.ttc")
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"]=font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams["axes.unicode_minus"]=False
LABEL={"geometry":"几何细调","raster":"直接 XOR","local_iou":"局部 IoU","sm_iou":"SM 删点",
       "post_xor":"几何后 XOR","post_guard":"几何后 XOR + 保护","rdp":"RDP","grid_dp":"网格 DP","full_dp":"全点 DP"}
COLOR={"geometry":"#444e55","raster":"#b87028","local_iou":"#2866af","sm_iou":"#9e627c","post_xor":"#745b9e","post_guard":"#008263"}


def rate_curves(folder):
    sources={r["id"] for r in rows(REC/"samples.csv") if r["curve"]=="1"}
    methods=json.loads(CFG.read_text())["curve_methods"]
    data=[r for s in ("new","curve") for r in rows(OUT/s/"per_image.csv") if r["id"] in sources and r["method"] in methods]
    tab={(r["id"],int(r["k"]),r["method"]):r for r in data}
    ks=sorted({int(r["k"]) for r in data})
    result=[]
    fig,axes=plt.subplots(1,2,figsize=(11,4.7))
    for method in methods:
        scores=[]
        delta=[]
        for k in ks:
            subset=[r for r in data if r["method"]==method and int(r["k"])==k]
            valid=[r for r in subset if (r["id"],k,"geometry") in tab]
            score=np.mean([float(r["iou"]) for r in subset])*100
            gain=np.mean([100*(float(r["iou"])-float(tab[r["id"],k,"geometry"]["iou"])) for r in valid])
            scores.append(score)
            delta.append(gain)
            result.append(dict(k=k,bytes=10+4*k,method=method,n=len(subset),iou_pct=score,iou_gain_pp=gain,
                               bf2=np.mean([float(r["bf2"]) for r in subset]),encode_ms=np.mean([float(r["encode_ms"]) for r in subset])))
        spec=dict(color=COLOR[method],marker="o",lw=2.4 if method=="post_guard" else 1.3,ms=4,label=LABEL[method])
        axes[0].plot(ks,scores,**spec)
        if method not in ("sm_iou","geometry"): axes[1].plot(ks,delta,**spec)
    axes[0].set(title="同一组 25 张照片的码长与质量",ylabel="平均 IoU（%）")
    axes[1].set(title="局部区域方法相对几何细调",ylabel="IoU 变化（百分点）")
    for ax in axes:
        ax.set_xticks(ks)
        ax.set_xlabel("顶点数 K")
        ax.grid(axis="y",alpha=.22)
        ax.spines[["top","right"]].set_visible(False)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,ncol=3,loc="lower center",frameon=False)
    fig.tight_layout(rect=[0,.14,1,1])
    fig.savefig(folder/"quality-by-k.png",dpi=160)
    plt.close(fig)
    save_rows(OUT/"quality-by-k.csv",result)


def cost_plot(folder):
    data={(r["method"],r["k"]):r for r in rows(OUT/"new/summary.csv")}
    methods=list(LABEL)
    fig,(left,right)=plt.subplots(1,2,figsize=(10.6,5),sharey=True)
    for ax,metric,title in [(left,"iou","原尺寸平均 IoU（%）"),(right,"encode_ms","完整编码均时（ms，对数刻度）")]:
        for i,m in enumerate(methods):
            a,b=[float(data[m,k][metric])*(100 if metric=="iou" else 1) for k in ("16","32")]
            ax.plot([a,b],[i,i],color="#bcc6c1",lw=1.2,zorder=0)
            ax.scatter([a],[i],s=32,color="#237458",label="16 点 / 74 B" if not i else None)
            ax.scatter([b],[i],s=34,color="#a65034",marker="D",label="32 点 / 138 B" if not i else None)
        ax.set_xlabel(title)
        ax.grid(axis="x",alpha=.20)
        ax.spines[["top","right"]].set_visible(False)
    left.set_yticks(range(len(methods)),[LABEL[m] for m in methods])
    left.invert_yaxis()
    right.set_xscale("log")
    handles,labels=left.get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",ncol=2,frameon=False,fontsize=9)
    fig.suptitle("200 张新 Oxford 照片，所有方法使用相同 POL1 解码器",fontsize=14)
    fig.tight_layout(rect=[0,.075,1,1])
    fig.savefig(folder/"quality-time.png",dpi=160)
    plt.close(fig)


def case_table():
    records=rows(OUT/"new/per_image.csv")
    by={(r["id"],int(r["k"]),r["method"]):r for r in records}
    keys=sorted({(r["id"],int(r["k"])) for r in records})
    def diff(pair,a,b,key):
        return float(by[*pair,a][key])-float(by[*pair,b][key])
    def relative(pair):
        return -diff(pair,"post_guard","geometry","xor")/max(1,int(by[*pair,"geometry"]["xor"]))
    positive=[x for x in keys if x[1]==16 and relative(x)>0]
    med=np.median([relative(x) for x in positive])
    typical=min(positive,key=lambda x:abs(relative(x)-med))
    degradation=min(keys,key=lambda x:diff(x,"raster","geometry","bf2"))
    rescue=[x for x in keys if diff(x,"post_xor","geometry","bf2")< -1e-12]
    cost=[x for x in keys if int(by[*x,"post_guard"]["boundary_rejected"])>0]
    choices=[("typical",typical,"geometry","post_guard"),("boundary_loss",degradation,"geometry","raster")]
    if rescue: choices.append(("boundary_rescue",max(rescue,key=lambda x:diff(x,"post_guard","post_xor","bf2")),"post_xor","post_guard"))
    if cost: choices.append(("region_cost",max(cost,key=lambda x:diff(x,"post_guard","post_xor","xor")),"post_xor","post_guard"))
    choices.append(("bf1_failure",min(keys,key=lambda x:diff(x,"post_guard","geometry","bf1")),"geometry","post_guard"))
    cases=[]
    for reason,(name,k),before,after in choices:
        res=dict(reason=reason,id=name,k=k,before=before,after=after)
        for prefix,m in [("base",before),("method",after)]:
            for met in ("xor","fp","fn","iou","bf1","bf2","bf3"):
                res[prefix+"_"+met]=by[name,k,m][met]
        cases.append(res)
    return cases


def cases_plot(folder):
    samples={r["id"]:r for r in rows(REC/"samples.csv")}
    cases=case_table()
    labels=dict(typical="典型改善",boundary_loss="直接 XOR 的边界退化",boundary_rescue="保护挡住了退化",region_cost="保护的区域代价",bf1_failure="1 像素边界仍退化")
    fig,axes=plt.subplots(len(cases),4,figsize=(10.4,2.13*len(cases)+.6),gridspec_kw={"width_ratios":[1.6,1,1,1]})
    for ax,title in zip(axes[0],["确认源与变化","外圈 / 放大位置","对照 · 局部误差","候选 · 同一局部"]):
        ax.set_title(title,fontsize=11)
    for line,r in enumerate(cases):
        name,k=r["id"],int(r["k"])
        mask,_=exterior(read_mask(samples[name]),k)
        polys=[decode((ROOT/"local/poly02/new"/name/f"{k}-{r[m]}.poly").read_bytes()) for m in ("before","after")]
        side=max(28,min(mask.shape)//4)
        delta=(polys[0]!=polys[1]).astype(np.uint8)
        ii=cv2.integral(delta,sdepth=cv2.CV_32S)
        areas=ii[side:,side:]+ii[:-side,:-side]-ii[side:,:-side]-ii[:-side,side:]
        y,x=map(int,np.unravel_index(areas.argmax(),areas.shape))
        r.update(crop_x=x,crop_y=y,crop_side=side)
        desc=axes[line,0]
        desc.text(0,.81,labels[r["reason"]],weight="bold",fontsize=12)
        desc.text(0,.61,f"{name} · K={k}",fontsize=9)
        desc.text(0,.43,LABEL[r["before"]]+" → "+LABEL[r["after"]],fontsize=8.5)
        desc.text(0,.24,f"错分 {r['base_xor']} → {r['method_xor']}",fontsize=9)
        if r["reason"]=="bf1_failure":
            desc.text(0,.085,f"BF1 {float(r['base_bf1']):.4f} → {float(r['method_bf1']):.4f}",fontsize=8.5)
            desc.text(0,-.045,f"BF2 {float(r['base_bf2']):.4f} → {float(r['method_bf2']):.4f}",fontsize=8.5)
        else:
            desc.text(0,.06,f"BF2 {float(r['base_bf2']):.4f} → {float(r['method_bf2']):.4f}",fontsize=9)
        axes[line,1].imshow(display(mask),interpolation="nearest")
        axes[line,1].add_patch(Rectangle((x-.5,y-.5),side,side,edgecolor="#b26635",facecolor="none",lw=1.5))
        for col,p in enumerate(polys,2): axes[line,col].imshow(display(mask,p).crop((x,y,x+side,y+side)),interpolation="nearest")
        for ax in axes[line]: ax.axis("off")
    fig.legend(handles=[Patch(color=np.array(c)/255,label=t) for c,t in [(FG,"正确前景"),(FP,"多填"),(FN,"漏填")]],
               ncol=3,loc="lower center",frameon=False)
    fig.tight_layout(rect=[0,.035,1,1])
    fig.savefig(folder/"cases.png",dpi=150)
    plt.close(fig)
    save_rows(OUT/"cases.csv",cases)


if __name__=="__main__":
    folder=OUT/"figures"
    folder.mkdir(exist_ok=True)
    rate_curves(folder)
    cost_plot(folder)
    cases_plot(folder)
