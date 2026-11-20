"""Build the fixed release or independently check its files, metrics and example decisions."""
import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import shutil
import tempfile
from fractions import Fraction
import zipfile
from pathlib import Path
import numpy as np
from src.codec import decode
from .core import exterior
from .data import ROOT,OUT,REC,DATA,CFG,read_mask,rows,sha
from .lock import norm,verify
from .run import execute
from .verify import IndependentScore,reference


def numerical_checks():
    # Independent slow reference: eligible moves in v1 direction order, strict exact IoU.
    from src.baselines import root_contour
    from src.codec import simple,encode
    from .core import initial
    from .analyze import analyze,decide
    cfg=json.loads(CFG.read_text())
    sample=next(r for r in rows(REC/"samples.csv") if r["stage"]=="dev")
    for k in cfg["main_k"]:
        mask,curve=exterior(read_mask(sample),k)
        curve=root_contour(curve)
        ids,_=initial(curve,k,cfg["grid"])
        points=curve[ids].copy()
        def iou(p):
            predicted=decode(encode(mask.shape,p))
            return Fraction(int((mask & predicted).sum()),int((mask | predicted).sum()))
        value=iou(points)
        for sweep,step in enumerate(cfg["radii"]):
            order=range(k) if sweep%2==0 else reversed(range(k))
            for j in order:
                best=points
                for dy in (-step,0,step):
                    for dx in (-step,0,step):
                        if not(dx or dy): continue
                        cand=points.copy()
                        cand[j]+=[dx,dy]
                        if np.any(cand[j]<0) or np.any(cand[j]>=[mask.shape[1],mask.shape[0]]) or not simple(cand): continue
                        score=iou(cand)
                        if score>value: value,best=score,cand
                points=best
        expected=ROOT/"local/poly02/dev"/sample["id"]/f"{k}-local_iou.poly"
        assert encode(mask.shape,points)==expected.read_bytes()
    with tempfile.TemporaryDirectory(prefix="poly02-stat-audit-") as tmp:
        for stage in ("new","cross"):
            folder=Path(tmp)/stage
            folder.mkdir()
            for name in ("per_image.csv","run.json"): shutil.copy2(OUT/stage/name,folder/name)
            analyze(folder)
            for name in ("summary.csv","paired.csv","paired_summary.csv"):
                assert norm(folder/name)==norm(OUT/stage/name)
            if stage=="new":
                decide(folder)
                assert json.loads((folder/"decision.json").read_text())==json.loads((OUT/stage/"decision.json").read_text())


def supplementary():
    verify(offline=True)
    old=rows(ROOT/"records/samples.csv")
    src=rows(REC/"samples.csv")
    old_sha={r["sha256"] for r in old}
    old_ids={r["id"] for r in old}
    new=[r for r in src if r["stage"]=="new"]
    assert len(src)==306 and len({r["sha256"] for r in src})==306
    assert len(new)==200 and len({r["group"] for r in new})==25
    assert not old_sha & {r["sha256"] for r in new} and not old_ids & {r["id"] for r in new}
    author=json.loads((REC/"resources.json").read_text(encoding="utf-8"))
    assert sha((DATA/"upf.zip").read_bytes())==author["upf.zip"]["sha256"]
    with zipfile.ZipFile(DATA/"upf.zip") as z:
        assert z.testzip() is None
        for name,digest in author["source_members"].items():
            assert sha(z.read(name))==sha((DATA/"upf"/name).read_bytes())==digest
    catalog={r["id"]:r for r in src}
    cfg=json.loads(CFG.read_text())
    fits=0
    for r in rows(OUT/"cases.csv"):
        name,k=r["id"],int(r["k"])
        raw=read_mask(catalog[name])
        for m in (r["before"],r["after"]):
            b,_=execute(raw,k,m,cfg)
            assert b==(ROOT/"local/poly02/new"/name/f"{k}-{m}.poly").read_bytes()
            fits+=1
    demo=OUT/"demo"
    witness=json.loads((demo/"witness.json").read_text(encoding="utf-8"))
    target=reference(read_mask(catalog[witness["id"]]))
    score=IndependentScore(target)
    for method,row in witness["methods"].items():
        blob=(demo/(method+".poly")).read_bytes()
        assert blob==(ROOT/"local/poly02/new"/witness["id"]/f"{witness['k']}-{method}.poly").read_bytes()
        assert sha(blob)==row["scores"]["blob_sha256"]
    outcomes=[]
    for r in witness["moves"]:
        label="accepted" if r["accepted"] else "rejected"
        values=[]
        for side in ("before","after"):
            actual=score.measure(decode((demo/f"{label}-{side}.poly").read_bytes()))
            assert all(abs(v-r[side][key])<1e-12 for key,v in actual.items())
            values.append(actual)
        assert values[1]["xor"]<values[0]["xor"]
        assert (values[1]["bf2"]>=r["floor"]-1e-12)==r["accepted"]
        outcomes.append(label)
    assert set(outcomes)=={"accepted","rejected"}
    return dict(author_members=len(author["source_members"]),unique_inputs=len(src),real_case_refits=fits,demo_decisions=outcomes)


