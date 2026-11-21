"""Paired developmental statistics and independent bit/metric checks for the single-ring trial."""
import argparse
from collections import defaultdict
from io import BytesIO
from pathlib import Path
import json
import struct
import zipfile
import numpy as np
from poly02.data import ROOT,REC,rows,save_rows,read_mask,sha
from poly02.verify import IndependentScore,reference
from src.codec import encode,decode,simple
from .single import OUT,source_set,METHODS
from .atomic import replace_vertex

METRICS=("saved","relative_saved","iou","bf1","bf2","bf3","full_ms","extra_ms","xor_evals","bf_tests","complete_xor_evals")
PAIRS=(("raster_pair","point"),("raster_pair","multi"),("raster_pair","random_pair"),
       ("raster_pair","geometry_pair"),("point","keep"),("multi","keep"),("multi","point"))


def source_means(table):
    groups=defaultdict(list)
    for row in table:
        row["relative_saved"]=int(row["saved"])/max(1,int(row["start_xor"]))
        groups[row["id"],int(row["k"]),row["method"]].append(row)
    by={}
    for key,items in groups.items():
        by[key]={name:float(np.mean([float(x[name]) for x in items])) for name in METRICS}
    return by


def stats():
    out_summary=[]
    paired=[]
    for mode in ("quota","time"):
        data=rows(OUT/mode/"per_image.csv")
        by=source_means(data)
        names=sorted({r["id"] for r in data})
        idx=np.random.default_rng(31009).integers(len(names),size=(10000,len(names)))
        for group in (16,32,"all"):
            ks=(16,32) if group=="all" else (group,)
            for method in METHODS:
                d=dict(mode=mode,k=group,method=method,n=len(names))
                for field in METRICS:
                    v=np.array([np.mean([by[name,k,method][field] for k in ks]) for name in names])
                    d[field]=float(v.mean())
                    if field=="saved":
                        d.update(up=int((v>0).sum()),tie=int((v==0).sum()),down=int((v<0).sum()))
                    if field in ("saved","relative_saved","full_ms","extra_ms"):
                        a,b=np.quantile(v[idx].mean(axis=1),[.025,.975])
                        d[field+"_lo"]=a; d[field+"_hi"]=b;d[field+"_median"]=np.median(v);d[field+"_p95"]=np.quantile(v,.95)
                out_summary.append(d)
            for method,base in PAIRS:
                for key in METRICS:
                    v=np.array([np.mean([by[name,k,method][key]-by[name,k,base][key] for k in ks]) for name in names])
                    a,b=np.quantile(v[idx].mean(axis=1),[.025,.975])
                    paired.append(dict(mode=mode,k=group,method=method,baseline=base,metric=key,n=len(names),mean=v.mean(),
                                       lo=a,hi=b,up=int((v>1e-12).sum()),tie=int((abs(v)<=1e-12).sum()),down=int((v< -1e-12).sum()),
                                       worst=names[v.argmin()],worst_value=v.min(),best=names[v.argmax()],best_value=v.max()))
    save_rows(OUT/"summary.csv",out_summary)
    save_rows(OUT/"paired_summary.csv",paired)
    if (OUT/"mpeg/per_image.csv").exists():
        external=rows(OUT/"mpeg/per_image.csv")
        domain=sorted({r["id"] for r in external})
        stats_out=[]
        for ids_k in ((16,),(32,),(16,32)):
            for field in ("saved","relative_saved"):
                values=[]
                for name in domain:
                    group=[r for r in external if r["id"]==name and int(r["k"]) in ids_k]
                    values.append(np.mean([int(r["saved"]) if field=="saved" else int(r["saved"])/max(1,int(r["stationary_xor"])) for r in group]))
                v=np.asarray(values)
                ix=np.random.default_rng(31009).integers(len(v),size=(10000,len(v)))
                lo,hi=np.quantile(v[ix].mean(1),[.025,.975])
                stats_out.append(dict(k=ids_k[0] if len(ids_k)==1 else "all",metric=field,n=len(v),
                                      mean=v.mean(),lo=lo,hi=hi,up=int((v>0).sum()),tie=int((v==0).sum()),down=int((v<0).sum())))
        save_rows(OUT/"mpeg/paired_summary.csv",stats_out)


