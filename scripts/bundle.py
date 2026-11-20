"""Pack the committed research snapshot plus small offline source and polygon witnesses."""
import csv
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip()
    freeze=subprocess.check_output(["git","rev-parse","selection-freeze-v1"],text=True,cwd=ROOT).strip()
    if subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=ROOT).strip():
        raise RuntimeError("Bundle needs a clean committed snapshot")
    snapshot=subprocess.check_output(["git","archive","--format=zip",commit],cwd=ROOT)
    directory=ROOT/"dist"
    directory.mkdir(exist_ok=True)
    artifact=directory/"outline-review.zip"
    inventory=[]
    with zipfile.ZipFile(artifact,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as dst:
        def add(name,raw,expected=None):
            digest=hashlib.sha256(raw).hexdigest()
            if expected and digest!=expected:
                raise ValueError(name)
            inventory.append(dict(path=name,bytes=len(raw),sha256=digest))
            # Use fixed member timestamps for reproducible packaging with a fixed zlib.
            zi=zipfile.ZipInfo(name,(2020,1,1,0,0,0))
            dst.writestr(zi,raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
        with zipfile.ZipFile(io.BytesIO(snapshot)) as src:
            for name in sorted(src.namelist()):
                if not name.endswith("/"):
                    add(name,src.read(name))
            sources=list(csv.DictReader(io.StringIO(src.read("records/samples.csv").decode())))
            for r in sources:
                name=f"data/trimaps/{r['id']}.png"
                add(name,(ROOT/name).read_bytes(),r["sha256"])
            for stage in ("dev","confirm"):
                table=csv.DictReader(io.StringIO(src.read(f"results/{stage}/per_image.csv").decode()))
                for r in sorted(table,key=lambda x:(x["id"],int(x["k"]),x["method"])):
                    if r["method"]=="input":
                        continue
                    name=f"local/{stage}/{r['id']}/{r['k']}-{r['method']}.poly"
                    add(name,(ROOT/name).read_bytes(),r["blob_sha256"])
        add("BUNDLE-INFO.json",json.dumps(dict(commit=commit,freeze=freeze,offline="python scripts/replay.py"),
                                         indent=2).encode())
        buffer=io.StringIO(newline="")
        writer=csv.DictWriter(buffer,fieldnames=["path","bytes","sha256"],lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)
        zi=zipfile.ZipInfo("REVIEW-SHA256.csv",(2020,1,1,0,0,0))
        dst.writestr(zi,buffer.getvalue(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
    (directory/(artifact.name+".sha256")).write_text(digest+"  "+artifact.name+"\n",encoding="ascii")
    print(artifact.name,artifact.stat().st_size,digest)


if __name__=="__main__":
    main()
