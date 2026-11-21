"""Record prior source-derived target views, linked to their original raw inputs."""
import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .data import ROOT,DATA,REC,keep,rows,sha,pixels,binary
from .data_known import native_family,write_csv

def write_views():
    table=[]
    for origin in rows(REC/"known.csv"):
        dataset,name=origin["dataset"],origin["id"]
        if dataset=="Oxford" or (dataset=="MPEG7" and "POLY02_cross" in origin["stages"]) or (dataset=="UPF" and name=="Fish-a100"):
            raw=binary((ROOT/origin["file"]).read_bytes(),dataset)
            rings,_=cv2.findContours(raw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
            if not rings:raise ValueError("Existing v1/POLY02 target without foreground")
            full=np.zeros_like(raw)
            cv2.drawContours(full,[max(rings,key=cv2.contourArea)],-1,1,cv2.FILLED,cv2.LINE_8)
            variants=[("outer",full)]
            if "POLY03_detail" in origin["stages"]:variants.append(("outer_nn2",np.repeat(np.repeat(full,2,axis=0),2,axis=1)))
            for kind,view in variants:
                id_=f"{dataset}__{name}__{kind}"
                buf=io.BytesIO();Image.fromarray(view*255).save(buf,format="PNG")
                data=buf.getvalue();dest=DATA/"known/views"/(id_+".png")
                keep(dest,data)
                table.append(dict(dataset="KnownView",id=id_,parent_dataset=dataset,parent_id=name,parent_raw_sha256=origin["raw_sha256"],
                  member=f"{origin['member']}#{kind}",category=origin["category"],transform=kind,file=dest.relative_to(ROOT).as_posix(),
                  raw_sha256=sha(data),pixel_sha256=pixels(view),tight_d4_sha256=native_family(view),w=view.shape[1],h=view.shape[0]))
    assert len(table)==443
    write_csv(REC/"known-views.csv",table)
    print("407 previously scored outer targets and 36 explicit nearest-neighbor 2x geometry diagnostic inputs recorded")

if __name__=="__main__":write_views()
