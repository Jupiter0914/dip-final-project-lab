"""Separate seed variation within images from variation across images."""
from collections import defaultdict
import json
import numpy as np
from .data import OUT,ROOT,rows,save_rows


def main():
    folder=OUT/"pso"
    table=rows(folder/"trials.csv")
    groups=defaultdict(list)
    for r in table: groups[r["id"],r["k"]].append(r)
    summary=[]
    for (name,k),group in sorted(groups.items()):
        good=[r for r in group if r["status"]=="ok"]
        item=dict(id=name,k=k,seeds=len(group),valid=len(good),clipped_trials=sum(int(r.get("clipped_vertices") or 0)>0 for r in group))
        for key in ["iou","author_iou","xor","fp","fn","bf1","bf2","bf3","encode_ms","decode_ms","solver_ms"]:
            v=[float(r[key]) for r in good if r.get(key)]
            if v:
                item.update({key+"_mean":np.mean(v),key+"_sd":np.std(v,ddof=1) if len(v)>1 else "",
                             key+"_min":min(v),key+"_max":max(v)})
        summary.append(item)
    save_rows(folder/"by_source_seed.csv",summary)
    # Capture the completed handshake file, whose first write could precede the reader.
    run=json.loads((folder/"run.json").read_text(encoding="utf-8"))
    run["matlab"]=(ROOT/"local/poly02/pso/ready.txt").read_text(encoding="utf-8").splitlines()
    (folder/"run.json").write_text(json.dumps(run,indent=2),encoding="utf-8")


if __name__=="__main__": main()
