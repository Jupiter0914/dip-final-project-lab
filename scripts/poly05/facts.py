
"""Build the reporting ledger from the pinned tables. The input directory is never modified."""
import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MAT = ROOT / "report/poly05"
FIG = ROOT / "results/poly05/figures"
C = "results/poly04/confirm/"
A = C + "analysis/"
D = "results/poly04/dev_fixed/"
SAMPLES = "records/poly04/samples.csv"
BASE = "9c8ce11143dfb30e310965136616fe0addb5c1ef"
FREEZE = "ff70458c06a8fd36e68f546a9b350510968dcddf"


@lru_cache(None)
def rows(file):
    with (ROOT / file).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select(file, **filters):
    return [r for r in rows(file) if all(r[k] == str(v) for k, v in filters.items())]


def one(file, **filters):
    found = select(file, **filters)
    if len(found) != 1:
        raise ValueError((file, filters, len(found)))
    return found[0]


def csv_bytes(data):
    import io
    buf = io.StringIO(newline="")
    wr = csv.DictWriter(buf, list(data[0]), lineterminator="\n")
    wr.writeheader()
    wr.writerows(data)
    return buf.getvalue().encode("utf-8-sig")


PAIR = "源内先均同会话配对重复，再均该源有效会话，最后源等权。区间为源配对百分位重抽。"
SCOPE = {"R2+": "原始多环且同次同码长共同及时成功", "all": "全体环数中同次同码长共同及时成功"}


