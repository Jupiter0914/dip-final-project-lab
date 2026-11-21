"""POLY04 input I/O and archive restoration; no method/score code is imported."""
import csv
import hashlib
import io
import os
import struct
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REC=ROOT/"records/poly04"
DATA=ROOT/"data/poly04"
OX=ROOT/"data/annotations.tar.gz"
LEMS=ROOT/"data/poly02/shapes-author.bin"
RGB=DATA/"archives/images.tar.gz"
OX_SHA="52425fb6de5c424942b7626b428656fcbd798db970a937df61750c0f1d358e91"
LEMS_SHA="f6a132c16ca4800fc9cfbe3d469a086599aba67783448362c0bc2275bf7e6d1c"
RGB_MD5="5c4f3ee8e5d25df40f4fd59a7f44e54c"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_hash(path,kind="sha256"):
    with path.open("rb") as f:
        return hashlib.file_digest(f,kind).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def binary(raw,dataset):
    with Image.open(io.BytesIO(raw)) as im:
        values=np.array(im)
    if dataset=="Oxford":
        fg=values==1
    elif dataset in ("PaperProbe","KnownView"):
        fg=values!=0
    elif dataset in ("LEMS","MPEG7","UPF"):
        bg=np.median([np.median(values[0,:]),np.median(values[:,0]),np.median(values[:,-1])])
        fg=values!=bg
    else:
        raise ValueError(dataset)
    if fg.ndim!=2:raise ValueError("Expected a scalar annotation")
    return np.ascontiguousarray(fg,dtype=np.uint8)


def pixels(a):
    h,w=a.shape
    return sha(struct.pack("<II",h,w)+np.packbits(a.ravel(),bitorder="big").tobytes())


def decode_binary_bytes(payload,row):
    a=binary(payload,row["dataset"])
    if pixels(a)!=row["pixel_sha256"]: raise ValueError("Different source pixels: "+row["id"])
    return a


def read_binary(row):
    raw=(ROOT/row["file"]).read_bytes()
    if sha(raw)!=row["raw_sha256"]:
        raise ValueError("Different source bytes: "+row["id"])
    return decode_binary_bytes(raw,row)


def keep(path,data):
    if path.exists():
        if path.read_bytes()!=data:raise ValueError(f"Existing data differs: {path}")
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)


def rgb_archive():
    if RGB.exists():
        if file_hash(RGB,"md5")!=RGB_MD5:raise ValueError("Oxford RGB archive digest mismatch")
        return
    RGB.parent.mkdir(parents=True,exist_ok=True)
    temp=RGB.with_suffix(".part")
    if temp.exists() and file_hash(temp,"md5")==RGB_MD5:
        temp.replace(RGB);return
    errors=[]
    for url in ("https://thor.robots.ox.ac.uk/datasets/pets/images.tar.gz","https://www.robots.ox.ac.uk/~vgg/data/pets/data/images.tar.gz"):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"DIP-course-reproduction/1"})
            with urllib.request.urlopen(req,timeout=90) as r,temp.open("wb") as out:
                while chunk:=r.read(2<<20):out.write(chunk)
            if file_hash(temp,"md5")!=RGB_MD5:raise ValueError("RGB checksum mismatch")
            temp.replace(RGB);return
        except (OSError,ValueError) as exc: errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors))


def restore():
    samples=rows(REC/"samples.csv")
    if file_hash(OX)!=OX_SHA or file_hash(LEMS)!=LEMS_SHA:raise ValueError("Original annotation archive mismatch")
    ox={r["member"]:r for r in samples if r["dataset"]=="Oxford"}
    with tarfile.open(OX,"r|gz") as t:
        for item in t:
            if item.name in ox:
                r=ox.pop(item.name);data=t.extractfile(item).read()
                if sha(data)!=r["raw_sha256"]:raise ValueError(item.name)
                keep(ROOT/r["file"],data)
    if ox:raise ValueError("Missing Oxford members")
    for r in samples:
        if r["dataset"]=="LEMS":
            data=subprocess.check_output(["tar","-xOf",str(LEMS),r["member"]])
            if sha(data)!=r["raw_sha256"]:raise ValueError(r["member"])
            keep(ROOT/r["file"],data)
        read_binary(r)
    print("Verified restored frozen masks",len(samples))


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["rgb-archive","restore"])
    a=p.parse_args()
    if a.action=="rgb-archive":
        rgb_archive();print(RGB.stat().st_size,file_hash(RGB))
    else:restore()
