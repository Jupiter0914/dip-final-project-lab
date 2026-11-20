"""Check frozen LF-normalized research files against the committed preregistration."""
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n",b"\n")).hexdigest()


def verify_lock(root):
    manifest=root/"records/freeze-lock.json"
    recorded=subprocess.check_output(["git","show","selection-freeze-v1:records/freeze-lock.json"],cwd=root)
    if recorded.replace(b"\r\n",b"\n")!=manifest.read_bytes().replace(b"\r\n",b"\n"):
        raise RuntimeError("Working freeze differs from committed freeze tag")
    for name,expected in json.loads(manifest.read_text(encoding="utf-8")).items():
        if digest(root/name)!=expected:
            raise RuntimeError("Changed after freeze: "+name)


if __name__=="__main__":
    verify_lock(Path(__file__).resolve().parents[1])
    print("Committed freeze and research file digests verified.")
