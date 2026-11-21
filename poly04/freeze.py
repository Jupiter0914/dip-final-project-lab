"""Check the production code, input roster and statistical policy fixed before confirmation."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/"records/poly04/freeze-lock.json"
TAG="poly04-confirm-freeze-v1"


def normalized(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n",b"\n")).hexdigest()


def freeze():
    files=set()
    for where,patterns in [
        ("poly04",["*.py"]),("poly03",["*.py","*.cpp"]),("poly02",["*.py"]),
        ("src",["*.py"]),("configs/poly04",["*.json","*.txt"]),("configs/poly03",["*.json"]),
        ("configs/poly02",["*.json"]),("records/poly04",["samples.csv","known.csv","known-views.csv","known-summary.json","data-protocol.md","data-audit.json","data-selection.json","data-links.csv","data-screening.csv","analysis-protocol.md","engine-methods.md","freeze.md","development-decision.md"]),
        ("records/poly03",["full-sources.csv"]),("scripts",["prepare_data.py"])
    ]:
        for patt in patterns:files.update((ROOT/where).glob(patt))
    for p in ("results/poly03/full/per_image.csv","records/samples.csv","records/poly02/samples.csv","requirements.txt"):
        files.add(ROOT/p)
    if LOCK.exists():raise FileExistsError(LOCK)
    output={p.relative_to(ROOT).as_posix():normalized(p) for p in sorted(files)}
    LOCK.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print("Frozen inputs and executable files",len(output))


def verify(offline=False):
    if not offline:
        committed=subprocess.check_output(["git","show",TAG+":records/poly04/freeze-lock.json"],cwd=ROOT)
        if committed.replace(b"\r\n",b"\n")!=LOCK.read_bytes().replace(b"\r\n",b"\n"):
            raise ValueError("Freeze manifest does not match the commit")
    for name,digest in json.loads(LOCK.read_text(encoding="utf-8")).items():
        if normalized(ROOT/name)!=digest:raise ValueError("Changed after freeze: "+name)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["lock","verify"])
    a=p.parse_args()
    if a.action=="lock":freeze()
    else:verify();print("POLY04 scientific freeze verified")
