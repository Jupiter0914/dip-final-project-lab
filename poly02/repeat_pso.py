"""Re-run the unmodified frozen MATLAB wrapper in a fresh isolated experiment directory."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .data import ROOT,REC,rows


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True,help="A new directory, e.g. local/repeat-matlab")
    dest=p.parse_args().output.resolve()
    dest.mkdir(parents=True,exist_ok=False)
    for source in ("src","poly02","data/poly02/upf"):
        shutil.copytree(ROOT/source,dest/source,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    files=["scripts/prepare_data.py","records/poly02/samples.csv","configs/poly02/settings.json","results/dev/per_image.csv"]
    files.extend(r["file"] for r in rows(REC/"samples.csv") if r["stage"]=="dev")
    for name in files:
        target=dest/name
        target.parent.mkdir(exist_ok=True,parents=True)
        shutil.copy2(ROOT/name,target)
    subprocess.run([sys.executable,"-X","utf8","-m","poly02.pso"],cwd=dest,check=True)
    subprocess.run([sys.executable,"-X","utf8","-m","poly02.pso_summary"],cwd=dest,check=True)
    old=rows(ROOT/"results/poly02/pso/trials.csv")
    new=rows(dest/"results/poly02/pso/trials.csv")
    fields=("id","k","seed","status","blob_sha256")
    assert [tuple(r.get(k) for k in fields) for r in old]==[tuple(r.get(k) for k in fields) for r in new]
    print("All trial IDs, seed statuses and POL1 bytes reproduced in",dest)


if __name__=="__main__": main()
