"""Development screen, then fixed-code evaluation, by source photo."""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
import psutil
from PIL import Image
from src.codec import silhouette,encode,decode
from src.method import fit
from src.metrics import metrics

cv2.setNumThreads(1)


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def inputs(source):
    path=ROOT/"data/trimaps"/(source["id"]+".png")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source["sha256"]:
        raise ValueError(f"Wrong source mask {path}")
    with Image.open(path) as im:
        return np.array(im)


def measure(source,trimap,k,method,grid,radii,save_dir=None):
    start=time.perf_counter_ns()
    mask,contour,common=silhouette(trimap)
    if method=="input":
        ok,data=cv2.imencode(".png",mask,[cv2.IMWRITE_PNG_COMPRESSION,9])
        if not ok:
            raise ValueError("Reference PNG encode failed")
        blob=data.tobytes()
        details={}
    else:
        vertices,details=fit(mask,contour,k,method,grid,radii)
        blob=encode(mask.shape,vertices)
    encoded=time.perf_counter_ns()
    if method=="input":
        predicted=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_GRAYSCALE)
    else:
        predicted=decode(blob)
    decoded=time.perf_counter_ns()
    if save_dir is not None and method!="input":
        file=save_dir/source["id"]/f"{k}-{method}.poly"
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(blob)
    return dict(id=source["id"],breed=source["breed"],partition=source["partition"],k=k,
                method=method,grid=grid,radii=",".join(map(str,radii)),h=mask.shape[0],w=mask.shape[1],
                n_contour=len(contour),bytes=len(blob),blob_sha256=hashlib.sha256(blob).hexdigest(),
                encode_ms=(encoded-start)/1e6,decode_ms=(decoded-encoded)/1e6,
                **common,**details,**metrics(mask,predicted))


def screen_specs(conf):
    yield "rdp",0,[]
    for grid in conf["grids"]:
        yield "dp",grid,[]
        for radii in conf["schedules"]:
            for method in ["geometry","raster"]:
                yield method,grid,radii


def fixed_specs(conf):
    return [(m,v["grid"],v["radii"]) for m,v in conf["methods"].items()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["screen","dev","confirm"])
    parser.add_argument("--output",type=Path,help="New empty destination for a reproduction")
    args=parser.parse_args()
    screen=args.stage=="screen"
    samples=read_csv(ROOT/"records/samples.csv")
    partition="confirm" if args.stage=="confirm" else "dev"
    selected=[s for s in samples if s["partition"]==partition]
    cfgpath=ROOT/"configs"/("screen.json" if screen else "fixed.json")
    cfg=json.loads(cfgpath.read_text(encoding="utf-8"))
    if args.stage=="confirm":
        from verify_lock import verify_lock
        verify_lock(ROOT)
    if screen:
        groups=defaultdict(list)
        for row in selected:
            groups[row["breed"]].append(row)
        selected=[s for group in groups.values() for s in group[:cfg["screen_photos_per_breed"]]]
    folder=args.output or ROOT/"results"/args.stage
    folder.mkdir(parents=True,exist_ok=False)
    local=folder/"polygons" if args.output else ROOT/"local"/args.stage
    specs=list(screen_specs(cfg)) if screen else fixed_specs(cfg)
    records=[]
    failures=[]
    start=time.perf_counter()
    for row in selected:
        image=inputs(row)
        for k in cfg["budgets"]:
            settings=specs+[("input",0,[])]
            settings=sorted(settings,key=lambda s:hashlib.sha256(repr((row["id"],k,s)).encode()).digest())
            for method,grid,radii in settings:
                try:
                    records.append(measure(row,image,k,method,grid,radii,None if screen else local))
                except ValueError as exc:
                    failures.append(dict(id=row["id"],k=k,method=method,grid=grid,radii=radii,error=str(exc)))
        if len(records) and len(records)%20==0:
            print(row["id"],len(records),"rows",flush=True)
    save_csv(folder/"per_image.csv",records)
    peak=psutil.Process().memory_info()
    info=dict(stage=args.stage,photos=len(selected),rows=len(records),wall_s=time.perf_counter()-start,
              peak_working_set_bytes=getattr(peak,"peak_wset",peak.rss),failures=failures,
              timer="perf_counter_ns; encode includes native foreground/contour extraction, fit and actual serialization; decoder validates polygon; I/O and scoring outside")
    (folder/"run.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    print(json.dumps({key:v for key,v in info.items() if key!="failures"}), "failures",len(failures))


if __name__=="__main__":
    main()
