
"""Six Word-width plates. Latin, Chinese and mathematics retain their own glyph families."""
import json
import os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm, pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Patch
from facts import A, C, FIG, MAT, SAMPLES, one, select, rows
from evidence import REPLAY, MEDIA, BG, HIT, FN, FP, source, decoded, paint

INK="#283335"; TEAL="#137368"; BLUE="#227a9f"; RUST="#ad4b25"; GRAY="#57666a"; RULE="#cdd6d4"
WIDTH=7.05
LABELS=["01-encoding","02-exchange","03-source-effects","04-coverage-comparators","05-structure","06-cases"]


def style():
    for name,win,env in [("Times New Roman","times.ttf","POLY05_TIMES"),("SimSun","simsun.ttc","POLY05_SIMSUN")]:
        path=Path(os.environ.get(env,"C:/Windows/Fonts/"+win))
        if path.exists():
            fm.fontManager.addfont(path)
        fm.findfont(fm.FontProperties(family=name),fallback_to_default=False)
    plt.rcParams.update({"font.family":["Times New Roman","SimSun"],"mathtext.fontset":"stix",
                         "svg.fonttype":"path","svg.hashsalt":"poly05","font.size":10.3,"axes.titlesize":11,
                         "text.color":INK,"axes.labelcolor":INK,"xtick.color":GRAY,"ytick.color":GRAY,
                         "axes.edgecolor":RULE,"axes.spines.top":False,"axes.spines.right":False,
                         "axes.titlelocation":"left","axes.titlepad":8,"xtick.labelsize":9.5,"ytick.labelsize":9.5,
                         "savefig.facecolor":"white","figure.facecolor":"white"})


def svg_lf(path):
    content=path.read_bytes()
    clean=b"\n".join(line.rstrip(b" \t") for line in content.replace(b"\r\n",b"\n").split(b"\n"))
    if content!=clean:
        path.write_bytes(clean)


def save(fig,key):
    FIG.mkdir(parents=True,exist_ok=True)
    fig.savefig(FIG/(key+".png"),dpi=320)
    fig.savefig(FIG/(key+".svg"),metadata={"Date":None})
    svg_lf(FIG/(key+".svg"))
    plt.close(fig)


def board(fig):
    ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis("off")
    return ax


def box(ax,x,y,w,h,title,body,accent=TEAL):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.006,rounding_size=.011",
                        facecolor="#f6f8f5",edgecolor=RULE,linewidth=.8))
    ax.text(x+.016,y+h-.052,title,fontsize=12,va="top",color=accent)
    ax.text(x+.016,y+.038,body,fontsize=10.0,va="bottom",linespacing=1.5)


def flow(data):
    fig=plt.figure(figsize=(WIDTH,4.03))
    ax=board(fig)
    ax.text(.04,.955,"从已经读入内存的 0/1 蒙版到可以解码的文件",fontsize=14,va="top")
    cards=[(.04,"提取完整环","前景 8 连通，背景 4 连通\n高精度回填逐像素核对"),
           (.36,"分配有限顶点","逐圈建误差曲线，共享总点数\n从有限池选首个合法起点"),
           (.68,"联合删插","删一点，补一点\n整图少错且结构合格才交付")]
    for x,title,body in cards:
        box(ax,x,.62,.272,.225,title,body)
    for x in (.322,.642):
        ax.annotate("",xy=(x+.032,.734),xytext=(x,.734),arrowprops=dict(arrowstyle="->",color=GRAY))
    ax.text(.045,.535,r"$L=10+4R+4K\ \leq\ B$",fontsize=15,color=INK)
    ax.text(.046,.452,"文件计入头部、环记录与坐标。验收检查环嵌套、部件、孔与邻接。",fontsize=10.5)
    events=select(C+"checkpoints.csv",id=data["action"]["id"],session="S1",rep=1,method="cross",budget=256)
    times=[float(r["delivered_ms"]) for r in events]
    line=fig.add_axes([.115,.205,.79,.117])
    line.set_xlim(0,145);line.set_ylim(-.3,1);line.set_yticks([]);line.set_xticks([0,50,100,140])
    line.axhline(.34,color=RULE,lw=1.5)
    for n,t in enumerate(times):
        line.plot(t,.34,"o",color=TEAL if t<=100 else GRAY,ms=5)
        line.text(t,.68,f"轮 {n}",ha="center",fontsize=9)
    line.axvline(100,color=RUST,ls="--",lw=1.2)
    line.set_xlabel("调用方实际接收时间（ms）",labelpad=2)
    line.spines["left"].set_visible(False)
    ax.text(.045,.045,"Ragdoll_32 的实际轨迹。100 ms 时已收到第 1 轮文件，第 2 轮留给后续观察。",fontsize=9.7)
    save(fig,LABELS[0])


