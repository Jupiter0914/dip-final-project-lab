"""Sensitivity only: exact geometric-cost ties are resolved by lexicographic integer coordinates."""
import argparse
import hashlib
import io
import zipfile
import json
import subprocess
from collections import defaultdict
from pathlib import Path
import numpy as np
from poly02.data import rows,save_rows,read_mask
from .cgal_build import ROOT,kernel_command,linux_path
from .cgal_variation import LOCAL,OUT,EXE
from .full_data import MANIFEST
from .maskcodec import extract,Renderer,digital,correspondence,vector_ok,pack,decode,length

# One fresh native process per source, budget, cost and seed. Three full identical fits per process.
# The small Linux orchestrator avoids per-trial WSL startup and returns native trial vertices openly.
BATCH=r'''
import subprocess,sys,json,hashlib
items=json.loads(sys.stdin.read())
for key,item in items.items():
    payload=(item["payload"]+"\n").encode()
    for seed in (7,47):
        cmd=[sys.argv[1],item["cost"],str(seed),"3","xy"]
        p=subprocess.run(cmd,input=payload,stdout=subprocess.PIPE,check=True)
        for trial,line in enumerate(p.stdout.splitlines()):
            rec=json.loads(line)
            trace=hashlib.sha256(json.dumps(rec["events"],separators=(",",":")).encode()).hexdigest()
            print(json.dumps([key,seed,trial,trace,rec["ring_order"],rec["rings"]],separators=(",",":")))
'''


def compare(reference,other,variant):
    """A paired source contributes its mean across common successful budgets at the same rate."""
    by_source=defaultdict(list)
    n_common=only_exchange=only_cgal=neither=0
    for k,r in reference.items():
        cg=other[k]
        ex_ok=r["status"]=="success";cg_ok=cg["status"]=="success"
        if ex_ok and cg_ok:
            assert int(r["file_bytes"])==int(cg["file_bytes"])
            n_common+=1
            delta=int(cg["xor"])-int(r["xor"])
            by_source[k[0]].append((delta,delta/max(1,int(cg["xor"]))))
        elif ex_ok: only_exchange+=1
        elif cg_ok: only_cgal+=1
        else: neither+=1
    avg=np.array([np.mean(g,axis=0) for g in by_source.values()])
    rng=np.random.default_rng(3417)
    idx=rng.integers(len(avg),size=(10000,len(avg)))
    lo,hi=np.quantile(avg[:,1][idx].mean(axis=1),[.025,.975])
    return dict(variant=variant,budget_conditions=len(reference),common_success=n_common,exchange_only=only_exchange,
                cgal_only=only_cgal,both_rejected=neither,paired_sources=len(avg),
                exchange_xor_pixels_saved=avg[:,0].mean(),exchange_relative_xor_saved=avg[:,1].mean(),
                ci_lo=lo,ci_hi=hi,source_exchange_wins=int((avg[:,0]>0).sum()),source_ties=int((avg[:,0]==0).sum()),
                source_cgal_wins=int((avg[:,0]<0).sum()))


