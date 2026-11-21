"""Analytic cases and exhaustive 3x3 binary images for the full-mask format."""
import json
from pathlib import Path
import cv2
import numpy as np
from .maskcodec import extract,pack,decode,digital,correspondence,length,vector_ok,Renderer,Unsupported
from .full_data import ROOT,REC,MANIFEST
from poly02.data import rows,read_mask


def named():
    a=np.zeros((13,14),np.uint8)
    cases={"empty":a.copy(),"full":1-a}
    p=a.copy();p[0,0]=1;cases["one_border_pixel"]=p
    p=a.copy();p[6,7]=p[7,8]=1;cases["corner_touch"]=p
    p=a.copy();p[1:12,1:13]=1;p[5,6]=0;cases["one_pixel_hole"]=p
    p=a.copy();p[1:-1,1:-1]=1;p[3:-3,3:-3]=0;p[5:-5,5:-5]=1;cases["island_in_hole"]=p
    p=a.copy();p[1:5,1:5]=1;p[8:12,9:13]=1
    for i in range(4,9):p[i,i+1]=1
    cases["diagonal_neck"]=p
    p=a.copy();p[2:11,1:6]=1;p[2:11,8:13]=1;cases["near_components"]=p
    return cases


def main():
    results=[]
    space=[(f"3x3-{i}",np.array([(i>>j)&1 for j in range(9)],np.uint8).reshape(3,3)) for i in range(512)]
    real=[(r["id"],read_mask(r)) for r in rows(MANIFEST)]
    for name,raw in [*named().items(),*space,*real]:
        rings,par=extract(raw)
        b=pack(raw.shape,rings,par)
        rebuilt=decode(b)
        if not np.array_equal(raw,rebuilt) or correspondence(digital(raw),digital(rebuilt))!="ok":
            raise AssertionError((name,int((raw!=rebuilt).sum())))
        if not name.startswith("3x3-"):results.append(dict(id=name,rings=len(par),parents=par,vertices=sum(map(len,rings)),bytes=len(b),xor=0))
    a=np.zeros((12,16),np.uint8);a[1:4,1:4]=1;a[6:9,6:9]=1
    b=a.copy();b[6:9,6:9]=0;b[7:10,12:15]=1
    swapped=correspondence(digital(a),digital(b))
    assert swapped=="digital_overlap"
    x=np.ones((15,20),np.uint8);x[2:4,2:4]=0;x[5:8,9:12]=0
    y=x.copy();y[5:8,9:12]=1;y[9:12,15:18]=0
    assert correspondence(digital(x),digital(y))=="digital_overlap"
    assert extract(named()["island_in_hole"])[1]==[-1,0,1]
    assert digital(named()["corner_touch"]).nf==1 and digital(named()["one_pixel_hole"]).nh==1
    try: extract(np.zeros((1,16383),np.uint8))
    except Unsupported as exc: unsupported=str(exc)
    else: raise AssertionError("Expected unsupported coordinate field")
    print("512 exhaustive, fixtures, and",len(real),"real sources passed; displaced identities rejected")
    (REC/"full-fixtures.json").write_text(json.dumps(dict(exhaustive_3x3=512,unsupported_fixture=unsupported,same_counts_wrong_fg=swapped,
                              same_counts_wrong_hole="digital_overlap",sources=results),indent=2),encoding="utf-8")


if __name__=="__main__": main()