def window(xy,side,shape):
    h,w=shape
    return max(0,min(w-side,int(round(xy[0]-side/2)))),max(0,min(h-side,int(round(xy[1]-side/2)))),side


def viewport(ax,img,crop=None):
    ax.imshow(img,interpolation="nearest",origin="upper")
    if crop:
        x,y,s=crop;ax.set_xlim(x-.5,x+s-.5);ax.set_ylim(y+s-.5,y-.5)
    ax.set_aspect("equal");ax.set_xticks([]);ax.set_yticks([])
    for e in ax.spines.values():e.set_visible(False)


def overlay(ax,ring,color):
    v=ring/4-1
    p=np.vstack([v,v[0]])
    ax.plot(p[:,0],p[:,1],color=color,lw=.8)
    ax.plot(v[:,0],v[:,1],"o",ms=2.8,mec="white",mew=.3,mfc=color)


def error_legend(fig):
    handles=[Patch(facecolor=np.array(c)/255,label=l) for c,l in [(HIT,"正确前景"),(FP,"多填 FP"),(FN,"漏填 FN")]]
    fig.legend(handles=handles,loc="lower center",bbox_to_anchor=(.5,.005),ncol=3,frameon=False,
               fontsize=9.3,handlelength=1.1,columnspacing=1.6)


def action_figure(data):
    a=data["action"]; card=next(c for c in data["cases"] if c["id"]==a["id"])
    raw,_=source(one(SAMPLES,id=a["id"]))
    states=[decoded(a[k]["sha256"]) for k in ("before","after")]
    donor,receiver=a["donor"],a["receiver"]
    coords=[states[0][1][donor][a["donor_vertex"]]/4-1,np.array(a["insert"])/4-1]
    crops=[window(p,53,raw.shape) for p in coords]
    fig=plt.figure(figsize=(WIDTH,4.48))
    gs=fig.add_gridspec(2,3,width_ratios=[1.45,1,1],left=.04,right=.96,top=.835,bottom=.13,wspace=.18,hspace=.36)
    ax=fig.add_subplot(gs[:,0]);viewport(ax,paint(raw))
    ax.set_title("原始完整蒙版")
    for (x,y,s),letter,col in zip(crops,("D","I"),(RUST,BLUE)):
        ax.add_patch(Rectangle((x-.5,y-.5),s,s,fill=False,ec=col,lw=1.3))
        ax.annotate(letter,(x,y),xytext=(-4,-8),textcoords="offset points",color=col,fontsize=11,
                    bbox=dict(facecolor="white",edgecolor="none",pad=.7))
    for j,(key,(pred,rings,_)) in enumerate(zip(("before","after"),states)):
        for i,(ring,crop,color) in enumerate(zip((donor,receiver),crops,(RUST,BLUE))):
            panel=fig.add_subplot(gs[i,j+1]);viewport(panel,paint(raw,pred),crop);overlay(panel,rings[ring],color)
            marker="x" if i==0 else "+"
            panel.plot(*coords[i],marker=marker,color="white",mew=2.6,ms=8,ls="none")
            panel.plot(*coords[i],marker=marker,color=color,mew=1.25,ms=8,ls="none")
            panel.set_title(f"{'供体 D' if i==0 else '接收 I'}　环 {ring} · {len(rings[ring])} 点",fontsize=10)
    fig.text(.045,.947,f"{card['id']}　一次跨圈交换",fontsize=14)
    fig.text(.047,.885,f"第 0 → 1 轮　{a['before']['size']} → {a['after']['size']} B　　错分 {a['before']['xor']} → {a['after']['xor']} 像素",fontsize=10.7)
    fig.text(.486,.092,"操作前",ha="center",fontsize=10.5);fig.text(.816,.092,"操作后",ha="center",fontsize=10.5)
    error_legend(fig);save(fig,LABELS[1])


