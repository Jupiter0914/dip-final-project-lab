"""Two-round ablation and source-level checks on the 32 previously seen masks only."""
import json
from pathlib import Path
import time
import zipfile
import numpy as np
from poly02.data import ROOT,rows,save_rows,read_mask
from poly03.maskcodec import decode,score_mask
from .study import WORK,RESULTS,measure,canonical

METHODS=["seed","within_old","within_full_oldtri","within_full","cross_oldtri","cross_full_oldtri","cross","cgal","cgal_within","exact"]


def main():
    dst=RESULTS/"dev_fixed"
    dst.mkdir(parents=True,exist_ok=False)
    root=WORK/"dev_fixed"
    output=[];rounds=[];journals=[];keys=set()
    for src in rows(ROOT/"records/poly03/full-sources.csv"):
        raw=read_mask(src)
        for m in METHODS:
            res,evs=measure(raw,256,m,float("inf"),2,root)
            row=dict(dataset=src["dataset"],id=src["id"],group=src["group"],stratum=src["stratum"],method=m,
                     rings=res["rings"],status=res["status"],reason=res["reason"],end_ms=res["end_ms"],
                     search_end_ms=res["search_end_ms"],proposed_pairs=res["proposed_pairs"],accepted_moves=res["accepted_moves"],
                     cross_moves=res["cross_moves"],triangle_moves=res["triangle_moves"],rounds=res["rounds"])
            for log in res["round_log"]:
                rounds.append({**{k:row[k] for k in ("dataset","id","method","rings")},**log})
            for ev in evs: keys.add(ev["sha256"])
            if res.get("raw_cgal_sha256"):keys.add(res["raw_cgal_sha256"])
            if evs:
                last=evs[-1];first=evs[0]
                def evaluate(ev):
                    digest=ev["sha256"]
                    blob=(root/"blobs"/digest[:2]/(digest+".pm3")).read_bytes()
                    return score_mask(raw,decode(blob))
                row.update(sha256=last["sha256"],actual_bytes=last["payload_bytes"],initial_xor=evaluate(first)["xor"],
                           seed_sha256=first["sha256"],delivered_ms=last["delivered_ms"],**evaluate(last))
            output.append(row)
            journals.append(canonical(dict(dataset=src["dataset"],id=src["id"],method=m,result=res,events=evs)))
    save_rows(dst/"per_image.csv",output);save_rows(dst/"rounds.csv",rounds)
    with zipfile.ZipFile(dst/"evidence.zip","w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("calls.jsonl","\n".join(journals)+"\n")
        for d in sorted(keys):z.writestr("polygons/"+d+".pm3",(root/"blobs"/d[:2]/(d+".pm3")).read_bytes())
    print("Two-round known-source ablation",len(output),"method-source trials",len(keys),"actual polygons")


if __name__=="__main__":main()
