"""Limited known-domain check after the Oxford single-ring development experiment."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import cv2
import numpy as np
from poly02.data import CFG,REC,ROOT,rows,save_rows,read_mask,sha
from poly02.core import exterior,metrics
from src.codec import encode,decode,paint
from . import single as study
from .single import source_set,save_poly
from .single_search import prepare,coordinate,Work,State
from .single_support import expanded
from .single_profile import independent_scan
from .atomic import replace_vertex


def select_sources():
    ranked=[]
    for src in rows(REC/"samples.csv"):
        if src["stage"]!="cross":continue
        raw=read_mask(src)
        mask,c=exterior(raw,3)
        perimeter=cv2.arcLength(c,True)
        area=int(mask.sum())
        ranked.append((perimeter**2/area,src["id"],perimeter,area,src))
    ranked.sort(key=lambda r:(r[0],r[1]))
    assert len(ranked)==70
    pick={int((j+.5)*len(ranked)/10) for j in range(10)}
    metadata=[dict(rank=i,id=name,group=src["group"],sha256=src["sha256"],perimeter=perimeter,area=area,
                   complexity=score,selected=int(i in pick)) for i,(score,name,perimeter,area,src) in enumerate(ranked)]
    return metadata,sorted([r[4] for i,r in enumerate(ranked) if i in pick],key=lambda r:r["id"])


def run():
    cfg=json.loads(CFG.read_text())
    folder=study.OUT/"mpeg"
    folder.mkdir(parents=True,exist_ok=False)
    rankings,sources=select_sources()
    save_rows(folder/"input_ranking.csv",rankings)
    baseline={(r["id"],int(r["k"])):r for r in rows(ROOT/"results/poly02/cross/per_image.csv") if r["method"]=="post_guard"}
    output=[]
    first=None
    failures=[]
    for src in sources:
        raw=read_mask(src)
        for k in (16,32):
            try:
                t0=perf_counter()
                mask,c,base,bf,floor,common=prepare(raw,k,cfg)
                assert sha(encode(mask.shape,base.p))==baseline[src["id"],k]["blob_sha256"]
                pt=Work(mask,bf,floor,float("inf"))
                stationary,certified,cycles=coordinate(base,pt,max_cycles=20)
                mid=perf_counter()
                work=Work(mask,bf,floor,float("inf"))
                best=stationary
                best_raw=None;desc=None
                improved=admissible=0
                donors,targets,damage=expanded(mask,c,stationary,work) if certified else ([],[],None)
                for i in donors:
                    for e,xy in targets:
                        if i in (e,(e+1)%k):continue
                        p=replace_vertex([stationary.p],0,int(i),0,e,xy)[0]
                        cost=work.score(p)
                        work.pair_seen+=1
                        best_raw=cost if best_raw is None else min(cost,best_raw)
                        if cost>=stationary.xor:continue
                        improved+=1
                        if work.valid(p):
                            admissible+=1
                            if cost<best.xor:
                                best=State(p,cost)
                                desc=(int(i),e,xy.copy())
                blob=encode(mask.shape,best.p)
                end=perf_counter()
                actual=metrics(mask,decode(blob))
                assert actual["xor"]==best.xor and bf.exact(decode(blob))>=floor
                sblob=encode(mask.shape,stationary.p)
                sfile=save_poly("mpeg",src["id"],k,"stationary",0,sblob)
                file=save_poly("mpeg",src["id"],k,"best",0,blob)
                output.append(dict(id=src["id"],group=src["group"],k=k,status="success",structural_status="simple",failure_reason="",
                       certified=int(certified),cycles=cycles,start_xor=base.xor,stationary_xor=stationary.xor,
                       final_xor=best.xor,saved=stationary.xor-best.xor,min_deletion_cost=damage if len(donors) else "",
                       best_examined_xor=best_raw if best_raw is not None else "",
                       improving_raw=improved,improved_legal_guarded=admissible,invalid=work.illegal,bf_rejected=work.bf_rejects,
                       zero_residual=int(stationary.xor==0),joint_evals=work.pair_seen,rank_evals=work.ranking,point_evals=pt.count,
                       complete_xor_evals=pt.count+work.count+common["initial_xor_evals"],bf_evals=pt.bf_evals+work.bf_evals,
                       extra_ms=(end-mid)*1000,full_ms=(end-t0)*1000,actual_bytes=len(blob),bf2_floor=float(floor),
                       stationary_file=sfile,stationary_sha=sha(sblob),file=file,sha256=sha(blob),**actual))
                if desc and first is None:
                    i,e,xy=desc
                    deleted=np.delete(stationary.p,i,axis=0)
                    first=dict(id=src["id"],k=k,donor=i,edge=e,xy=xy.tolist(),initial_sha=sha(encode(mask.shape,base.p)),
                        stationary=stationary.p.tolist(),after=best.p.tolist(),stationary_sha=sha(sblob),after_sha=sha(blob),
                        stationary_xor=stationary.xor,deletion_only_xor=int(np.count_nonzero(paint(mask.shape,deleted)!=mask)),
                        final_xor=best.xor,stationary_bf2=float(bf.exact(decode(sblob))),final_bf2=actual["bf2"],
                        floor_num=floor.numerator,floor_den=floor.denominator)
                    sc=independent_scan(mask,stationary.p,floor)
                    save_rows(folder/"escape_point_certificate.csv",sc)
            except (ValueError,IndexError) as exc:
                failures.append(dict(id=src["id"],k=k,status="search_failed",reason=str(exc)))
        save_rows(folder/"per_image.csv",output)
        print("known MPEG",src["id"],sum(r["saved"]>0 for r in output),flush=True)
    (folder/"witness.json").write_text(json.dumps(dict(first_escape=first,failures=failures),indent=2),encoding="utf-8")


if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.output:
        study.OUT=a.output.resolve();study.LOCAL=study.OUT/"polygons"
    run()
