
"""Read saved annotations and delivered bytes. Reconstruct figures without running a search."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from facts import ROOT, MAT, C, A, SAMPLES, one, select, rows

REPLAY=MAT/"replay"
ASSETS=REPLAY/"evidence"
MEDIA=REPLAY/"media"
BG=(250,249,244)
HIT=(55,68,71)
FP=(190,82,31)
FN=(37,123,158)
CASE_INFO={
    "typical_positive":("典型改善","取最接近正改善源中位数的源，再取最接近该源均值的共同重复。"),
    "nearest_zero":("持平","取源均值最接近零的源，再取最接近该源均值的共同重复。"),
    "worst":("最差退化","取源均值最小的源，再取最接近该源均值的共同重复。"),
    "structure_conflict":("局部覆盖下降","从已登记的局部冲突中取小部件覆盖下降的实际配对。"),
    "largest_supplement":("最大改善","附例取源均值最高的源，再取最接近该源均值的共同重复。"),
    "absolute_structure":("共同孔缩水","附例取已有面积比极小的有限孔与对应的实际重复。"),
    "nearest_zero+worst":("持平／最小源差","按原选择规则，最接近零和源均值最小两项选到了同一源。"),
}

def digest(b):
    return hashlib.sha256(b).hexdigest()


def file_for_blob(sha):
    return ASSETS/(sha+".pm3")


def ensure_bytes(dst, original, expected):
    if dst.exists():
        data=dst.read_bytes()
    else:
        data=original()
        if digest(data)!=expected:
            raise ValueError(f"Wrong external file for {dst}")
        dst.write_bytes(data)
    if digest(data)!=expected:
        raise ValueError(f"Changed evidence {dst}")
    return data


def unpack(data):
    magic,w,h,n=struct.unpack_from("<4sHHH",data)
    assert magic==b"PM31"
    offset=10
    rings=[]; parents=[]
    for i in range(n):
        parent,k=struct.unpack_from("<hH",data,offset)
        assert -1<=parent<i and k>=3
        ring=np.frombuffer(data,"<u2",2*k,offset+4).astype(np.int32).reshape(-1,2)
        parents.append(parent); rings.append(ring)
        offset+=4+4*k
    assert offset==len(data)==10+4*n+4*sum(map(len,rings))
    return (h,w),rings,parents


def decoded(sha):
    shape,rings,parents=unpack(file_for_blob(sha).read_bytes())
    h,w=shape
    plane=np.zeros((4*h+5,4*w+5),np.uint8)
    out=np.zeros(shape,bool)
    for ring in rings:
        plane.fill(0)
        cv2.fillPoly(plane,[ring],1,lineType=cv2.LINE_8)
        out^=plane[4:4*h+1:4,4:4*w+1:4].astype(bool)
    return out,rings,parents


def source(row, *, stored_only=False):
    name=Path(row["file"]).name
    dst=ASSETS/name
    if stored_only and not dst.is_file():
        raise FileNotFoundError(dst)
    ensure_bytes(dst,lambda:(ROOT/row["file"]).read_bytes(),row["raw_sha256"])
    with Image.open(dst) as im:
        v=np.array(im)
    if row["dataset"]=="Oxford":
        raw=v==1
    else:
        bg=np.median([np.median(v[0]),np.median(v[:,0]),np.median(v[:,-1])])
        raw=v!=bg
    packed=struct.pack("<II",*raw.shape)+np.packbits(raw,bitorder="big").tobytes()
    assert digest(packed)==row["pixel_sha256"]
    return raw,name


def paint(ref,out=None):
    rgb=np.empty((*ref.shape,3),np.uint8)
    rgb[:]=BG
    if out is None:
        rgb[ref]=HIT
    else:
        rgb[ref&out]=HIT
        rgb[out&~ref]=FP
        rgb[ref&~out]=FN
    return rgb


def counts(raw,out):
    fp=int((out&~raw).sum()); fn=int((raw&~out).sum())
    union=int((raw|out).sum())
    return fp,fn,fp+fn,int((raw&out).sum())/union if union else 1.


def save_image(array,name):
    Image.fromarray(array).save(MEDIA/name,optimize=True)
    return "media/"+name


def blob(sha):
    def origin():
        local=ROOT/"local/poly04/confirm"
        individual=local/"blobs"/sha[:2]/(sha+".pm3")
        if individual.is_file():
            return individual.read_bytes()
        with zipfile.ZipFile(local/"outputs.zip") as z:
            return z.read(sha+".pm3")
    return ensure_bytes(file_for_blob(sha),origin,sha)


def build():
    ASSETS.mkdir(parents=True,exist_ok=True); MEDIA.mkdir(parents=True,exist_ok=True)
    cards=[]
    for case in rows(C+"figures/figure-cases.csv"):
        id=case["id"]; ds=case["dataset"]
        if id=="Robot055" and case["reason"]=="structure_conflict":
            continue   # Identical delivered pair already included as the positive external case.
        spec=one(SAMPLES,dataset=ds,id=id)
        raw,name=source(spec)
        ft=dict(dataset=ds,id=id,budget=256,session=case["session"],rep=case["rep"])
        avg=one(A+"source_pairs.csv",dataset=ds,id=id,budget=256,deadline_ms=100,method="cross",baseline="within_full")
        title,why=CASE_INFO[case["reason"]]
        card=dict(id=id,dataset=ds,title=title,why=why,session=ft["session"],rep=ft["rep"],reason=case["reason"],
                  source_mean=float(avg["xor_saved"]),common=int(avg["common"]),crop=[int(case[k]) for k in ("crop_x","crop_y","crop_side")],
                  width=raw.shape[1],height=raw.shape[0],source_file="evidence/"+name,raw_sha256=spec["raw_sha256"],
                  pixel_sha256=spec["pixel_sha256"],raw=save_image(paint(raw),id+"-raw.png"),methods={})
        for m,side in [("within_full","baseline"),("cross","method")]:
            r=one(C+"per_run.csv",**ft,method=m,deadline_ms=100)
            trial=one(C+"runs.csv",**ft,method=m)
            checkpoints=select(C+"checkpoints.csv",**ft,method=m)
            ready=[p for p in checkpoints if int(p["received_ns"])-int(trial["clock_start_ns"])<=100_000_000]
            p=ready[-1]; sha=p["sha256"]
            assert sha==r["sha256"]==case[side+"_sha256"]
            size=len(blob(sha))
            out,rings,parents=decoded(sha)
            fp,fn,xor,iou=counts(raw,out)
            assert [fp,fn,xor,size]==[int(r[k]) for k in ("fp","fn","xor","actual_bytes")]
            assert abs(iou-float(r["iou"]))<1e-14
            times={k:float(r[k]) for k in ("serialized_ms","dispatch_ms","delivered_ms","search_end_ms","end_ms")}
            assert times["serialized_ms"]<=times["delivered_ms"]<=100 and times["end_ms"]>=times["search_end_ms"]
            card["methods"][m]=dict(sha256=sha,pm31="evidence/"+sha+".pm3",round=int(p["round"]),size=size,ring_points=list(map(len,rings)),
                    parents=parents,fp=fp,fn=fn,xor=xor,iou=iou,**times,mask=save_image(paint(out),id+"-"+m+".png"),
                    errors=save_image(paint(raw,out),id+"-"+m+"-errors.png"))
        card["repeat_delta"]=card["methods"]["within_full"]["xor"]-card["methods"]["cross"]["xor"]
        if case["kind"]:
            card["region"]=dict(kind=case["kind"],reference_id=int(case["reference_id"]),reference_area=int(case["reference_area"]),
                      within_area=int(case["baseline_region_area"]),cross_area=int(case["method_region_area"]),
                      within_recall=float(case["baseline_recall"]),cross_recall=float(case["method_recall"]))
        cards.append(card)
    # First accepted cross-ring step of the already selected maximum-improvement example.
    card=next(c for c in cards if c["reason"]=="largest_supplement")
    ft=dict(dataset=card["dataset"],id=card["id"],session=card["session"],rep=card["rep"],budget=256,method="cross")
    move=next(r for r in select(C+"rounds.csv",**ft) if r["accepted"]=="1" and r["cross"]=="1")
    n=int(move["round"])
    cp=[one(C+"checkpoints.csv",**ft,round=i) for i in (n-1,n)]
    raw,_=source(one(SAMPLES,dataset=card["dataset"],id=card["id"]))
    stages=[]
    for p in cp:
        sha=p["sha256"]; size=len(blob(sha)); out,rings,_=decoded(sha)
        stages.append(dict(sha256=sha,round=int(p["round"]),size=size,points=list(map(len,rings)),
                           xor=counts(raw,out)[2],received_ms=float(p["delivered_ms"])))
    before,after=stages
    d,r=int(move["donor"]),int(move["receiver"])
    assert [b-a for a,b in zip(before["points"],after["points"])]==[int(i==r)-int(i==d) for i in range(len(after["points"]))]
    assert before["size"]==after["size"] and [s["xor"] for s in stages]==[int(move[k]) for k in ("xor_before","xor_after")]
    action=dict(id=card["id"],session=ft["session"],rep=ft["rep"],donor=d,receiver=r,donor_vertex=int(move["donor_vertex"]),
                receiver_edge=int(move["receiver_edge"]),insert=json.loads(move["insert"]),before=before,after=after)
    data=dict(cases=cards,action=action)
    (REPLAY/"index.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return data


if __name__=="__main__":
    print(build()["action"])