def pack():
    git=lambda *a:subprocess.check_output(["git",*a],cwd=ROOT)
    if git("status","--porcelain","--untracked-files=all").strip():
        raise ValueError("Commit the intended release snapshot first")
    commit=git("rev-parse","HEAD").decode().strip()
    freeze=git("rev-parse","poly02-freeze-v1").decode().strip()
    path=ROOT/"dist/poly02-review.zip"
    path.parent.mkdir(exist_ok=True)
    inventory=[]
    used=set()
    def store(dst,name,data,listed=True):
        if name in used: raise ValueError("Duplicate ZIP path "+name)
        used.add(name)
        zi=zipfile.ZipInfo(name,(2020,1,1,0,0,0))
        dst.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
        if listed: inventory.append(dict(path=name,bytes=len(data),sha256=sha(data)))
    with zipfile.ZipFile(path,"w") as dst:
        with zipfile.ZipFile(io.BytesIO(git("archive","--format=zip",commit))) as code:
            for name in sorted(code.namelist()):
                if not name.endswith("/"): store(dst,name,code.read(name))
        sources=rows(REC/"samples.csv")
        for row in sources:
            name=row["file"]
            raw=(ROOT/name).read_bytes()
            assert sha(raw)==row["sha256"]
            store(dst,name,raw)
        for stage in ["dev","dev_curve","new","cross","curve"]:
            for row in rows(OUT/stage/"per_image.csv"):
                name=f"local/poly02/{stage}/{row['id']}/{row['k']}-{row['method']}.poly"
                raw=(ROOT/name).read_bytes()
                assert sha(raw)==row["blob_sha256"]
                store(dst,name,raw)
        for row in rows(OUT/"pso/trials.csv")+rows(OUT/"pso/controls.csv"):
            if "seed" in row:
                if row["status"]!="ok": continue
                name=f"local/poly02/pso/polygons/{row['id']}/{row['k']}-{row['seed']}.poly"
            else:
                name=f"local/poly02/pso/control-polygons/{row['id']}/{row['k']}-{row['method']}.poly"
            raw=(ROOT/name).read_bytes()
            assert sha(raw)==row["blob_sha256"]
            store(dst,name,raw)
        for source in [DATA/"upf.zip",*sorted((DATA/"upf").rglob("*"))]:
            if source.is_file():
                store(dst,source.relative_to(ROOT).as_posix(),source.read_bytes())
        store(dst,"POLY02-INFO.json",json.dumps(dict(commit=commit,freeze=freeze,offline="python -X utf8 -m poly02.review audit"),indent=2).encode())
        buf=io.StringIO(newline="")
        w=csv.DictWriter(buf,fieldnames=["path","bytes","sha256"],lineterminator="\n")
        w.writeheader()
        w.writerows(inventory)
        store(dst,"POLY02-SHA256.csv",buf.getvalue().encode(),False)
    digest=sha(path.read_bytes())
    path.with_name(path.name+".sha256").write_text(digest+"  "+path.name+"\n",encoding="ascii")
    print(commit,path.stat().st_size,digest,len(inventory))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["build","audit","examples"])
    a=p.parse_args()
    if a.action=="build": pack()
    else:
        if a.action=="audit":
            subprocess.run([sys.executable,"-X","utf8","-m","poly02.verify"],cwd=ROOT,check=True)
            numerical_checks()
        print(json.dumps(supplementary()))