def build():
    out = []

    def fact(key, what, v, unit, ds, scope, n, calls, file, filt, fields, how,
             *, a="cross", b="within_full", budget=256, t=100, tier="主要", lo="", hi=""):
        condition = filt if isinstance(filt, str) else "; ".join(f"{k}={x}" for k,x in filt.items())
        out.append(dict(fact_id=key, conclusion=what, method=a, comparator=b, dataset=ds,
                        population=scope, budget_B=budget, observable_ms=t, independent_sources=n,
                        calls_or_matched_pairs=calls, value=v, unit=unit, ci95_low=lo, ci95_high=hi,
                        aggregation=how, original_file=file, filter=condition, fields=fields,
                        evidence_commit=BASE, scientific_freeze=FREEZE, role=tier))

    for ds, prefix in [("Oxford","O"), ("LEMS","L")]:
        samples = select(SAMPLES,dataset=ds)
        source_rows = select(A+"source_pairs.csv",dataset=ds,budget=256,deadline_ms=100,
                             method="cross",baseline="within_full")
        for kind, keep in [("R0", lambda r:int(r["rings"])==0),("R1",lambda r:int(r["rings"])==1),
                           ("R2",lambda r:int(r["rings"])>=2),("all",lambda r:True)]:
            target=[r for r in samples if keep(r)]
            active=[r for r in source_rows if keep(r) and int(r["common"])>0]
            for suffix, group, file, extra in [("input",target,SAMPLES,"清单登记"),
                        ("shared",active,A+"source_pairs.csv","共同及时次数 common>0")]:
                fact(f"{prefix}.{kind}.{suffix}",extra+"的独立源",len(group),"源",ds,kind,len(group),
                     sum(int(r["common"]) for r in group) if suffix=="shared" else "",file,
                     f"dataset={ds}; {kind}; "+("256/100 cross/within_full; common>0" if suffix=="shared" else "all selected"),
                     "id,rings"+(",common" if suffix=="shared" else ""), "按不同源 ID 计数",
                     a="cross" if suffix=="shared" else "", b="within_full" if suffix=="shared" else "",
                     t=100 if suffix=="shared" else "", budget=256 if suffix=="shared" else "",tier="样本与覆盖")
        for budget,t in [(256,100),(256,200),(128,100),(128,200),(512,100),(512,200)]:
            for base,scope in ([("within_full","R2+"),("cgal","all"),("cgal_within","all")]
                               if (budget,t)==(256,100) else [("within_full","R2+")]):
                f=dict(dataset=ds,budget=budget,deadline_ms=t,method="cross",baseline=base,scope=scope)
                group=f"{prefix}.{budget}.{t}.{base}"
                tier=("主要" if ds=="Oxford" else "外部验证") if (budget,t,base)==(256,100,"within_full") else "次要"
                for metric,unit in [("xor_saved","像素"),("relative_xor_saved_pct","%"),("iou_gain_pp","百分点")]:
                    if metric!="xor_saved" and (budget,t,base)!=(256,100,"within_full"):
                        continue
                    q=one(A+"paired_summary.csv",**f,metric=metric)
                    n=q["n_sources"]; calls=q["n_common_runs"]
                    how=PAIR
                    if metric=="relative_xor_saved_pct":
                        how+=" 每对先算 100×(B−A)/max(1,B)，B 为对照错分。"
                    label={"xor_saved":"对照减跨圈的平均错分","relative_xor_saved_pct":"平均相对少错","iou_gain_pp":"跨圈减对照的平均 IoU"}[metric]
                    scope_text=SCOPE[scope]+("；每域事前 24 个代表的子集" if budget!=256 else "")
                    info=dict(a="cross",b=base,budget=budget,t=t,tier=tier)
                    fact(group+"."+metric,label,q["mean"],unit,ds,scope_text,n,calls,A+"paired_summary.csv",
                         dict(**f,metric=metric),"mean,lo,hi,n_sources,n_common_runs",how,lo=q["lo"],hi=q["hi"],**info)
                    if metric=="xor_saved" and (budget,t,base)==(256,100,"within_full"):
                        for k,lab,u in [("wins","改善","源"),("ties","持平","源"),("losses","退化","源"),("median","源差中位数","像素"),
                                        ("worst","最差源差","像素"),("best","最大源差","像素")]:
                            fact(f"{prefix}.{k}",lab,q[k],u,ds,scope_text,n,calls,A+"paired_summary.csv",
                                 dict(**f,metric=metric),k,PAIR,**info)
                        pc=one(A+"paired_coverage.csv",**f)
                        for key in ("common_method_xor","common_baseline_xor"):
                            fact(prefix+"."+key,"共同成功样本上"+("跨圈" if key=="common_method_xor" else "圈内")+"平均错分",
                                 pc[key],"像素",ds,scope_text,n,calls,A+"paired_coverage.csv",f,key,PAIR,**info)
        for scope in ("all","R2+"):
            ft=dict(dataset=ds,budget=256,deadline_ms=100,scope=scope)
            for method in ("cross","within_full"):
                filt=dict(**ft,method=method); q=one(A+"coverage.csv",**filt)
                fact(f"{prefix}.{scope}.{method}.coverage","截止前收到合格文件",q["obs_success"],"次",ds,scope,q["sources"],q["runs"],
                     A+"coverage.csv",filt,"obs_success,runs,sources","分母为该方法此范围的全部预定调用，每源六次。",a=method,b="",tier="覆盖")
            f=dict(**ft,method="cross",baseline="within_full")
            q=one(A+"paired_coverage.csv",**f)
            for k in ("n_common_runs","n_baseline_only","n_method_only","n_neither","coverage_gain_pp"):
                isdiff=k=="coverage_gain_pp"
                fact(f"{prefix}.{scope}.{k}","及时配对交付 "+k,q[k],"百分点" if isdiff else "对",ds,scope,q["sources"],int(q["sources"])*6,
                     A+"paired_coverage.csv",f,k,"配对状态计数；覆盖差为源等权的跨圈减圈内。",
                     lo=q["coverage_lo_pp"] if isdiff else "",hi=q["coverage_hi_pp"] if isdiff else "",tier="覆盖")
        for r in select(A+"stability.csv",dataset=ds):
            fact(prefix+"."+r["analysis"].replace("/","."),"源级会话或完整配对差",r["mean"],"像素",ds,"R≥2；"+r["analysis"],r["n"],"",
                 A+"stability.csv",dict(dataset=ds,analysis=r["analysis"]),"mean,lo,hi,n",PAIR,lo=r["lo"],hi=r["hi"],tier="稳定性")
        loo=select(A+"leave_one_source.csv",dataset=ds)
        for k,fn in [("min",min),("max",max)]:
            fact(f"{prefix}.loo.{k}","删除任一源后均值的"+("下端" if k=="min" else "上端"),fn(float(r["mean_without"]) for r in loo),
                 "像素",ds,"R≥2、每次少一个源",loo[0]["n"],"",A+"leave_one_source.csv",dict(dataset=ds),"mean_without",k+"（敏感性范围，非置信区间）",tier="稳定性")
        ex=one(C+"screen_summary.csv",dataset=ds)
        for k,u in [("states","状态"),("proposals","对"),("screened_valid_improvements","对"),("different_first_choice","状态")]:
            fact(f"{prefix}.exact.{k}","精确整图补充 "+k,ex[k],u,ds,"预登记补充源的可审计状态",ex["actual_sources"],"",C+"screen_summary.csv",
                 dict(dataset=ds),k,"按已交付状态，在计时外复查候选。",a="exact",b="cross",t="",tier="补充诊断")
    for q in select(C+"structure_summary.csv",dataset="Oxford",budget=256):
        for col,which in [("mean_extra_xor_recovered","recovered_after_invalid"),("mean_extra_xor_valid","final_valid")]:
            fact("O.struct."+which,"结构验收改选合法起点的额外错分",q[col],"像素","Oxford",which,q[which],"",C+"structure_summary.csv",
                 dict(dataset="Oxford",budget=256),col+","+which,"逐源 legal_xor−unconstrained_xor 等权；仅初始化。",
                 a="合法种子",b="DP 第一解",t="",tier="结构诊断")
    case=one(C+"figures/figure-cases.csv",id="British_Shorthair_38",reason="absolute_structure")
    for k,unit in [("reference_area","像素"),("method_region_area","像素"),("baseline_region_area","像素"),("method_recall","比例")]:
        fact("hole."+k,"同一有限孔的"+k,case[k],unit,"Oxford","British_Shorthair_38；孔 2",1,1,C+"figures/figure-cases.csv",
             "id=British_Shorthair_38; S2/2; reason=absolute_structure",k,"匹配身份后在原尺寸像素格计数。",tier="真实案例")
    for m in ("within_old","within_full_oldtri","within_full"):
        q=one(D+"summary-rounds.csv",method=m,condition="fixed2")
        for k in ("rounds","under_24","proposed","accepted"):
            fact("dev."+m+"."+k,"开发固定两轮的"+k,q[k],{"rounds":"轮","under_24":"轮","proposed":"对","accepted":"次"}[k],"已知混合开发源",
                 "32 个输入；30 个取得合法起点",32,32,D+"summary-rounds.csv",dict(method=m,condition="fixed2"),k,"逐轮计数，非时间截止。",
                 a=m,b="",t="",tier="开发诊断")
    q=one(D+"summary-pairs.csv",condition="fixed2",scope="all",method="within_full",baseline="within_old")
    fact("dev.same","加强前后最终错分持平",q["tie"],"源","已知混合开发源","共同成功",q["sources"],q["common_runs"],D+"summary-pairs.csv",
         "fixed2; all; within_full/within_old","tie,sources,common_runs","固定两轮，同源配对。",a="within_full",b="within_old",t="",tier="开发诊断")
    f=dict(dataset="Oxford",budget=256,method="cross")
    calls=select(C+"runs.csv",**f)
    obs=select(C+"per_run.csv",**f,deadline_ms=100)
    for field,label,data,path in [("search_end_ms","内部搜索结束",calls,C+"runs.csv"),("end_ms","完整函数返回",obs,C+"per_run.csv")]:
        for suffix,p in [("median",.5),("p95",.95)]:
            fact("time."+field+"."+suffix,label+" "+suffix,np.quantile([float(r[field]) for r in data],p),"ms","Oxford","所有调用，含失败",len({r["id"] for r in data}),
                 len(data),path,dict(**f,**({"deadline_ms":100} if data is obs else {})),field,"跨调用取线性分位，每一调用只取一行。",
                 a="cross",b="",t=100 if data is obs else "",tier="时钟核对")
    for ds,p in [("Oxford","O"),("LEMS","L")]:
        inputs=select(SAMPLES,dataset=ds)
        for layer,n in Counter(r["stratum"] for r in inputs).items():
            fact(p+".strata."+layer,"按输入分层登记",n,"源",ds,layer,n,"",SAMPLES,dict(dataset=ds,stratum=layer),
                 "id,stratum","不同源 ID 计数。",a="",b="",budget="",t="",tier="样本")
        q=one(C+"structure_summary.csv",dataset=ds,budget=256)
        for col in ("n","raw_valid","recovered_after_invalid","final_valid","search_failed"):
            fact(p+".init."+col,"初始化结构检查 "+col,q[col],"源",ds,"全部输入",q["n"],"",C+"structure_summary.csv",
                 dict(dataset=ds,budget=256),col,"独立输入计数。",a="合法分配起点",b="独立 DP 第一解",t="",tier="结构诊断")
        opt=one(A+"paired_summary.csv",dataset=ds,budget=256,deadline_ms=100,method="exact",baseline="cross",scope="all",metric="xor_saved")
        fact(p+".exact.effect","精确整图相对跨圈可加路径的平均少错",opt["mean"],"像素",ds,"每域事前 24 源中的共同及时成功者",
             opt["n_sources"],opt["n_common_runs"],A+"paired_summary.csv",f"dataset={ds};256/100; exact/cross; all; xor_saved",
             "mean,lo,hi",PAIR,a="exact",b="cross",lo=opt["lo"],hi=opt["hi"],tier="补充诊断")
    for c in rows(C+"figures/figure-cases.csv"):
        if c["id"]=="Robot055" and c["reason"]=="structure_conflict":continue
        source=one(A+"source_pairs.csv",dataset=c["dataset"],id=c["id"],method="cross",baseline="within_full",budget=256,deadline_ms=100)
        tag="case."+c["id"]
        fact(tag+".average","案例的源均差",source["xor_saved"],"像素",c["dataset"],c["id"],1,source["common"],A+"source_pairs.csv",
             c["id"]+"; cross/within_full; 256/100","xor_saved,common",PAIR,tier="真实案例")
        trace=dict(dataset=c["dataset"],id=c["id"],session=c["session"],rep=c["rep"],budget=256,deadline_ms=100)
        for m in ("within_full","cross"):
            obs=one(C+"per_run.csv",**trace,method=m)
            for col,unit in [("xor","像素"),("actual_bytes","B"),("delivered_ms","ms"),("search_end_ms","ms")]:
                fact(tag+"."+m+"."+col,"案例单次解码或时间",obs[col],unit,c["dataset"],c["id"],1,1,C+"per_run.csv",
                     dict(**trace,method=m),col,"使用实际所示共同重复。",a=m,b="",tier="真实案例")
    move=one(C+"rounds.csv",dataset="Oxford",id="Ragdoll_32",budget=256,session="S1",rep=1,method="cross",round=1)
    for col in ("xor_before","xor_after"):
        fact("move."+col,"同一轨迹原子删插前后错分",move[col],"像素","Oxford","Ragdoll_32",1,1,C+"rounds.csv",
             "Ragdoll_32; 256; S1/1; cross; round=1",col,"读该次被接受移动的整图错分。",a="cross 第 1 轮",b="cross 合法起点",t="",tier="真实动作")
    cluster=one(A+"cluster.csv",dataset="LEMS")
    fact("L.cluster","按整个类别重抽的源均值",cluster["mean"],"像素","LEMS","R≥2；四类别",cluster["sources"],42,A+"cluster.csv",
         "LEMS; 256/100; cross/within_full","mean,lo,hi,categories,sources","整类有放回重抽，保留每类源数。",
         lo=cluster["lo"],hi=cluster["hi"],tier="外部验证")
    for field in ("serialized_ms","delivered_ms"):
        example=one(C+"checkpoints.csv",id="keeshond_55",session="S1",rep=2,budget=256,method="within_full",round=3)
        fact("clock."+field,"临界检查点",example[field],"ms","Oxford","keeshond_55",1,1,C+"checkpoints.csv",
             "keeshond_55; S1/2; 256; within_full; round=3",field,"同一份 PM31 的时钟读数。",a="within_full",b="",tier="时钟核对")
    # The two files beside the round log are proof of this operation's point counts and rate.
    from evidence import file_for_blob, unpack, digest
    for number in (0,1):
        t0=one(C+"checkpoints.csv",id="Ragdoll_32",session="S1",rep=1,budget=256,method="cross",round=number)
        stored=file_for_blob(t0["sha256"]).read_bytes()
        assert digest(stored)==t0["sha256"]
        _,rings,_=unpack(stored)
        readings=[("donor",len(rings[1]),"点","PM31 ring[1].vertex_count"),
                  ("receiver",len(rings[0]),"点","PM31 ring[0].vertex_count"),
                  ("K",sum(map(len,rings)),"点","PM31 sum(vertex_count)"),
                  ("R",len(rings),"圈","PM31 ring_count"),("bytes",len(stored),"B","actual_bytes"),
                  ("received",t0["delivered_ms"],"ms","delivered_ms")]
        for col,val,unit,field in readings:
            fact(f"move.r{number}.{col}","图 1–2 的真实动作 "+col,val,unit,"Oxford","Ragdoll_32",1,1,C+"checkpoints.csv",
                 f"Ragdoll_32; S1/1; 256; cross; round={number}; sha256={t0['sha256']}",field,
                 "读取该检查点的实收实物；圈编号从零起。",a="cross",b="",t="",tier="真实动作")
    known="records/poly04/known.csv"
    old_oxford=[r for r in rows(known) if r["dataset"]=="Oxford"]
    fact("O.known","抽样前排除的已知 Oxford 照片数",len({r["id"] for r in old_oxford}),"源","Oxford",
         "历史登记",len({r["id"] for r in old_oxford}),"",known,"dataset=Oxford","id","原始 ID 去重。",a="",b="",t="",budget="",tier="样本")
    assert len({r["fact_id"] for r in out})==len(out)
    return out


if __name__=="__main__":
    ledger=build()
    MAT.mkdir(parents=True,exist_ok=True)
    (MAT/"facts.csv").write_bytes(csv_bytes(ledger))
    print(len(ledger),"facts")
