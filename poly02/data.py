"""Build source-grouped POLY02 manifests without using holdout metrics."""
import csv
import hashlib
import io
import json
import re
import subprocess
import tarfile
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image
from scripts.prepare_data import rank

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/poly02"
REC=ROOT/"records/poly02"
OUT=ROOT/"results/poly02"
CFG=ROOT/"configs/poly02/settings.json"
OLD_SHA="52425fb6de5c424942b7626b428656fcbd798db970a937df61750c0f1d358e91"
SHAPES_SHA="f6a132c16ca4800fc9cfbe3d469a086599aba67783448362c0bc2275bf7e6d1c"
ADAPT={"apple-1.gif","bat-1.gif","camel-1.gif"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def save_rows(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,list(dict.fromkeys(k for r in records for k in r)),lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def binary_from_bytes(raw,dataset):
    with Image.open(io.BytesIO(raw)) as im:
        if dataset=="Oxford":
            return np.ascontiguousarray(np.array(im)==1,np.uint8)
        values=np.array(im)
        background=np.median([np.median(values[0,:]),np.median(values[:,0]),np.median(values[:,-1])])
        return np.ascontiguousarray(values!=background,np.uint8)


def read_mask(row):
    raw=(ROOT/row["file"]).read_bytes()
    if sha(raw)!=row["sha256"]:
        raise ValueError("Source byte mismatch "+row["id"])
    return binary_from_bytes(raw,row["dataset"])


def remember_file(path,data):
    if path.exists():
        if path.read_bytes()!=data:
            raise ValueError("Published file changed: "+str(path))
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)


def add_row(records,dataset,stage,name,group,member,raw,curve=False):
    suffix=Path(member).suffix.lower()
    dest=DATA/"sources"/dataset/(name+suffix)
    remember_file(dest,raw)
    records.append(dict(dataset=dataset,stage=stage,id=name,group=group,member=member,file=dest.relative_to(ROOT).as_posix(),
                        sha256=sha(raw),curve=int(curve)))


def main():
    samples=rows(ROOT/"records/samples.csv")
    used_names={r["id"] for r in samples}
    used_hash={r["sha256"] for r in samples}
    ox=ROOT/"data/annotations.tar.gz"
    if sha(ox.read_bytes())!=OLD_SHA: raise ValueError("Oxford archive differs")
    records=[]
    with tarfile.open(ox) as tar:
        for r in samples:
            if r["partition"]=="dev":
                raw=tar.extractfile(r["member"]).read()
                assert sha(raw)==r["sha256"]
                add_row(records,"Oxford","dev",r["id"],r["breed"],r["member"],raw)
        groups=defaultdict(list)
        for line in tar.extractfile("annotations/test.txt").read().decode().splitlines():
            name=line.split()[0]
            groups[name.rsplit("_",1)[0]].append(name)
        for group in sorted({r["breed"] for r in samples if r["partition"]=="confirm"}):
            taken=0
            for name in sorted(groups[group],key=rank):
                if name in used_names: continue
                member=f"annotations/trimaps/{name}.png"
                raw=tar.extractfile(member).read()
                if sha(raw) in used_hash: continue
                used_hash.add(sha(raw))
                add_row(records,"Oxford","new",name,group,member,raw,curve=(taken==0))
                taken+=1
                if taken==8: break
            assert taken==8
    shapes=DATA/"shapes-author.bin"
    if sha(shapes.read_bytes())!=SHAPES_SHA: raise ValueError("Author RAR differs")
    names=subprocess.check_output(["tar","-tf",str(shapes)]).decode("utf-8").splitlines()
    by_class=defaultdict(list)
    for member in names:
        if not member.startswith("MPEG_7_resize/") or not member.lower().endswith(".gif"): continue
        leaf=Path(member).name
        if leaf in ("confusions.gif","shapedata.gif"): continue
        group=re.sub(r"-\d+\.gif$","",leaf,flags=re.I)
        if group==leaf: raise ValueError("Unknown MPEG class "+leaf)
        by_class[group].append(member)
    assert len(by_class)==70 and all(len(n)==20 for n in by_class.values())
    for group,members in sorted(by_class.items()):
        members=sorted(members,key=lambda s:sha(("poly02-mpeg|"+s).encode()))
        for member in members:
            if Path(member).name in ADAPT: continue
            raw=subprocess.check_output(["tar","-xOf",str(shapes),member])
            if sha(raw) in used_hash: continue
            used_hash.add(sha(raw))
            add_row(records,"MPEG7","cross",Path(member).stem,group,member,raw)
            break
    assert len(records)==306 and len({r["sha256"] for r in records})==306
    target=REC/"samples.csv"
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=list(records[0]),lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    remember_file(target,buf.getvalue().encode())
    print("36 Oxford development, 200 untouched Oxford test, 70 MPEG-7 classes; SHA",sha(target.read_bytes()))


if __name__=="__main__":
    main()
