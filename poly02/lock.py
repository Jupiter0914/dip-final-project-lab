"""Validate versioned study inputs before evaluating any unopened sample."""
import json
import subprocess
from .data import ROOT,REC,sha


def norm(path):
    return sha(path.read_bytes().replace(b"\r\n",b"\n"))


def verify(offline=False):
    lock=REC/"freeze-lock.json"
    if not offline:
        committed=subprocess.check_output(["git","show","poly02-freeze-v1:records/poly02/freeze-lock.json"],cwd=ROOT)
        if committed.replace(b"\r\n",b"\n")!=lock.read_bytes().replace(b"\r\n",b"\n"):
            raise ValueError("Mismatch with published POLY02 freeze")
    for name,digest in json.loads(lock.read_text(encoding="utf-8")).items():
        if norm(ROOT/name)!=digest: raise ValueError("Changed after freeze: "+name)


if __name__=="__main__":
    verify()
    print("POLY02 freeze matches")
