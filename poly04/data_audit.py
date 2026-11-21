"""Verify selected raw masks, graph components and the quota/serial sampling from public tables."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import re
import subprocess
from pathlib import Path
import cv2
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from .data import ROOT,REC,DATA,read_binary,rows,sha,pixels,binary,file_hash
from .data_known import native_family
from poly03.full_data import descriptor

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--record",action="store_true",help="Save the result of the fresh verification")
    opts=parser.parse_args()
    cfg=json.loads((ROOT/"configs/poly04/sampling.json").read_text(encoding="utf-8"))
    complete=json.loads((REC/"data-selection.json").read_text(encoding="utf-8"))
    old=rows(REC/"known.csv");views=rows(REC/"known-views.csv")
    old_keys={r["dataset"]+"/"+r["id"] for r in old+views}
    assert len({r["id"] for r in old if r["dataset"]=="Oxford"})==336
    assert len(views)==443 and all(r["parent_dataset"]+"/"+r["parent_id"] in old_keys for r in views)
    allrows=rows(REC/"data-screening.csv");picked=rows(REC/"samples.csv")
    keys=[r["dataset"]+"/"+r["id"] for r in allrows]
    positions={key:i for i,key in enumerate(keys)}
    assert len(positions)==len(keys) and old_keys.issubset(positions)
    links=rows(REC/"data-links.csv");x=[];y=[]
    for r in links:
        x.append(positions[r["a"]]);y.append(positions[r["b"]])
    # Sparse undirected connectivity is independent of the selection-time union-find.
    mat=csr_matrix((np.ones(len(x),dtype=bool),(x,y)),shape=(len(keys),len(keys)))
    nc,classes=connected_components(mat,directed=False)
    by=defaultdict(list)
    for i,cls in enumerate(classes):by[int(cls)].append(i)
    blocked=set();eligible=[]
    missing={r["id"] for r in complete["missing_rgb"]}
    salt=cfg["salt"]
    def order(i):
        r=allrows[i];return sha(f"{salt}|{r['dataset']}|{r['id']}".encode())
    for members in by.values():
        fid="F"+sha("\n".join(sorted(keys[i] for i in members)).encode())[:20]
        for i in members:
            assert allrows[i]["family"]==fid and int(allrows[i]["family_size"])==len(members)
        excluded=any(keys[i] in old_keys or (allrows[i]["dataset"]=="LEMS" and allrows[i]["category"] in cfg["external"]["excluded_prefixes"]) or
                     (allrows[i]["dataset"]=="Oxford" and allrows[i]["id"] in missing) for i in members)
        if excluded: blocked.update(members)
        else: eligible.append(min(members,key=order))
    strata=cfg["oxford"]["strata"]
    obins={s:iter(sorted((i for i in eligible if allrows[i]["dataset"]=="Oxford" and allrows[i]["stratum"]==s),key=order)) for s in strata}
    ox=[]
    for s,num in zip(strata,cfg["oxford"]["quota"]):
        for _ in range(num):
            i=next(obins[s],None)
            if i is None:break
            ox.append(i)
    while len(ox)<cfg["oxford"]["n"]:
        n=len(ox)
        for s in ["near","holes","components","simple"]:
            i=next(obins[s],None)
            if i is not None and len(ox)<cfg["oxford"]["n"]:ox.append(i)
        if n==len(ox):break
    ecats=cfg["external"]["eligible_prefixes"]
    ebins={c:iter(sorted((i for i in eligible if allrows[i]["dataset"]=="LEMS" and allrows[i]["category"]==c),key=order)) for c in ecats}
    occupied=defaultdict(set)
    def num(i):return int(re.search(r"\d+$",allrows[i]["id"])[0])
    for i in blocked:
        r=allrows[i]
        if r["dataset"]=="LEMS" and r["category"] in ecats:occupied[r["category"]].update(range(num(i)-2,num(i)+3))
    le=[]
    while len(le)<cfg["external"]["n"]:
        n=len(le)
        for c in ecats:
            if len(le)==cfg["external"]["n"]:break
            for i in ebins[c]:
                j=num(i)
                if j in occupied[c]:continue
                le.append(i);occupied[c].update(range(j-2,j+3));break
        if n==len(le):break
    expected=[keys[i] for i in ox+le]
    assert expected==[r["dataset"]+"/"+r["id"] for r in picked]
    assert len(picked)==len({r["family"] for r in picked})
    assert not old_keys.intersection(expected)
    known_px={r["pixel_sha256"] for r in old+views}
    known_raw={r["raw_sha256"] for r in old+views}
    for r in picked:
        a=read_binary(r)
        assert a.shape==(int(r["h"]),int(r["w"])) and r["tight_d4_sha256"]==native_family(a)
        assert pixels(a) not in known_px and r["raw_sha256"] not in known_raw
        desc=descriptor(a)
        assert desc["stratum"]==r["stratum"] and desc["components"]+desc["holes"]==int(r["rings"])
    result=dict(passed=True,materialized_native_inputs=len(picked),old_raw_exclusions=len(old),
                known_source_views=len(views),graph_components_rebuilt=int(nc),matching_links=len(links),
                fully_reselected_from_family_graph=True,known_intersections=0,selected_duplicate_families=0,
                oxford=len(ox),lems=len(le),selected_strata={d:dict(Counter(r["stratum"] for r in picked if r["dataset"]==d)) for d in ("Oxford","LEMS")},
                r_multiple={d:sum(r["dataset"]==d and int(r["rings"])>=2 for r in picked) for d in ("Oxford","LEMS")},
                manifest_sha256=file_hash(REC/"samples.csv"),selection_commit=complete["rule_commit"])
    if opts.record:(REC/"data-audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__": main()
