"""Regenerate all donor/edge comparisons for the negative Oxford witness from packed bytes."""
import argparse
import csv
import json
import tempfile
import zipfile
from pathlib import Path
from poly02.core import exterior
from poly02.data import read_mask,rows,sha
from . import single_profile as profile
from .single import OUT,source_set


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    p.add_argument("--record",action="store_true",help="Write the verification receipt in the study output directory")
    args=p.parse_args()
    directory=args.output.resolve() if args.output else OUT
    files=directory/"cost_audit"
    expected=json.loads((files/"real_case.json").read_text())
    pool=[]
    for stage in ("support","support_rest"):
        f=directory/stage/"per_image.csv"
        if f.exists():pool.extend(rows(f))
    selected=min((r for r in pool if r["k"]=="32"),key=lambda r:(int(r["min_deletion_cost"]),r["id"]))
    assert expected["id"]==selected["id"]
    src=next(r for r in source_set()[0] if r["id"]==selected["id"])
    mask,c=exterior(read_mask(src),int(selected["k"]))
    previous=profile.LOCAL
    try:
        with tempfile.TemporaryDirectory(prefix="poly03-atomic-replay-") as tmp:
            tmp=Path(tmp)
            profile.LOCAL=tmp
            rel=selected["stationary_file"]
            with zipfile.ZipFile(directory/"polygons.zip") as z:
                binary=z.read(rel)
            assert sha(binary)==selected["stationary_sha"]
            target=tmp/rel
            target.parent.mkdir(parents=True)
            target.write_bytes(binary)
            profile.strong(mask,c,selected,tmp)
            got=json.loads((tmp/"real_case.json").read_text(encoding="utf-8"))
            for key in ("all_donor_edge_scores.csv","single_move_certificate.csv"):
                assert rows(files/key)==rows(tmp/key),key
            assert {k:v for k,v in expected.items() if k!="elapsed_s"}=={k:v for k,v in got.items() if k!="elapsed_s"}
    finally:
        profile.LOCAL=previous
    report=dict(id=expected["id"],k=expected["k"],all_joint_evaluations=expected["candidates"],donor_edge_groups=len(rows(files/"all_donor_edge_scores.csv")),
                single_slots=expected["certified_directed_neighbors"],identical_group_minima_and_counts=True,identical_reported_joint_polygon=True)
    if args.record:
        (files/"cold-run.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__":main()