def effects(data):
    fig,axes=plt.subplots(2,2,figsize=(WIDTH,4.85),gridspec_kw={"width_ratios":[1.21,1],"height_ratios":[1.45,1]})
    fig.subplots_adjust(left=.115,right=.97,top=.925,bottom=.115,wspace=.43,hspace=.67)
    for i,ds in enumerate(("Oxford","LEMS")):
        ax,ci=axes[i]
        src=select(A+"source_pairs.csv",dataset=ds,budget=256,deadline_ms=100,method="cross",baseline="within_full")
        v=np.sort([float(r["xor_saved"]) for r in src if int(r["rings"])>=2 and r["xor_saved"]]);x=np.arange(1,len(v)+1)
        ax.axhline(0,color=GRAY,lw=.8)
        cols=[TEAL if z>0 else RUST if z<0 else GRAY for z in v]
        ax.vlines(x,0,v,color=cols,lw=.8);ax.scatter(x,v,c=cols,s=10,zorder=3)
        ax.axhline(v.mean(),ls="--",lw=1,color=BLUE)
        ax.set_title(f"{ds}　逐源差值（{len(v)} 源）")
        ax.set_ylabel("少错像素");ax.set_xlabel("源按差值排序",labelpad=1);ax.grid(axis="y",alpha=.18)
        ax.set_xlim(.5,len(v)+.5)
        if ds=="LEMS":ax.set_xticks(x);ax.set_ylim(-.3,3.55)
        entries=["all_common"]+(["session/S1","session/S2","session/S3"] if ds=="Oxford" else ["category"])
        ci.axvline(0,color=GRAY,lw=.8,ls="--");ci.set_title("源均值和 95% 区间")
        ticks=[]
        for j,key in enumerate(entries):
            if key=="category":
                r=one(A+"cluster.csv",dataset=ds);name="整类重抽"
            else:
                r=one(A+"stability.csv",dataset=ds,analysis=key);name="总体" if j==0 else key[-2:]
            m,lo,hi=map(float,[r[k] for k in ("mean","lo","hi")]);col=TEAL if j==0 else BLUE
            ci.errorbar(m,j,xerr=[[m-lo],[hi-m]],fmt="o",color=col,ms=4.3,capsize=3,lw=1.4)
            ticks.append(name)
        ci.set_yticks(range(len(ticks)),ticks)
        ci.set_ylim(len(ticks)-.45,-.5);ci.set_xlabel("少错像素",labelpad=1);ci.grid(axis="x",alpha=.18)
    save(fig,LABELS[2])


def delivery(data):
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,3.1),gridspec_kw={"width_ratios":[1.13,1]})
    fig.subplots_adjust(left=.055,right=.965,top=.84,bottom=.2,wspace=.4)
    tab,ax=axes;tab.axis("off")
    tab.set_title("及时交付次数／预定调用数")
    cols=[.0,.48,.82]
    for x,s in zip(cols,["来源与范围","圈内","跨圈"]):
        tab.text(x,.89,s,fontsize=10.5,ha="left" if x==0 else "center",transform=tab.transAxes)
    for i,(ds,scope) in enumerate([("Oxford","all"),("Oxford","R2+"),("LEMS","all"),("LEMS","R2+")]):
        y=.7-i*.194
        tab.text(0,y,ds+(" 全体" if scope=="all" else " 多环"),transform=tab.transAxes)
        for x,m in zip(cols[1:],("within_full","cross")):
            r=one(A+"coverage.csv",dataset=ds,budget=256,deadline_ms=100,method=m,scope=scope)
            tab.text(x,y,f"{r['obs_success']}/{r['runs']}",transform=tab.transAxes,ha="center",
                     color=TEAL if m=="cross" else INK)
    for y in (.84,.025):
        tab.plot([0,1],[y,y],transform=tab.transAxes,color=RULE,lw=1)
    ax.set_title("Oxford　分别配对的平均差")
    for j,(base,scope,label) in enumerate([("cgal","all","原版 CGAL"),("cgal_within","all","CGAL 加圈内后处理"),("within_full","R2+","增强圈内基线")]):
        q=one(A+"paired_summary.csv",dataset="Oxford",budget=256,deadline_ms=100,method="cross",baseline=base,scope=scope,metric="xor_saved")
        m,lo,hi=map(float,[q[k] for k in ("mean","lo","hi")])
        ax.errorbar(m,j,xerr=[[m-lo],[hi-m]],color=TEAL if j==2 else BLUE,fmt="o",ms=4.5,capsize=3)
        ax.text(0,j-.28,f"{label} · {q['n_sources']} 源 · {m:.2f}",fontsize=9.3)
    ax.set_ylim(2.42,-.62);ax.set_xlim(-4,130);ax.set_yticks([]);ax.set_xlabel("对照错分减跨圈错分（像素）")
    ax.grid(axis="x",alpha=.17)
    save(fig,LABELS[3])


