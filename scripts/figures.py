"""Make fixed-rule examples and source-level comparison figures from confirmed outputs."""
from pathlib import Path
import cv2
import numpy as np
from matplotlib import pyplot as plt, font_manager
from matplotlib.patches import Rectangle,Patch
from PIL import Image

from study import ROOT,read_csv,save_csv
from src.codec import silhouette,decode

FONT=Path("C:/Windows/Fonts/msyh.ttc")
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"]=font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams["axes.unicode_minus"]=False

DARK="#253343"
TEAL="#19786b"
CORAL="#b44734"
BG=np.array([249,248,244],np.uint8)
AGREE=np.array([56,69,78],np.uint8)
OVER=np.array([218,105,68],np.uint8)
MISS=np.array([52,144,174],np.uint8)


def error_map(mask,pred):
    rgb=np.empty((*mask.shape,3),np.uint8)
    rgb[:]=BG
    rgb[(mask==1)&(pred==1)]=AGREE
    rgb[(mask==0)&(pred==1)]=OVER
    rgb[(mask==1)&(pred==0)]=MISS
    return rgb


def choose_window(changed,side):
    integral=cv2.integral(changed.astype(np.uint8),sdepth=cv2.CV_32S)
    areas=integral[side:,side:]+integral[:-side,:-side]-integral[side:,:-side]-integral[:-side,side:]
    y,x=np.unravel_index(areas.argmax(),areas.shape)
    return int(x),int(y),side


