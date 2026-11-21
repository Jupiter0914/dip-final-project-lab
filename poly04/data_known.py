"""Build the complete pre-POLY04 exposure ledger without reading new confirmation candidates."""
import argparse
import csv
import io
import json
import re
import subprocess
import tarfile
import zipfile
from collections import Counter,defaultdict
import cv2
import numpy as np
from PIL import Image
from .data import DATA,REC,ROOT,OX,LEMS,OX_SHA,LEMS_SHA,RGB,sha,file_hash,rows,binary,pixels,keep


def write_csv(path,records):
    if not records: raise ValueError(f"Empty table {path}")
    fields=list(dict.fromkeys(k for r in records for k in r))
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fields,lineterminator="\n");writer.writeheader();writer.writerows(records)
    keep(path,buf.getvalue().encode("utf-8"))


def trimmed(mask):
    yy,xx=np.where(mask)
    if not len(xx):return np.zeros((1,1),np.uint8)
    return np.ascontiguousarray(mask[yy.min():yy.max()+1,xx.min():xx.max()+1],np.uint8)


def d4(a):
    for q in range(4):
        v=np.rot90(a,q)
        yield np.ascontiguousarray(v)
        yield np.ascontiguousarray(v[:,::-1])


def native_family(a):
    return min(pixels(v) for v in d4(trimmed(a)))