def audit(write=False):
    sources={r["id"]:r for r in rows(REC/"samples.csv") if r["stage"] in ("dev","cross")}
    verifier={}
    records=[]
    covered=set()
    geometry_counts={}
    with zipfile.ZipFile(OUT/"polygons.zip") as pack:
        assert pack.testzip() is None
        def verify_file(file,digest,target):
            raw=pack.read(file)
            assert sha(raw)==digest
            code,w,h,k=struct.unpack("<4sHHH",raw[:10])
            p=np.frombuffer(raw,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            assert code==b"POL1" and (h,w)==target.shape and len(p)==k and simple(p)
            covered.add(file)
            return decode(raw)
        for mode in ("quota","time","stagnation","support","support_rest","mpeg"):
            path=OUT/mode/"per_image.csv"
            if not path.exists():continue
            table=rows(path)
            for row in table:
                name=row["id"];k=int(row["k"])
                if name not in verifier:
                    target=reference(read_mask(sources[name]))
                    verifier[name]=(target,IndependentScore(target))
                target,scorer=verifier[name]
                pred=verify_file(row["file"],row["sha256"],target)
                values=scorer.measure(pred)
                assert all(abs(float(row[k])-v)<1e-12 for k,v in values.items())
                assert values["bf2"]>=float(row["bf2_floor"])-1e-12
                if "stationary_file" in row:
                    fixed=verify_file(row["stationary_file"],row["stationary_sha"],target)
                    assert int(np.count_nonzero(fixed!=target))==int(row["stationary_xor"])
                extra_geom=int(row.get("extra_geometric_guide_evals") or 0)
                if row.get("method")=="geometry_pair" and "extra_geometric_guide_evals" not in row:
                    # The captured initial run accepted no pair and built exactly one guide.
                    assert int(row["raw_accepts"])==0 and int(row["guide_rounds"])==1
                    cache=(name,k)
                    if cache not in geometry_counts:
                        from .single_search import pool
                        from poly02.core import exterior
                        curve=exterior(read_mask(sources[name]),k)[1]
                        vertices=np.frombuffer(pack.read(row["file"]),offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
                        targets,_=pool(curve,vertices)
                        geometry_counts[cache]=k+len(targets)
                    extra_geom=geometry_counts[cache]
                records.append(dict(mode=mode,id=name,k=k,method=row.get("method","raster_pair"),seed=row.get("seed",""),
                                    extra_geometric_guide_evals=extra_geom,legality_checks=row.get("geometry_tests",""),
                                    status="success",vector_simple=True,bf2_floor_met=True,failure_reason="",
                                    actual_bytes=int(row["actual_bytes"]),full_ms=float(row["full_ms"]),
                                    xor_evals=row.get("xor_evals",row.get("complete_xor_evals","")),
                                    full_xor_evals=row.get("complete_xor_evals",""),**values,file=row["file"],sha256=row["sha256"]))
            if mode in ("quota","time"):
                failures=json.loads((OUT/mode/"run.json").read_text())["failures"]
                records.extend(dict(mode=mode,status="search_failed",failure_reason=r["error"],**r) for r in failures)
        assert covered==set(pack.namelist())
    if write:
        save_rows(OUT/"all_outputs.csv",records)
    else:
        published=rows(OUT/"all_outputs.csv")
        assert [(r["file"],r["sha256"]) for r in published]==[(r["file"],r["sha256"]) for r in records]
    control=json.loads((OUT/"cost_audit/analytic_control.json").read_text())
    case=json.loads((OUT/"cost_audit/real_case.json").read_text())
    shape=tuple(case["shape"]);target,score=verifier[case["id"]]
    before=np.array(case["stationary"],np.int32)
    after=replace_vertex([before],0,case["donor"],0,case["edge"],case["insert_xy"])[0]
    assert np.array_equal(after,case["final_trial"])
    assert int(np.count_nonzero(decode(encode(shape,before))!=target))==case["stationary_xor"]
    import cv2
    observed=np.zeros(shape,np.uint8)
    cv2.fillPoly(observed,[after],1,lineType=cv2.LINE_8)
    assert score.measure(observed)["xor"]==case["final_xor"]
    assert case["eligible_point_neighbors"]==0 and case["certified_directed_neighbors"]==32*32
    from fractions import Fraction
    from .single_profile import independent_scan
    mpeg=json.loads((OUT/"mpeg/witness.json").read_text())["first_escape"]
    real_mpeg=None
    if mpeg:
        tgt,independent=verifier[mpeg["id"]]
        p=np.asarray(mpeg["stationary"],np.int32)
        q=replace_vertex([p],0,mpeg["donor"],0,mpeg["edge"],mpeg["xy"])[0]
        assert np.array_equal(q,mpeg["after"])
        before=independent.measure(decode(encode(tgt.shape,p)))
        after=independent.measure(decode(encode(tgt.shape,q)))
        floor=Fraction(mpeg["floor_num"],mpeg["floor_den"])
        assert after["xor"]<before["xor"] and after["bf2"]>=float(floor)-1e-12
        scan=independent_scan(tgt,p,floor)
        saved=rows(OUT/"mpeg/escape_point_certificate.csv")
        assert [r["status"] for r in scan]==[r["status"] for r in saved]
        real_mpeg=dict(id=mpeg["id"],k=mpeg["k"],before=int(before["xor"]),after=int(after["xor"]),single_neighbors=len(scan),strict_escape=True)
    recheck=independent_scan(target,np.asarray(case["stationary"],np.int32),Fraction(*case["floor"]))
    assert [r["status"] for r in recheck]==[r["status"] for r in rows(OUT/"cost_audit/single_move_certificate.csv")]
    verified_winners=0
    mpeg_rows={(r["id"],r["k"]):r for r in rows(OUT/"mpeg/per_image.csv")}
    with zipfile.ZipFile(OUT/"polygons.zip") as z:
        for winner in rows(OUT/"mpeg/winners.csv"):
            row=mpeg_rows[winner["id"],winner["k"]]
            b=z.read(row["stationary_file"]);a=z.read(row["file"])
            p=np.frombuffer(b,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)
            i,e=int(winner["donor"]),int(winner["edge"])
            xy=[int(winner["new_x"]),int(winner["new_y"])]
            q=replace_vertex([p],0,i,0,e,xy)[0]
            target,independent=verifier[winner["id"]]
            assert encode(target.shape,q)==a
            removed=np.delete(p,i,axis=0);inserted=np.insert(p,e+1,xy,axis=0)
            for key,pts in (("deletion_only_xor",removed),("insertion_only_xor",inserted)):
                tmp=np.zeros_like(target)
                cv2.fillPoly(tmp,[pts],1,lineType=cv2.LINE_8)
                assert int(np.count_nonzero(tmp!=target))==int(winner[key])
            assert independent.measure(decode(a))["bf2"]>=float(winner["floor"])-1e-12
            verified_winners+=1
    ans=dict(source_contents=len(verifier),oxford_photos=36,known_mpeg_shapes=10,observed_mpeg_winners=verified_winners,mpeg_escape=real_mpeg,zip_polygons=len(covered),evaluated_rows=len(records),all_saved_scores_independently_verified=True,
             positive_control=[control["before_xor"],control["intermediate_xor"],control["final_xor"]],
             strong_witness_id=case["id"],strong_witness_k=case["k"],strong_joint_candidates=case["candidates"],
             joint_raw_improvements=case["strict_raw"],joint_bf2_improvements=case["strict_floor"])
    if write:
        (OUT/"verification.json").write_text(json.dumps(ans,indent=2),encoding="utf-8")
    else:
        assert ans==json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    print(json.dumps(ans))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["stats","audit","both"])
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.output: OUT=args.output.resolve()
    if args.mode in ("stats","both"): stats()
    if args.mode in ("audit","both"): audit(write=args.mode=="both")