def encode_archive(directory,blobroot):
    members={r["blob"]:r for r in rows(directory/"xy-primary.csv") if r["blob"]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        for name,r in sorted(members.items()):
            b=(blobroot/name).read_bytes()
            assert len(b)==int(r["attempt_bytes"]) and hashlib.sha256(b).hexdigest()==r["sha256"]
            z.writestr(zipfile.ZipInfo(name,(2020,1,1,0,0,0)),b,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    target=directory/"encoded.zip"
    data=out.getvalue()
    if target.exists() and target.read_bytes()!=data:
        raise ValueError("Existing encoded archive differs")
    target.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def verify_files(directory,blobroot):
    source={r["id"]:r for r in rows(MANIFEST)}
    inputs={}
    count=0
    data=rows(directory/"xy-primary.csv")
    members={r["blob"] for r in data if r["blob"]}
    packed={}
    archive=directory/"encoded.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(members) and set(z.namelist())==members
            packed={name:z.read(name) for name in members}
    for r in data:
        if not r["blob"]:
            assert r["status"]=="below_proved_lower_bound"
            continue
        name=r["id"]
        if name not in inputs:
            raw=read_mask(source[name])
            dense,par=extract(raw)
            inputs[name]=(raw,par,digital(raw),sum(map(len,dense)))
        raw,par,ref,total=inputs[name]
        blob=packed[r["blob"]] if packed else (blobroot/r["blob"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest()==r["sha256"] and len(blob)==int(r["attempt_bytes"])
        from .maskcodec import unpack
        shape,rr,pp=unpack(blob)
        assert shape==raw.shape and pp==par and vector_ok(rr,par)==r["vector"]
        pred=decode(blob)
        error=int(np.count_nonzero(raw!=pred))
        assert error==int(r["attempt_xor"]) and correspondence(ref,digital(pred))==r["digital"]
        n=sum(map(len,rr))
        target=min(total,(int(r["budget"])-length(par,0))//4)
        assert n==int(r["actual_vertices"])
        assert (r["status"]=="success")==(n==target and r["digital"]=="ok" and len(blob)<=int(r["budget"]))
        if r["status"]=="success": assert error==int(r["xor"]) and len(blob)==int(r["file_bytes"])
        count+=1
    print(f"Independent stored-file replay: {count} POLY03 files, budgets, XOR and structure statuses matched.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,help="Fresh output for an independent recomputation")
    p.add_argument("--verify",action="store_true",help="Read frozen tables and actual archived PM3 output only; CGAL is not needed")
    p.add_argument("--pack-saved",action="store_true",help="Package recorded worker outputs in their original paths")
    p.add_argument("--blob-root",type=Path,help="Root containing the blobs/ directory")
    opts=p.parse_args()
    directory=opts.output or (OUT if opts.verify or opts.pack_saved else LOCAL/"rerun-cohort")
    blobroot=opts.blob_root or (LOCAL if opts.verify or opts.pack_saved else directory)
    if opts.pack_saved:
        print("encoded.zip SHA-256",encode_archive(directory,blobroot))
    if opts.verify or opts.pack_saved:
        verify_files(directory,blobroot)
        return
    directory.mkdir(parents=True,exist_ok=False)
    table=rows(ROOT/"results/poly03/full/per_image.csv")
    repeated=ROOT/"local/poly03/full-accounted-repeat/per_image.csv"
    previous=rows(repeated) if repeated.exists() else []
    src={r["id"]:r for r in rows(MANIFEST)}
    inputs={}
    jobs={}
    output=[]
    reference={(r["id"],r["budget"]):r for r in table if r["method"]=="exchange_add"}
    for r in table:
        if not r["method"].startswith("cgal_"):continue
        name,budget,cost=r["id"],int(r["budget"]),r["method"].split("_")[-1]
        if name not in inputs:
            raw=read_mask(src[name]); rings,par=extract(raw)
            inputs[name]=raw,rings,par,digital(raw)
        raw,rings,par,ref=inputs[name]
        key=f"{name}/{budget}/{cost}"
        if budget<length(par,3*len(par)):
            output.append(dict(id=name,budget=budget,method=r["method"],status="below_proved_lower_bound",
                               reason="header+ring_metadata+three_vertices_per_ring",actual_vertices="",attempt_bytes="",file_bytes="",sha256="",xor="",blob=""))
            continue
        target=int(r["target_vertices"])
        coords=[f"{len(rings)} {target}"]
        for ring in rings:
            coords.append(str(len(ring)));coords.extend(f"{x} {y}" for x,y in ring)
        jobs[key]=dict(payload="\n".join(coords),cost=cost)
    # The exact cost-only comparator remains in the main paper's original two CGAL runs.
    # This binary alone uses the patched coordinate tie-break. Never overwrite those files.
    p=subprocess.run(kernel_command("python3","-c",BATCH,linux_path(EXE)),input=json.dumps(jobs).encode(),
                     capture_output=True,check=False)
    if p.returncode:raise RuntimeError(p.stderr.decode(errors="replace"))
    trials=[]
    variants={}
    for line in p.stdout.splitlines():
        key,seed,trial,tr_hash,order,coords=json.loads(line)
        name,b,cost=key.split("/");budget=int(b)
        raw,ring,par,ref=inputs[name]
        points=[np.asarray(v,np.int32) for v in coords]
        count=sum(map(len,points))
        vcheck=vector_ok(points,par)
        if vcheck!="ok": raise RuntimeError((key,vcheck))
        blob=pack(raw.shape,points,par)
        digest=hashlib.sha256(blob).hexdigest()
        variant_key=(key,digest)
        if variant_key not in variants:
            pred=decode(blob)
            dc=correspondence(ref,digital(pred))
            target=min(sum(map(len,ring)),(budget-length(par,0))//4)
            valid=(count==target and len(blob)<=budget and dc=="ok")
            reason=("wrong_vertex_count" if count!=target else dc)
            path=Path("blobs")/name/str(budget)/f"{cost}-{digest[:12]}.pm3"
            filename=blobroot/path
            filename.parent.mkdir(exist_ok=True,parents=True); filename.write_bytes(blob)
            variants[variant_key]=dict(id=name,budget=budget,method="cgal_"+cost,status="success" if valid else "search_no_valid_output",
                                      reason=reason,vector=vcheck,digital=dc,actual_vertices=count,attempt_bytes=len(blob),
                                      file_bytes=len(blob) if valid else "",sha256=digest,xor=int(np.count_nonzero(raw!=pred)) if valid else "",
                                      attempt_xor=int(np.count_nonzero(raw!=pred)),blob=path.as_posix())
        r=variants[variant_key]
        trials.append(dict(id=name,budget=budget,cost=cost,seed=seed,repeat=trial,ring_order=",".join(map(str,order)),
                           trace_sha256=tr_hash,sha256=digest,status=r["status"]))
        if seed==7 and trial==0:output.append(r)
    save_rows(directory/"xy-primary.csv",output)
    save_rows(directory/"xy-all-trials.csv",trials)
    comparisons=[]
    primary=[]
    for cost in ("squared","scaled"):
        m="cgal_"+cost
        for label,rlist in [("original",table),("repeat",previous),("xy",output)]:
            if not rlist: continue
            bykey={(r["id"],str(r["budget"])):r for r in rlist if r["method"]==m}
            comparisons.append(dict(cost=cost,**compare(reference,bykey,label)))
            primary_ref={k:r for k,r in reference.items() if int(k[1]) in (128,256,512)}
            primary.append(dict(cost=cost,**compare(primary_ref,bykey,label)))
    save_rows(directory/"exchange-comparison.csv",comparisons)
    save_rows(directory/"exchange-main-budgets.csv",primary)
    bykey=defaultdict(list)
    for trial in trials: bykey[trial["id"],trial["budget"],trial["cost"]].append(trial)
    summary=dict(eligible_conditions=len(jobs),runs=len(trials),seeds=[7,47],repeats_per_process=3,
                 distinct_output_files=len(variants),file_variation_conditions=sum(len({r["sha256"] for r in g})>1 for g in bykey.values()),
                 trace_variation_conditions=sum(len({r["trace_sha256"] for r in g})>1 for g in bykey.values()),
                 different_ring_order_conditions=sum(len({r["ring_order"] for r in g})>1 for g in bykey.values()),
                 other_original_format_conditions=len(output)-len(jobs))
    (directory/"xy-summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print("encoded.zip SHA-256",encode_archive(directory,blobroot))
    verify_files(directory,blobroot)
    print(json.dumps(summary))
    for r in comparisons: print(json.dumps(r))


if __name__=="__main__":main()
