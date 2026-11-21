"""A simple competing strategy for the six known feasibility triggers, same 64 structure checks."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from .allocation import curves
from .repair import ordered_allocations
from .maskcodec import Renderer,extract,length,vector_ok,digital,correspondence,pack,decode,score_mask
from .full_data import ROOT,REC,LOCAL,OUT,MANIFEST
from poly02.data import rows,save_rows,read_mask


def phase_ring(p,frac):
    if frac==0:return p
    lengths=np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1)
    idx=int(np.searchsorted(np.cumsum(lengths),frac*sum(lengths)))
    return np.roll(p,-idx,axis=0)


def solve(raw,B):
    t=time.perf_counter_ns()
    orig,par=extract(raw)
    ren=Renderer(raw.shape);rf=digital(raw)
    assert np.array_equal(ren.combined(orig),raw)
    ref=[ren.ring(p) for p in orig]
    target=min(sum(map(len,orig)),(B-length(par,0))//4)
    tests=[]
    banks={}; streams={}; exhausted=set();winner=None
    for turn in range(64*4):
        idx=turn%4
        if idx in exhausted:continue
        if idx not in banks:
            bank=curves([phase_ring(p,idx/4) for p in orig],ref,ren,target)
            banks[idx]=bank
            streams[idx]=ordered_allocations(bank,target)
        allocation=next(streams[idx],None)
        if allocation is None:
            exhausted.add(idx)
            if len(exhausted)==4:break
            continue
        candidate=[b[k].points for b,k in zip(banks[idx],allocation)]
        mask=ren.combined(candidate)
        vec=vector_ok(candidate,par)
        dr=correspondence(rf,digital(mask))
        tests.append(dict(phase=idx,counts=allocation,vector=vec,digital=dr,xor=int(np.count_nonzero(mask!=raw))))
        if vec==dr=="ok":
            winner=candidate
            break
        if len(tests)==64:break
    blob=pack(raw.shape,winner,par) if winner is not None else None
    end=time.perf_counter_ns()
    info=dict(status="success" if blob else "search_no_valid_output",encode_ms=(end-t)/1e6,checks=len(tests),phase_banks=len(banks))
    if blob is not None:
        pred=decode(blob);done=time.perf_counter_ns()
        info.update(file_bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),decode_ms=(done-end)/1e6,**score_mask(raw,pred))
    return info,blob,tests


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=ROOT/"results/poly03/phase")
    a=p.parse_args()
    folder=a.output;folder.mkdir(parents=True,exist_ok=False)
    blobs=LOCAL/"blobs" if folder==ROOT/"results/poly03/phase" else folder/"blobs"
    data=rows(OUT/"per_image.csv");src={r["id"]:r for r in rows(MANIFEST)}
    records=[];logs=[]
    for r in data:
        if r["method"]!="independent_dp":continue
        if r["status"]!="search_no_valid_output":
            records.append(dict(id=r["id"],budget=r["budget"],triggered=0,status=r["status"],checks=int(r["status"]=="success"),
                   encode_ms=r["encode_ms"],xor=r.get("xor",""),iou=r.get("iou",""),sha256=r.get("sha256",""),file_bytes=r.get("file_bytes",""),
                   blob=r.get("blob","")))
            continue
        id_=r["id"];B=int(r["budget"]);data_row,file,trace=solve(read_mask(src[id_]),B)
        if file:
            rel=Path(id_)/str(B)/"phase.pm3"
            path=blobs/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(file)
            data_row["blob"]=rel.as_posix()
        records.append(dict(id=id_,budget=B,triggered=1,**data_row))
        logs.append(dict(id=id_,budget=B,tests=trace))
    save_rows(folder/"per_image.csv",records)
    (folder/"triggered.json").write_text(json.dumps(logs,separators=(",",":")),encoding="utf-8")
    print([(r["id"],r["budget"],r["status"],r["checks"]) for r in records if r["triggered"]])


if __name__=="__main__":main()