def paper_witnesses():
    pdf=ROOT/"data/poly02/paper.pdf"
    orig=file_hash(pdf)
    expected="b61b404a1cf4dff210c5832fa806506f53e432009425e21e2d0969709531a31a"
    if orig!=expected:raise ValueError("Known article PDF changed")
    out=DATA/"known/paper"
    out.mkdir(parents=True,exist_ok=True)
    for prefix,first,last in [("fig1",2,2),("fig2",6,6),("ex",9,12)]:
        subprocess.run(["pdfimages","-f",str(first),"-l",str(last),"-j",str(pdf),str(out/prefix)],check=True,capture_output=True)
    found=[]
    def record(pid,mask,obj):
        crop=trimmed(mask)
        buf=io.BytesIO();Image.fromarray(np.uint8(crop)*255).save(buf,format="PNG")
        path=out/(pid+".png");keep(path,buf.getvalue())
        found.append(dict(dataset="PaperProbe",id=pid,category="published-figure",member=obj.name+"#"+pid,
                          file=path.relative_to(ROOT).as_posix(),raw_sha256=sha(buf.getvalue()),
                          pixel_sha256=pixels(crop),tight_d4_sha256=native_family(crop),h=crop.shape[0],w=crop.shape[1],
                          parent_asset_sha256=orig,parent_image_sha256=file_hash(obj),historical_role="previously consulted published article; approximate visual exclusion probe"))
    for num in (0,1):
        obj=out/f"fig2-{num:03}.jpg"
        with Image.open(obj) as im: b=np.asarray(im.convert("L"))<110
        h,w=b.shape
        def split(proj,z,r):
            # Choose the nearest blank column/row to the nominal tile boundary.
            possible=np.where(~proj)[0];possible=possible[(possible>z-r)&(possible<z+r)]
            return int(possible[np.argmin(abs(possible-z))]) if len(possible) else z
        cy=split(b.any(1),h//2,h//6)
        for j,canvas in enumerate((b[:cy],b[cy:])):
            cuts=[0]+[split(canvas.any(0),int(w*k/6),w//12) for k in range(1,6)]+[w]
            for i,(l,r) in enumerate(zip(cuts,cuts[1:])):
                record(f"fig2{'ab'[num]}-{j*6+i+1:02}",np.uint8(canvas[:,l:r]),obj)
    # Clean the black reference foreground from one old plotted panel per example.
    for label,fn in [("fig1-apple","fig1-000.jpg"),("fig1-building","fig1-002.jpg"),
                     ("fig6-bat","ex-000.jpg"),("fig7-turtle","ex-023.jpg"),("fig8-horse","ex-041.jpg")]:
        obj=out/fn
        with Image.open(obj) as im:a=np.asarray(im.convert("RGB"))
        h,w=a.shape[:2]
        roi=a[round(.105*h):round(.876*h),round(.135*w):round(.898*w)]
        b=np.uint8(roi.max(axis=2)<110)
        b=cv2.morphologyEx(b,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(11,11)))
        _,lab,stats,_=cv2.connectedComponentsWithStats(b,8)
        b=np.uint8(lab==1+np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        record(label,b,obj)
    assert len(found)==29
    return found


def main():
    if file_hash(OX)!=OX_SHA or file_hash(LEMS)!=LEMS_SHA:raise ValueError("Old archive hash changed")
    records={}
    stages=defaultdict(set)
    def add(dataset,name,category,member,path,raw,role):
        mask=binary(raw,dataset)
        u=(dataset,name)
        if u in records:
            assert records[u]["raw_sha256"]==sha(raw)
            return
        records[u]=dict(dataset=dataset,id=name,category=category,member=member,file=path.relative_to(ROOT).as_posix(),
                        raw_sha256=sha(raw),pixel_sha256=pixels(mask),tight_d4_sha256=native_family(mask),
                        h=mask.shape[0],w=mask.shape[1],parent_asset_sha256=OX_SHA if dataset=="Oxford" else LEMS_SHA if dataset in ("LEMS","MPEG7") else "67c9a9f527142f8e2e5f4cec7a8a2724930059ecb876cc678095dbc3a868c1bc",
                        parent_image_sha256="",historical_role=role)
    for r in rows(ROOT/"records/samples.csv"):
        name=r["id"];path=ROOT/"data/trimaps"/(name+".png");raw=path.read_bytes()
        assert sha(raw)==r["sha256"];add("Oxford",name,r["breed"],r["member"],path,raw,"v1 scored")
        stages["Oxford",name].add("POLY01_"+r["partition"])
    for r in rows(ROOT/"records/poly02/samples.csv"):
        u=(r["dataset"],r["id"]);path=ROOT/r["file"];raw=path.read_bytes()
        assert sha(raw)==r["sha256"];add(*u,r["group"],r["member"],path,raw,"POLY02 scored")
        stages[u].add("POLY02_"+r["stage"])
        if r["curve"]=="1":stages[u].add("POLY02_rate_subset")
    for r in rows(ROOT/"records/poly03/known-pool.csv"):
        stages[r["dataset"],r["id"]].add("POLY03_input_screen")
    for r in rows(ROOT/"records/poly03/full-sources.csv"):
        stages[r["dataset"],r["id"]].add("POLY03_complete_mask")
    for fn,stage in [("full/per_image.csv","POLY03_main"),("repetition/per_image.csv","POLY03_repeat"),
                     ("feasibility/per_image.csv","POLY03_feasibility_table"),("phase/per_image.csv","POLY03_phase_table"),
                     ("time_fair/per_image.csv","POLY03_timing"),("detail/per_image.csv","POLY03_detail"),
                     ("single/all_outputs.csv","POLY03_single")]:
        for name in {r["id"] for r in rows(ROOT/"results/poly03"/fn)}:
            matching=[k for k in records if k[1]==name]
            if len(matching)!=1:raise ValueError((fn,name))
            stages[matching[0]].add(stage)
    for r in rows(ROOT/"results/poly03/single/mpeg/input_ranking.csv"):
        if r["selected"]=="1":stages["MPEG7",r["id"]].add("POLY03_single_MPEG")
    for r in rows(ROOT/"results/poly02/pso/trials.csv"):
        if r["id"]!="author_Fish-a100":stages["Oxford",r["id"]].add("POLY02_PSO")
    for name in ("apple-1","bat-1","camel-1"):
        m=f"MPEG_7_resize/{name}.gif";raw=subprocess.check_output(["tar","-xOf",str(LEMS),m])
        path=DATA/"known/MPEG_format"/(name+".gif");keep(path,raw)
        add("MPEG7",name,name.rsplit("-",1)[0],m,path,raw,"format-reserved, conservatively excluded")
        stages["MPEG7",name].add("POLY02_format_reserve_not_scored")
    for name,cat in [("Building170","Building"),("Fish-a100","Fish-a")]:
        fn=name+".gif";path=ROOT/"data/poly02/upf"/fn;raw=path.read_bytes()
        add("UPF",name,cat,fn,path,raw,"author software fixture")
        stages["UPF",name].add("POLY02_PSO_K4_and_reproduction" if cat=="Fish-a" else "POLY02_available_author_example_conservative")
        m="LEMS_ALL/"+fn;raw=subprocess.check_output(["tar","-xOf",str(LEMS),m])
        path=DATA/"known/LEMS_alias"/fn;keep(path,raw)
        add("LEMS",name,cat,m,path,raw,"same-name author dataset counterpart; full name prefix excluded")
        stages["LEMS",name].add("known_companion_alias")
    for r in paper_witnesses():
        records[r["dataset"],r["id"]]=r;stages[r["dataset"],r["id"]].add("POLY02_literature_visual_exposure")
    inventory=[]
    for u,r in sorted(records.items()):
        r["source_family_id"]=r["category"] if u[0] in ("UPF","LEMS") else r["id"]
        r["stages"]="|".join(sorted(stages[u]));inventory.append(r)
    c=Counter(r["dataset"] for r in inventory)
    assert c=={"Oxford":336,"MPEG7":73,"LEMS":2,"UPF":2,"PaperProbe":29},c
    write_csv(REC/"known.csv",inventory)
    with tarfile.open(OX,"r:gz") as t:
        ids=[m.name for m in t if m.isfile() and m.name.startswith("annotations/xmls/") and not "/._" in m.name and m.name.endswith(".xml")]
    meta=dict(sources=dict(c),unique_dataset_and_id=len(inventory),scored_known_oxford=336,scored_mpeg=70,
              physical_source_warning="UPF/LEMS same-name pairs and paper figures are not additional independent sources",
              archives={"Oxford annotations":dict(sha256=OX_SHA,bytes=OX.stat().st_size,xml_files=len(ids),scope="archive downloaded; only 336 native masks scored prior to POLY04"),
                        "Author shape RAR":dict(sha256=LEMS_SHA,bytes=LEMS.stat().st_size,scope="LEMS 1462 and MPEG 1400 numbered images plus two index graphics; wholesale download and name checks do not count as per-file evaluation"),
                        "Author ZIP":dict(bytes=(ROOT/"data/poly02/upf.zip").stat().st_size,scope="includes two visually available example GIFs; Fish actually ran")},
              original_split_note="No comprehensive individual/session ID in Oxford masks, official lists or XML; original paper reports same-animal manual screening.")
    keep(REC/"known-summary.json",(json.dumps(meta,ensure_ascii=False,indent=2)+"\n").encode())
    print(dict(c),len(inventory),"entries")


if __name__=="__main__":main()
