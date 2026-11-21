"""Prespecified post-timing diagnostics for structural validity, additive screening and seed effects."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from poly03.allocation import curves,optimal,candidates,perimeter_counts
from poly03.maskcodec import pack,decode,score_mask
from poly02.data import rows,save_rows,sha
from .prepare import prepare_input,validate_rings,SUCCESS
from .engine import CFG as METHOD_CFG
from .engine_audit import audit_screen
from .study import ROOT,WORK,RESULTS,config,manifest,load_input,store_blob


def structural_cost(raw,budget):
    prep=prepare_input(raw,budget)
    info=dict(support_status=prep.status,reason=prep.reason,rings=prep.rings,lower_bound=prep.lower_bound,
              target_vertices=prep.target)
    if prep.status!=SUCCESS:return info,None,None
    if not prep.dense:
        blob=pack(raw.shape,[],[])
        return {**info,"status":"success","raw_reason":"ok","unconstrained_xor":0,"legal_xor":0,
                "validity_cost_xor":0,"tested_allocations":1},blob,blob
    bank=curves(prep.dense,prep.ref_masks,prep.render,prep.target)
    dp=optimal(bank,prep.target)
    naive=None;accepted=None
    if dp is not None:
        base=[b[k].points for b,k in zip(bank,dp)]
        naive=pack(raw.shape,base,prep.parents)
        info.update(raw_reason=validate_rings(prep,base),
                    unconstrained_xor=int(np.count_nonzero(prep.render.combined(base)!=raw)),
                    raw_counts=",".join(map(str,dp)))
    pool=candidates(bank,dp,perimeter_counts(prep.dense,prep.target),prep.target,METHOD_CFG)
    info.update(pool_size=len(pool),tested_allocations=0,status="search_no_valid_output")
    for c in pool:
        state=[b[k].points for b,k in zip(bank,c)]
        info["tested_allocations"]+=1
        if validate_rings(prep,state)!="ok":continue
        accepted=pack(raw.shape,state,prep.parents)
        x=int(np.count_nonzero(prep.render.combined(state)!=raw))
        info.update(status="success",legal_xor=x,validity_cost_xor=x-info["unconstrained_xor"] if naive else None,
                    legal_counts=",".join(map(str,c)))
        break
    return info,naive,accepted


def run(stage):
    cfg=config(stage)
    root=WORK/stage;folder=RESULTS/stage
    roster={(r["dataset"],r["id"]):r for r in manifest(cfg)}
    base=defaultdict(set);probe=defaultdict(set)
    first_session=cfg["session_ids"][0];first_rep=str(cfg["rep_ids"][0])
    exact_ids={(r["dataset"],r["id"]) for r in rows(folder/"runs.csv") if r["method"]=="exact" and int(r["budget"])==256}
    for r in rows(folder/"checkpoints.csv"):
        key=(r["dataset"],r["id"])
        b=int(r["budget"])
        if r["method"]=="seed" and r["round"]=="0":base[key,b].add(r["sha256"])
        if key in exact_ids and r["session"]==first_session and r["rep"]==first_rep and b==256 and r["method"] in ("exact","cross"):
            probe[key].add(r["sha256"])
    planned={(r["dataset"],r["id"],int(r["budget"])) for r in rows(folder/"runs.csv")}
    structure=[];audit=[];misses=[];costfiles={}
    for key,row in roster.items():
        raw,_=load_input(row,stage)
        for b in sorted({x[2] for x in planned if x[:2]==key}):
            s,naive,accepted=structural_cost(raw,b)
            record=dict(dataset=key[0],id=key[1],group=row.get("group") or row.get("family") or row.get("breed"),
                        stratum=row["stratum"],budget=b,**s)
            if "status" not in record:record["status"]=record["support_status"]
            for label,blob in [("raw_allocation_sha256",naive),("legal_seed_sha256",accepted)]:
                if blob:
                    digest=sha(blob);record[label]=digest
                    costfiles[digest]=blob
            if accepted is None:
                if base[key,b]:raise ValueError(("Recorded seed on failed source",key,b))
            elif base[key,b]!={sha(accepted)}:
                raise ValueError(("Seed reproduction failed",key,b,base[key,b]))
            structure.append(record)
        for digest in sorted(probe[key]):
            blob=(root/"blobs"/digest[:2]/(digest+".pm3")).read_bytes()
            report=audit_screen(raw,256,blob)
            fields={k:v for k,v in report.items() if k not in ("candidates","exact_choice","additive_choice")}
            audit.append(dict(dataset=key[0],id=key[1],sha256=digest,**fields))
            if report["valid_skipped_by_add"] or report["choices_differ"]:
                misses.append(dict(dataset=key[0],id=key[1],sha256=digest,**report))
    save_rows(folder/"structural_cost.csv",structure)
    save_rows(folder/"exact_screen.csv",audit)
    (folder/"exact_disagreements.json").write_text(json.dumps(misses,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    import zipfile
    with zipfile.ZipFile(root/"structure_attempts.zip","w",zipfile.ZIP_DEFLATED) as z:
        for k,v in sorted(costfiles.items()):z.writestr(k+".pm3",v)
    print("Structural inputs/budgets",len(structure),"exact-screen source/states",len(audit),"differences",len(misses))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["dev","confirm"])
    run(p.parse_args().stage)
