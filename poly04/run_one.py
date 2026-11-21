"""Observe a PM31 file being delivered from a single source and save the chosen checkpoint."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from poly02.data import rows
from poly03.maskcodec import decode,score_mask
from .engine import encode
from .study import CFG,REC,RESULTS,config,manifest,load_input


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument("--file",type=Path,help="Single-channel nonzero foreground PNG")
    source.add_argument("--id",help="Registered confirmation ID")
    p.add_argument("--method",choices=["seed","within_full","cross","cgal","cgal_within","exact"],default="cross")
    p.add_argument("--budget",type=int,default=256);p.add_argument("--deadline",type=float,default=100)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.file:
        if a.file.resolve()==a.output.resolve():p.error("Choose a different output file")
        with Image.open(a.file) as im:
            pixels=np.asarray(im)
            if pixels.ndim!=2:p.error("Provide a single-channel binary image")
            raw=np.ascontiguousarray(pixels!=0,np.uint8)
    else:
        src=next((s for s in manifest(config("confirm")) if s["id"]==a.id),None)
        if src is None:p.error("Unknown registered input")
        raw,_=load_input(src,"confirm")
    events=[]
    def receive(blob,event):
        now=time.perf_counter_ns()
        events.append((blob,event["round"],event["serialized_ms"],(now-event["start_ns"])/1e6))
    result=encode(raw,a.budget,a.method,receive,max_ms=max(a.deadline,200),max_rounds=8)
    ready=[ev for ev in events if ev[3]<=a.deadline]
    print(json.dumps(dict(status=result["status"],reason=result["reason"],search_end_ms=result["end_ms"],
        checkpoints=[dict(round=r,serialized_ms=s,delivered_ms=t,bytes=len(b)) for b,r,s,t in events])))
    if not ready:raise SystemExit("No eligible file was received by the requested observation time")
    blob,r,s,t=ready[-1]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(blob)
    print(json.dumps(dict(chosen_round=r,actual_bytes=len(blob),delivered_ms=t,**score_mask(raw,decode(blob)))))


if __name__=="__main__":main()
