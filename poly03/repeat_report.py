"""Preserve both process runs, including every varying CGAL output, without changing the first run."""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
import numpy as np
from poly02.data import rows,save_rows
from .full_data import ROOT,OUT,REC


def main(folder):
    dst=ROOT/"results/poly03/repetition"
    dst.mkdir(parents=True,exist_ok=False)
    keys=("id","budget","method")
    aa={tuple(r[k] for k in keys):r for r in rows(OUT/"per_image.csv")}
    bb={tuple(r[k] for k in keys):r for r in rows(folder/"per_image.csv")}
    assert set(aa)==set(bb) and len(aa)==980
    assert json.loads((OUT/"moves.json").read_text())==json.loads((folder/"moves.json").read_text())
    assert (OUT/"allocation_candidates.csv").read_bytes()==(folder/"allocation_candidates.csv").read_bytes()
    summary=[]
    for m in sorted({k[2] for k in aa}):
        keys_m=[k for k in aa if k[2]==m]
        changed=sum(aa[k].get("sha256","")!=bb[k].get("sha256","") for k in keys_m)
        split=sum(aa[k]["status"]!=bb[k]["status"] for k in keys_m)
        common=[k for k in keys_m if aa[k]["status"]==bb[k]["status"]=="success"]
        if not m.startswith("cgal_"):
            assert not changed and not split
        summary.append(dict(method=m,settings=len(keys_m),success1=sum(aa[k]["status"]=="success" for k in keys_m),
              success2=sum(bb[k]["status"]=="success" for k in keys_m),different_payloads=changed,status_changes=split,
              common_ok=len(common),mean_abs_iou_difference_pp=np.mean([abs(float(aa[k]["iou"])-float(bb[k]["iou"]))*100 for k in common])))
    save_rows(dst/"summary.csv",summary)
    shutil.copy2(folder/"per_image.csv",dst/"per_image.csv")
    shutil.copy2(folder/"run.json",dst/"run.json")
    (REC/"full-repetition.json").write_text(json.dumps(dict(settings_with_methods=len(aa),
            noncgal_statuses_and_payloads_match=True,all_atomic_trajectories_match=True,all_allocation_diagnostics_match=True,
            first_run_retained=True,second_run="complete raw-to-byte path includes full-canvas scratch allocation; CGAL variations retained"),indent=2),encoding="utf-8")
    print([(r["method"],r["different_payloads"],r["status_changes"]) for r in summary])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=ROOT/"local/poly03/full-accounted-repeat")
    main(p.parse_args().input)
