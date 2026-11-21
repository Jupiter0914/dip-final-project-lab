"""Select a fixed input cohort only after publication of the sampling preregistration."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageOps
from poly03.full_data import descriptor
from .data import ROOT,DATA,REC,OX,LEMS,RGB,OX_SHA,LEMS_SHA,file_hash,rows,sha,pixels,binary,keep
from .data_known import write_csv
from .data_families import Families,shape,exact_links,mask_links,photo_links

cv2.setNumThreads(1)
SETTINGS=ROOT/"configs/poly04/sampling.json"
LOCK_FILES=["configs/poly04/sampling.json","records/poly04/data-protocol.md","records/poly04/known.csv","records/poly04/known-views.csv","records/poly04/known-summary.json",
            "poly04/data.py","poly04/data_known.py","poly04/data_views.py","poly04/data_families.py","poly04/data_select.py","poly03/full_data.py"]
RGB_SHA="67195c5e1c01f1ab5f9b6a5d22b8c27a580d896ece458917e61d459337fa318d"


def rank(s):return sha(s.encode("utf-8"))


def check_lock():
    commit=subprocess.check_output(["git","rev-parse","poly04-sampling-v1^{commit}"],cwd=ROOT).decode().strip()
    for name in LOCK_FILES:
        raw=subprocess.check_output(["git","show",f"{commit}:{name}"],cwd=ROOT)
        if raw.replace(b"\r\n",b"\n")!=(ROOT/name).read_bytes().replace(b"\r\n",b"\n"):
            raise ValueError("Published sampling implementation or rule changed: "+name)
    return commit


def make_node(dataset,name,category,member,raw,known,excluded,source_file="",info=None):
    mask=binary(raw,dataset)
    desc=descriptor(mask)
    row=dict(dataset=dataset,id=name,category=category,group=category,member=member,raw_sha256=sha(raw),
             pixel_sha256=pixels(mask),file=source_file,w=mask.shape[1],h=mask.shape[0],
             components=desc["components"],holes=desc["holes"],rings=desc["components"]+desc["holes"],
             near=desc["near"],stratum=desc["stratum"],preexisting=int(known),family_excluded=int(excluded),
             rgb_sha256="",exif_unique_id="")
    ft=shape(mask)
    row["tight_d4_sha256"]=ft.canonical
    if info:
        assert all(row[k]==info[k] for k in ("raw_sha256","pixel_sha256","tight_d4_sha256"))
    return row,ft


def select():
    commit=check_lock()
    settings=json.loads(SETTINGS.read_text(encoding="utf-8"))
    if file_hash(OX)!=OX_SHA or file_hash(LEMS)!=LEMS_SHA or file_hash(RGB)!=RGB_SHA:
        raise ValueError("Checked original archives required")
    nodes=[];features=[];compressed={};keys={}
    def add(*args,**kwargs):
        row,f=make_node(*args,**kwargs)
        key=(row["dataset"],row["id"])
        if key in keys:
            old=nodes[keys[key]]
            assert old["raw_sha256"]==row["raw_sha256"] and old["pixel_sha256"]==row["pixel_sha256"]
            return keys[key]
        i=len(nodes);keys[key]=i;nodes.append(row);features.append(f)
        return i
    known=rows(REC/"known.csv")
    aliases=rows(REC/"known-views.csv")
    for r in known+aliases:
        raw=(ROOT/r["file"]).read_bytes()
        add(r["dataset"],r["id"],r["category"],r["member"],raw,True,False,r["file"],r)
    with tarfile.open(OX) as t:
        official={r.split()[0] for r in t.extractfile("annotations/test.txt").read().decode().splitlines()}
    seen=set()
    with tarfile.open(OX,"r|gz") as t:
        for entry in t:
            if not(entry.isfile() and entry.name.startswith("annotations/trimaps/") and entry.name.endswith(".png")):continue
            name=Path(entry.name).stem
            if name not in official:continue
            seen.add(name)
            if ("Oxford",name) in keys:continue
            raw=t.extractfile(entry).read()
            i=add("Oxford",name,name.rsplit("_",1)[0],entry.name,raw,False,False)
            compressed[i]=raw
    assert seen==official
    print("Oxford metadata/annotations indexed",len(seen),flush=True)
    members=subprocess.check_output(["tar","-tf",str(LEMS)]).decode().splitlines()
    lems=[m for m in members if m.startswith("LEMS_ALL/") and m.lower().endswith(".gif")]
    if not all(re.fullmatch(r"LEMS_ALL/[A-Za-z-]+\d+\.gif",m) for m in lems) or len(lems)!=1462:
        raise ValueError("Unexpected author corpus layout")
    folder=DATA/"input-dedup"
    folder.mkdir(parents=True,exist_ok=True)
    subprocess.run(["tar","-xf",str(LEMS),"-C",str(folder),"LEMS_ALL"],check=True)
    denied=set(settings["external"]["excluded_prefixes"])
    categories=set(settings["external"]["eligible_prefixes"])|denied
    for member in sorted(lems):
        name=Path(member).stem;category=re.match(r"[^0-9]+",name).group()
        if category not in categories:raise ValueError(category)
        raw=(folder/member).read_bytes()
        i=add("LEMS",name,category,member,raw,False,category in denied)
        if category in denied:nodes[i]["family_excluded"]=1
        else:compressed[i]=raw
    print("LEMS directory and known whole-prefix exclusions indexed",len(lems),flush=True)
    photos={};missing=[]
    with tarfile.open(RGB,"r|gz") as t:
        for entry in t:
            if not(entry.isfile() and entry.name.startswith("images/") and entry.name.lower().endswith(".jpg")):continue
            name=Path(entry.name).stem
            i=keys.get(("Oxford",name))
            if i is None:continue
            raw=t.extractfile(entry).read()
            if i in photos:raise ValueError("Duplicate RGB member: "+name)
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    uid=str(im.getexif().get(42016,"")).strip().lower()
                    thumb=ImageOps.exif_transpose(im).convert("RGB").resize((32,32),Image.Resampling.LANCZOS)
                    photos[i]=np.array(thumb)
            except (ValueError,OSError) as exc:
                missing.append(dict(id=name,reason="RGB decode failed",detail=str(exc)))
                continue
            nodes[i]["rgb_sha256"]=sha(raw)
            if re.fullmatch(r"[0-9a-f-]{16,64}",uid) and len(set(uid.replace("-","")))>3:
                nodes[i]["exif_unique_id"]=uid
    for i,r in enumerate(nodes):
        if r["dataset"]=="Oxford" and i not in photos:
            # Failure of the leakage-screening asset is recorded before any encoding.
            r["family_excluded"]=1
            if not any(v["id"]==r["id"] for v in missing):missing.append(dict(id=r["id"],reason="RGB member missing",detail=""))
    graph=Families(len(nodes))
    exact_links(nodes,features,graph)
    for r in aliases:
        graph.add(keys[r["dataset"],r["id"]],keys[r["parent_dataset"],r["parent_id"]],"documented_source_transform")
    mask_links(nodes,features,graph)
    print("Full mask family graph built",len(graph.edges),flush=True)
    photo_links(sorted(photos),photos,graph)
    comp=defaultdict(list)
    for i in range(len(nodes)):comp[graph.root(i)].append(i)
    family={}; blocked={};representatives=[]
    for indices in comp.values():
        labels=sorted(nodes[i]["dataset"]+"/"+nodes[i]["id"] for i in indices)
        fid="F"+rank("\n".join(labels))[:20]
        exclusion=any(nodes[i]["preexisting"] or nodes[i]["family_excluded"] for i in indices)
        for i in indices:
            nodes[i]["family"]=fid
            nodes[i]["family_size"]=len(indices)
            nodes[i]["screen_excluded"]=int(exclusion)
            family[i]=fid;blocked[i]=exclusion
        if not exclusion:
            representatives.append(min(indices,key=lambda i:rank(settings["salt"]+"|"+nodes[i]["dataset"]+"|"+nodes[i]["id"])))
    def ranked(indices):
        return sorted(indices,key=lambda i:rank(settings["salt"]+"|"+nodes[i]["dataset"]+"|"+nodes[i]["id"]))
    ox=[i for i in representatives if nodes[i]["dataset"]=="Oxford"]
    le=[i for i in representatives if nodes[i]["dataset"]=="LEMS"]
    strata=settings["oxford"]["strata"]
    by_stratum={s:ranked([i for i in ox if nodes[i]["stratum"]==s]) for s in strata}
    selected_ox=[];left={}
    for s,n in zip(strata,settings["oxford"]["quota"]):
        selected_ox.extend(by_stratum[s][:n]);left[s]=by_stratum[s][n:]
    def fill(items,bins,order,n):
        while len(items)<n:
            prior=len(items)
            for group in order:
                if bins[group] and len(items)<n:items.append(bins[group].pop(0))
            if len(items)==prior:break
    fill(selected_ox,left,["near","holes","components","simple"],settings["oxford"]["n"])
    cats=settings["external"]["eligible_prefixes"]
    by_cat={cat:ranked([i for i in le if nodes[i]["category"]==cat]) for cat in cats}
    selected_le=[]
    remaining={k:list(v) for k,v in by_cat.items()}
    serial_excluded=set()
    selected_numbers=defaultdict(list)
    # A spacing precaution supplements the explicit family graph without claiming
    # that every adjacent serial number necessarily describes the same object.
    for r in nodes:
        if r["dataset"]=="LEMS" and r["category"] in cats and blocked[keys["LEMS",r["id"]]]:
            selected_numbers[r["category"]].append(int(re.search(r"\d+$",r["id"])[0]))
    while len(selected_le)<settings["external"]["n"]:
        start_count=len(selected_le)
        for cat in cats:
            if len(selected_le)>=settings["external"]["n"]:break
            while remaining[cat]:
                i=remaining[cat].pop(0)
                number=int(re.search(r"\d+$",nodes[i]["id"])[0])
                if any(abs(number-prev)<3 for prev in selected_numbers[cat]):
                    serial_excluded.add(i);continue
                selected_le.append(i);selected_numbers[cat].append(number)
                break
        if len(selected_le)==start_count:break
    selected=selected_ox+selected_le
    if len(selected)!=len(set(family[i] for i in selected)):raise AssertionError("Multiple picked in one source family")
    sub=set()
    for domain in (selected_ox,selected_le):
        order=lambda i:rank("POLY04-secondary|"+nodes[i]["dataset"]+"|"+nodes[i]["id"])
        bins={s:sorted([i for i in domain if nodes[i]["stratum"]==s],key=order) for s in strata}
        few=[];fill(few,bins,strata,settings["supplements"]["small_budget_sources_per_dataset"])
        sub.update(few)
    samples=[]
    for i in selected:
        r=nodes[i]
        dest=DATA/"sources"/r["dataset"]/(r["id"]+Path(r["member"]).suffix)
        keep(dest,compressed[i])
        r["file"]=dest.relative_to(ROOT).as_posix()
        r["supplement"]=int(i in sub)
        samples.append({k:r[k] for k in ("dataset","id","category","group","family","family_size","stratum","components","holes","near","rings","w","h","member","file","raw_sha256","pixel_sha256","tight_d4_sha256","rgb_sha256","supplement")})
    write_csv(REC/"samples.csv",samples)
    chosen=set(selected);reps=set(representatives)
    screening=[]
    for i,r in enumerate(nodes):
        role="selected" if i in chosen else "known_source" if r["preexisting"] else "excluded_prefix_or_missing_rgb" if r["family_excluded"] else "touches_excluded_family" if blocked[i] else "same_family_other" if i not in reps else "serial_spacing" if i in serial_excluded else "not_selected_by_quota"
        screening.append(dict(dataset=r["dataset"],id=r["id"],category=r["category"],family=family[i],family_size=r["family_size"],disposition=role,stratum=r["stratum"],
                              raw_sha256=r["raw_sha256"],pixel_sha256=r["pixel_sha256"],rgb_sha256=r["rgb_sha256"]))
    write_csv(REC/"data-screening.csv",screening)
    edges=[dict(a=nodes[i]["dataset"]+"/"+nodes[i]["id"],b=nodes[j]["dataset"]+"/"+nodes[j]["id"],reason=reason,score=f"{score:.8f}")
           for (i,j,reason),score in sorted(graph.edges.items())]
    write_csv(REC/"data-links.csv",edges)
    summary=dict(rule_commit=commit,rule_sha256=file_hash(SETTINGS),manifest_sha256=file_hash(REC/"samples.csv"),
        archives=dict(oxford_annotations=OX_SHA,oxford_rgb=RGB_SHA,author_shapes=LEMS_SHA),n_oxford=len(selected_ox),n_lems=len(selected_le),n_total=len(selected),
        official_oxford_test=len(official),native_oxford_rgb_usable=len(photos),missing_rgb=missing,
        known_exclusion_rows=len(known),explicit_derived_known_views=len(aliases),native_inputs_indexed=len(nodes),known_or_denied_linked_components=len({family[i] for i in range(len(nodes)) if blocked[i]}),
        graph_edges_by_reason=dict(Counter(k[2] for k in graph.edges)),clusters=len(comp),
        available_oxford_by_stratum={s:len(v) for s,v in by_stratum.items()},available_lems_by_category={cat:len(v) for cat,v in by_cat.items()},
        manifest_strata={d:dict(Counter(r["stratum"] for r in samples if r["dataset"]==d)) for d in ("Oxford","LEMS")},
        manifest_groups={d:dict(Counter(r["category"] for r in samples if r["dataset"]==d)) for d in ("Oxford","LEMS")},
        held_out_family_disjoint=True,per_family_limit=1,supplementary_n=len(sub),
        known_paper_components={r["id"]:[nodes[j]["dataset"]+"/"+nodes[j]["id"] for j in comp[graph.root(i)] if j!=i] for i,r in enumerate(nodes) if r["dataset"]=="PaperProbe"})
    keep(REC/"data-selection.json",(json.dumps(summary,ensure_ascii=False,indent=2)+"\n").encode())
    print("Frozen inputs",len(selected_ox),len(selected_le),summary["manifest_strata"],"source digest",summary["manifest_sha256"])


if __name__=="__main__":
    select()
