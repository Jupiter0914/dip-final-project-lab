"""Restore only known POLY02 research inputs from the previous private offline release."""
import argparse
import hashlib
import zipfile
from pathlib import Path
from poly02.data import ROOT,rows,sha

V2="9c3e998bd3c464a42db840349f9ca6e5c63418e65c51ec6f319ad83a37413d79"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("archive",type=Path)
    a=p.parse_args()
    with a.archive.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=V2:raise ValueError("Unexpected POLY02 review archive")
    wanted=[(r["file"],r["sha256"]) for r in rows(ROOT/"records/poly02/samples.csv")]
    # Restore only the existing dev baseline cache needed for the small single-ring checks.
    for r in rows(ROOT/"results/poly02/dev/per_image.csv"):
        if r["method"] in ("geometry","post_guard","post_xor"):
            wanted.append((f"local/poly02/dev/{r['id']}/{r['k']}-{r['method']}.poly",r["blob_sha256"]))
    with zipfile.ZipFile(a.archive) as z:
        for name,digest in wanted:
            path=(ROOT/name).resolve()
            if not path.is_relative_to(ROOT.resolve()): raise ValueError("Bad source path")
            raw=z.read(name)
            assert sha(raw)==digest
            if path.exists():
                if sha(path.read_bytes())!=digest:raise ValueError("Existing input differs: "+name)
            else:
                path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(raw)
    print("Recovered or verified",len(wanted),"registered inputs and prior baseline files")


if __name__=="__main__":main()