def examples(res,folder,paired,table):
    gains=[p for p in paired if p["k"]=="all" and p["baseline"]=="geometry"]
    value=lambda r:float(r["relative_xor_saved"])
    mid=np.median([value(r) for r in gains])
    stress=max([r for r in table if r["method"]=="raster" and r["k"]=="16"],
               key=lambda r:int(r["xor_pixels"])/int(r["reference_pixels"]))
    chosen=[("最大相对改善",max(gains,key=value)["id"]),("中位附近",min(gains,key=lambda r:abs(value(r)-mid))["id"]),
            ("最差变化",min(gains,key=value)["id"]),("剩余错误最多¹",stress["id"])]
    fig,axes=plt.subplots(4,4,figsize=(10.6,9.2),gridspec_kw={"width_ratios":[1.34,1,1,1]})
    for i,title in enumerate(["确认照片 / 16 点","外形与放大区域","几何目标 · 局部","回填目标 · 同一局部"]):
        axes[0,i].set_title(title,fontsize=11,fontweight="bold",color=DARK,pad=8)
    index={(r["id"],r["method"],r["k"]):r for r in table}
    outrows=[]
    for line,(reason,name) in enumerate(chosen):
        with Image.open(ROOT/"data/trimaps"/(name+".png")) as im:
            mask,_,_=silhouette(np.array(im))
        base=decode((ROOT/"local/confirm"/name/"16-geometry.poly").read_bytes())
        proposed=decode((ROOT/"local/confirm"/name/"16-raster.poly").read_bytes())
        changed=(proposed!=mask) if name==stress["id"] else (base!=proposed)
        x,y,side=choose_window(changed,max(32,min(mask.shape)//4))
        a,b=index[name,"geometry","16"],index[name,"raster","16"]
        main=gains[[r["id"] for r in gains].index(name)]
        rec=dict(reason=reason,id=name,k=16,mean_relative_gain=value(main),geometry_xor=int(a["xor_pixels"]),
                 raster_xor=int(b["xor_pixels"]),geometry_iou=float(a["iou"]),raster_iou=float(b["iou"]),
                 geometry_fp=int(a["fp"]),geometry_fn=int(a["fn"]),raster_fp=int(b["fp"]),raster_fn=int(b["fn"]),
                 crop_x=x,crop_y=y,crop_side=side)
        outrows.append(rec)
        label=axes[line,0]
        label.text(.02,.74,reason,fontsize=12,fontweight="bold",color=DARK)
        label.text(.02,.52,name,fontsize=10,color=DARK)
        label.text(.02,.29,f"全图误填 {rec['geometry_xor']:,} → {rec['raster_xor']:,} px",fontsize=9,color=TEAL if rec["raster_xor"]<rec["geometry_xor"] else CORAL)
        axes[line,1].imshow(error_map(mask,mask),interpolation="nearest")
        axes[line,1].add_patch(Rectangle((x-.5,y-.5),side,side,edgecolor="#bd7032",facecolor="none",linewidth=1.4))
        for col,pred in [(2,base),(3,proposed)]:
            axes[line,col].imshow(error_map(mask,pred)[y:y+side,x:x+side],interpolation="nearest")
        for ax in axes[line]:
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
    fig.suptitle("固定 16 个顶点，回填错误出现在什么位置",fontsize=17,fontweight="bold",color=DARK,y=.985)
    fig.legend(handles=[Patch(color=c/255,label=t) for c,t in [(AGREE,"正确前景"),(OVER,"多填"),(MISS,"漏填")]],
               loc="lower center",ncol=3,frameon=False,bbox_to_anchor=(.53,.041))
    fig.text(.055,.025,"¹ 按 16 点错分像素 / 参考前景面积选取。前三行按每张照片两档预算的平均相对增益选取。",fontsize=9,color=DARK)
    fig.subplots_adjust(left=.045,right=.98,bottom=.102,top=.907,hspace=.20,wspace=.16)
    fig.savefig(folder/"cases.png",dpi=155,facecolor="white")
    plt.close(fig)
    save_csv(res/"cases.csv",outrows)


def distribution(folder,paired):
    main=[r for r in paired if r["baseline"]=="geometry" and r["k"]=="all"]
    gains=100*np.array([float(r["relative_xor_saved"]) for r in main])
    fig,(left,right)=plt.subplots(1,2,figsize=(9.8,3.8),gridspec_kw={"width_ratios":[1.22,1]})
    ordered=np.sort(gains)
    left.bar(np.arange(1,len(ordered)+1),ordered,width=.9,
             color=[CORAL if v<0 else TEAL for v in ordered],edgecolor="none")
    left.axhline(0,color=DARK,linewidth=.9)
    left.axhline(5,color="#87939b",linewidth=.8,ls="--")
    left.text(2,5.8,"预设总体均值门槛 5%",fontsize=8,color="#59636a")
    left.set(xlabel="确认原图（按变化排序）",ylabel="相对几何基线减少的误填像素（%）",
             title="每张照片先平均两档预算")
    summary=read_csv(ROOT/"results/confirm/paired_summary.csv")
    for y,group in enumerate(["all","32","16"]):
        row=next(r for r in summary if r["baseline"]=="geometry" and r["metric"]=="relative_xor_saved" and r["k"]==group)
        m,lo,hi=[100*float(row[k]) for k in ["mean","ci_low","ci_high"]]
        right.errorbar(m,y,xerr=[[m-lo],[hi-m]],fmt="o",color=TEAL,capsize=4,lw=2)
        right.text(hi+.12,y,f"{m:.2f}%",va="center",fontsize=9,color=DARK)
    right.axvline(5,color="#87939b",lw=.8,ls="--")
    right.set(yticks=[0,1,2],yticklabels=["两档平均","32 个顶点","16 个顶点"],ylim=(-.45,2.45),
              xlim=(4,11),xlabel="平均相对减少（%）",title="均值和原图配对 95% 区间")
    for ax in (left,right):
        ax.spines[["top","right"]].set_visible(False)
        ax.tick_params(labelsize=9)
    fig.tight_layout(w_pad=2.2)
    fig.savefig(folder/"paired-gains.png",dpi=165,facecolor="white")
    plt.close(fig)


def vertices(folder):
    # The frozen largest-residual example illustrates both the gain and the fixed-K limit.
    record=read_csv(ROOT/"results/cases.csv")[-1]
    name=record["id"]
    with Image.open(ROOT/"data/trimaps"/(name+".png")) as im:
        mask,_,_=silhouette(np.array(im))
    fig,axes=plt.subplots(1,3,figsize=(10.2,3.4))
    for ax,method,title in zip(axes,[None,"geometry","raster"],["标准化外形","几何基线 · 16 点","按回填误差细调 · 16 点"]):
        ax.imshow(np.where(mask,0.74,1),cmap="gray",vmin=0,vmax=1,interpolation="nearest")
        if method:
            blob=(ROOT/"local/confirm"/name/f"16-{method}.poly").read_bytes()
            p=np.frombuffer(blob[10:],dtype="<u2").reshape(-1,2)
            closed=np.vstack([p,p[0]])
            color="#98482d" if method=="geometry" else TEAL
            ax.plot(closed[:,0],closed[:,1],lw=1.3,color=color)
            ax.scatter(p[:,0],p[:,1],s=11,c=color,zorder=3)
        ax.set_xlim(-8,mask.shape[1]+7)
        ax.set_ylim(mask.shape[0]+7,-8)
        ax.set_title(title,fontsize=11,color=DARK)
        ax.axis("off")
    fig.suptitle(f"两种 16 点近似都占 74 字节  ·  {name}",fontsize=15,color=DARK,fontweight="bold",y=.99)
    fig.text(.5,.06,"灰色为已有蒙版，圆点为实际存储的顶点。这个例子在 16 点预算下仍保留较大的残余误差。",
             ha="center",fontsize=9,color=DARK)
    fig.subplots_adjust(left=.015,right=.985,bottom=.13,top=.82,wspace=.04)
    fig.savefig(folder/"vertices.png",dpi=160,facecolor="white")
    plt.close(fig)


if __name__=="__main__":
    res=ROOT/"results"
    folder=res/"figures"
    folder.mkdir(exist_ok=True)
    paired=read_csv(res/"confirm/paired_by_source.csv")
    examples(res,folder,paired,read_csv(res/"confirm/per_image.csv"))
    distribution(folder,paired)
    vertices(folder)