def structure(data):
    card=next(c for c in data["cases"] if c["reason"]=="absolute_structure")
    batch=select(C+"structural_cost.csv",dataset="Oxford",budget=256)
    vals=sorted(int(r["validity_cost_xor"]) for r in batch if r["raw_reason"]!="ok" and r["validity_cost_xor"])
    fig=plt.figure(figsize=(WIDTH,3.44))
    gs=fig.add_gridspec(1,3,width_ratios=[1.52,1,1],left=.105,right=.97,top=.785,bottom=.245,wspace=.26)
    ax=fig.add_subplot(gs[0,0]);ax.bar(np.arange(1,len(vals)+1),vals,color=BLUE,width=.7);ax.axhline(np.mean(vals),color=RUST,ls="--",lw=1.3)
    ax.set_xlabel("恢复的 9 源，按代价排序");ax.set_ylabel("初始化额外错分（像素）");ax.set_xticks([1,5,9]);ax.grid(axis="y",alpha=.15)
    fig.text(.045,.91,"结构验收的初始化代价",fontsize=12)
    fig.text(.49,.91,"一个已对应孔的面积",fontsize=12)
    raw,_=source(one(SAMPLES,id=card["id"]))
    pred=decoded(card["methods"]["cross"]["sha256"])[0]
    assert np.array_equal(pred,decoded(card["methods"]["within_full"]["sha256"])[0])
    for j,(img,label) in enumerate([(raw,"原蒙版 · 271 像素"),(pred,"两法同值 · 96 像素")]):
        p=fig.add_subplot(gs[0,j+1]);viewport(p,paint(img),card["crop"]);p.set_title(label,fontsize=9.8)
    fig.text(.105,.07,"虚线为恢复源均值。右图按同一 28 × 28 像素窗口放大，浅色为背景。",fontsize=9.5)
    save(fig,LABELS[4])


def cases(data):
    fig=plt.figure(figsize=(WIDTH,5.03))
    gs=fig.add_gridspec(3,4,width_ratios=[1.48,.90,1,1],left=.035,right=.97,top=.89,bottom=.095,wspace=.09,hspace=.17)
    for i,why in enumerate(("typical_positive","nearest_zero","worst")):
        c=next(c for c in data["cases"] if c["dataset"]=="Oxford" and c["reason"]==why)
        ax=fig.add_subplot(gs[i,0]);ax.axis("off")
        for j,(s,fs) in enumerate([(c["title"],11.7),(c["id"],9.8),(f"源均值　{c['source_mean']:+g} 像素",9.6),(f"该次差　{c['repeat_delta']:+d} 像素",9.6)]):
            ax.text(0,.86-j*.217,s,transform=ax.transAxes,fontsize=fs,va="center")
        for j,(path,label) in enumerate([(c["raw"],"原蒙版／取景框"),(c["methods"]["within_full"]["errors"],"增强圈内基线"),(c["methods"]["cross"]["errors"],"允许跨圈")]):
            ax=fig.add_subplot(gs[i,j+1]);img=plt.imread(REPLAY/path)
            viewport(ax,img,c["crop"] if j else None)
            if not j:
                x,y,s=c["crop"];ax.add_patch(Rectangle((x-.5,y-.5),s,s,ec=RUST,fill=False,lw=1))
            if i==0:ax.set_title(label,fontsize=9.8)
    error_legend(fig);save(fig,LABELS[5])


def generate():
    data=json.loads((REPLAY/"index.json").read_text(encoding="utf-8"))
    style()
    for fn in [flow,action_figure,effects,delivery,structure,cases]:
        fn(data)


if __name__=="__main__":
    generate()
