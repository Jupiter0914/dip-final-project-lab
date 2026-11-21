"""Input-defined detail probes on the 36 previously used POLY02 development masks."""
import argparse
from collections import deque
from functools import lru_cache
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi
from poly02.core import exterior, disk, boundary, fit
from poly02.data import ROOT, REC, CFG, rows, save_rows, binary_from_bytes, sha
from src.codec import decode, encode

BASE=ROOT/"results/poly03/detail"
cv2.setNumThreads(1)
NEIGH=((-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1))


def edt(mask):
    return cv2.distanceTransform(np.pad(mask.astype(np.uint8),1),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]


def thinning(mask):
    weights=np.zeros((3,3),np.float32)
    for i,(dy,dx) in enumerate(NEIGH):
        weights[1+dy,1+dx]=1<<i
    codes=np.arange(256)
    p=np.stack([(codes>>i)&1 for i in range(8)])
    common=(p.sum(0)>=2)&(p.sum(0)<=6)&(((p==0)&(np.roll(p,-1,axis=0)==1)).sum(0)==1)
    luts=[common&((p[0]*p[2]*p[4])==0)&((p[2]*p[4]*p[6])==0),
          common&((p[0]*p[2]*p[6])==0)&((p[0]*p[4]*p[6])==0)]
    image=np.pad(mask.astype(np.uint8),1)
    while True:
        changed=False
        for lut in luts:
            index=cv2.filter2D(image,cv2.CV_16U,weights,borderType=cv2.BORDER_CONSTANT)
            remove=(image!=0)&lut[index]
            if remove.any():
                image[remove]=0
                changed=True
        if not changed: return image[1:-1,1:-1].astype(bool)


def skeleton_graph(skeleton):
    points={tuple(p) for p in np.argwhere(skeleton)}
    graph={}
    for y,x in points:
        adjacent=[]
        for dy,dx in NEIGH:
            v=(y+dy,x+dx)
            if v not in points: continue
            if dy and dx and ((y+dy,x) in points or (y,x+dx) in points): continue
            adjacent.append(v)
        graph[y,x]=adjacent
    return graph


def longest_run(flags):
    longest=current=0
    for yes in flags:
        current=current+1 if yes else 0
        longest=max(current,longest)
    return longest


def lost_diameter(graph,loss):
    """Geodesic endpoint distance in the lost reference graph, two sweeps per component."""
    remaining={tuple(p) for p in np.argwhere(loss)}
    largest=0
    def walk(seed,allowed):
        dist={seed:1}
        queue=deque([seed])
        while queue:
            u=queue.popleft()
            for v in graph[u]:
                if v in allowed and v not in dist:
                    dist[v]=dist[u]+1
                    queue.append(v)
        return dist
    while remaining:
        a=walk(min(remaining),remaining)
        terminal=max(a,key=a.get)
        b=walk(terminal,a)
        largest=max(largest,max(b.values()))
        remaining.difference_update(a)
    return largest


class DetailReference:
    def __init__(self,mask):
        self.mask=mask.astype(np.uint8)
        self.scale=math.sqrt(int(mask.sum()))
        self.skeleton=thinning(mask)
        self.graph=skeleton_graph(self.skeleton)
        self.dt=edt(mask)
        self.min_loss=max(3,math.ceil(.0125*self.scale))
        self.min_branch=max(4,math.ceil(.035*self.scale))
        self.radius=max(2.,.02*self.scale)
        self.branches=[]
        seen=set()
        for u in sorted(p for p,g in self.graph.items() if len(g)==1):
            prev=None
            chain=[]
            while self.dt[u]<=self.radius and u not in chain:
                if len(self.graph[u])>2: break
                chain.append(u)
                nxt=[v for v in self.graph[u] if v!=prev]
                if len(nxt)!=1: break
                prev,u=u,nxt[0]
            key=frozenset(chain)
            if len(chain)>=self.min_branch and key not in seen:
                self.branches.append(np.array(chain))
                seen.add(key)
        self.terminal=np.zeros_like(mask,bool)
        for chain in self.branches: self.terminal[tuple(chain.T)]=True
        self.close_r=max(4,round(.04*self.scale))
        pad=2*self.close_r+2
        closed=cv2.morphologyEx(np.pad(self.mask,pad),cv2.MORPH_CLOSE,disk(self.close_r))[pad:-pad,pad:-pad]
        self.pockets=[]
        labels,n=ndi.label((closed!=0)&(mask==0),structure=np.ones((3,3)))
        for i,box in enumerate(ndi.find_objects(labels),1):
            if box is None: continue
            yy,xx=np.where(labels[box]==i)
            if len(yy)>=max(8,self.close_r**2/3):
                self.pockets.append((yy+box[0].start,xx+box[1].start))
        self.neck_r=max(3,round(.035*self.scale))
        self.necks=self.find_necks()
        self.ref_edge=boundary(self.mask).astype(bool)
        y,x=np.where(self.ref_edge)
        h=y.max()-y.min()+1
        w=x.max()-x.min()+1
        ids=4*((y-y.min())*4//h)+(x-x.min())*4//w
        self.tiles=[(i,(y[ids==i],x[ids==i])) for i in range(16) if (ids==i).sum()>=max(8,math.ceil(.05*self.scale))]
        self.ref_double=np.repeat(np.repeat(self.mask,2,axis=0),2,axis=1)
        self.edge_double=boundary(self.ref_double).astype(bool)
        self.edt_ref=distance_to(self.ref_edge)
        self.edt_double=distance_to(self.edge_double)

    def find_necks(self):
        labs,_=ndi.label(self.dt>self.neck_r,structure=np.ones((3,3)))
        sizes=np.bincount(labs.ravel())
        eligible=np.flatnonzero(sizes>=max(16,self.neck_r**2))
        eligible=eligible[eligible!=0]
        if len(eligible)<2: return []
        cores=np.where(np.isin(labs,eligible),labs,0)
        nearest=ndi.distance_transform_edt(cores==0,return_distances=False,return_indices=True)
        zone=cores[tuple(nearest)]
        pairs=set()
        for dy,dx in ((0,1),(1,0),(1,1),(1,-1)):
            # Both pixels must lie inside the reference foreground.
            a=(slice(0,-dy or None),slice(0,-dx or None) if dx>=0 else slice(-dx,None))
            b=(slice(dy,None),slice(dx,None) if dx>=0 else slice(0,dx))
            different=(self.mask[a]!=0)&(self.mask[b]!=0)&(zone[a]!=zone[b])
            pairs.update(tuple(sorted(v)) for v in zip(zone[a][different],zone[b][different]))
        centers={}
        for i in eligible:
            centers[i]=np.unravel_index(np.argmax(np.where(cores==i,self.dt,-1)),self.dt.shape)
        result=[]
        for i,j in sorted(pairs):
            corridor=(self.mask!=0)&((zone==i)|(zone==j))
            pair=(centers[i],centers[j],corridor)
            start=self.clearance(self.mask,self.dt,pair)
            if start>=0: result.append(pair)
        return result

    def clearance(self,support,dt,neck):
        a,b,corridor=neck
        if not(support[a] and support[b]): return -2
        for level in range(self.neck_r,-1,-1):
            if dt[a]<=level or dt[b]<=level: continue
            _,lab=cv2.connectedComponents(np.uint8(corridor & (dt>level)),connectivity=8)
            if lab[a]!=0 and lab[a]==lab[b]: return level
        return -1

    def measurements(self,pred):
        edge=boundary(pred).astype(bool)
        dist=distance_to(edge)
        double=np.repeat(np.repeat(pred,2,axis=0),2,axis=1)
        de=boundary(double).astype(bool)
        dd=distance_to(de)
        support=self.mask & pred
        dt=edt(support)
        neck=[self.clearance(support,dt,pair) for pair in self.necks]
        return dict(xor=int(np.count_nonzero(self.mask!=pred)),
                    bf1=bf(self.edt_ref[edge],dist[self.ref_edge],1),bf2=bf(self.edt_ref[edge],dist[self.ref_edge],2),
                    bf3=bf(self.edt_ref[edge],dist[self.ref_edge],3),bf2_2x=bf(self.edt_double[de],dd[self.edge_double],2),
                    bf4_2x=bf(self.edt_double[de],dd[self.edge_double],4),
                    skel_hit=int(pred[self.skeleton].sum()),terminal_hit=int(pred[self.terminal].sum()),
                    notch_fp=sum(int(pred[p].sum()) for p in self.pockets)),neck,dist


def distance_to(edge):
    return cv2.distanceTransform(np.uint8(~edge),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)


def bf(pred_to_ref,ref_to_pred,radius):
    p=(pred_to_ref<=radius).mean()
    r=(ref_to_pred<=radius).mean()
    return float(2*p*r/(p+r)) if p+r else 0.


def compare(info,geometry,pred,g_values,g_necks,g_dist):
    values,necks,dist=info.measurements(pred)
    old=geometry.astype(bool)
    new=pred.astype(bool)
    lost=old & ~new
    gain=new & ~old
    parts=[]
    branch_loss=0
    branch_longest=0
    for j,points in enumerate(info.branches):
        loc=tuple(points.T)
        run=longest_run(lost[loc])
        branch_longest=max(branch_longest,run)
        branch_loss+=run>=info.min_loss
        parts.append(dict(kind="terminal",feature=j,size=len(points),old_hit=int(old[loc].sum()),new_hit=int(new[loc].sum()),
                          lost=int(lost[loc].sum()),gained=int(gain[loc].sum()),longest_run=run))
    notch_count=0
    notch_lost=notch_gained=0
    for j,loc in enumerate(info.pockets):
        bad,good=int(gain[loc].sum()),int(lost[loc].sum())
        notch_lost+=bad
        notch_gained+=good
        notch_count+=(bad-good)>=4
        parts.append(dict(kind="notch",feature=j,size=len(loc[0]),old_fp=int(old[loc].sum()),new_fp=int(new[loc].sum()),
                          lost=bad,gained=good))
    net_tile=0
    worst_tile=0.
    for j,loc in info.tiles:
        before=g_dist[loc]<=2
        after=dist[loc]<=2
        lost_tile=int((before&~after).sum())
        gain_tile=int((after&~before).sum())
        net_tile+=lost_tile-gain_tile>=3
        change=(gain_tile-lost_tile)/len(before)
        worst_tile=min(worst_tile,change)
        parts.append(dict(kind="tile",feature=j,size=len(before),old_hit=int(before.sum()),new_hit=int(after.sum()),
                          lost=lost_tile,gained=gain_tile))
    ngood=nthin=nbreak=nanchor=0
    for j,(b,a) in enumerate(zip(g_necks,necks)):
        if b>=0:
            ngood+=1
            nthin+=a>=0 and a<b
            nbreak+=a==-1
            nanchor+=a==-2
        parts.append(dict(kind="neck",feature=j,old_clearance=b,new_clearance=a,
                          anchor_a=",".join(map(str,info.necks[j][0])),anchor_b=",".join(map(str,info.necks[j][1]))))
    row=dict(**values,n_skeleton=int(info.skeleton.sum()),skeleton_lost=int(lost[info.skeleton].sum()),
             skeleton_gained=int(gain[info.skeleton].sum()),skeleton_lost_path=lost_diameter(info.graph,info.skeleton&lost),
             n_terminal=int(info.terminal.sum()),branch_count=len(info.branches),terminal_lost=int(lost[info.terminal].sum()),
             terminal_gained=int(gain[info.terminal].sum()),terminal_run=branch_longest,meaningful_loss_threshold=info.min_loss,
             branches_long_loss=branch_loss,notch_pixels=sum(len(p[0]) for p in info.pockets),notch_count=len(info.pockets),
             notch_lost=notch_lost,notch_gained=notch_gained,notches_net4=notch_count,
             neck_count=len(info.necks),geo_connected_necks=ngood,necks_thinner=nthin,necks_broken=nbreak,
             anchors_disappeared=nanchor,tile_drops=net_tile,worst_tile_recall_change=worst_tile)
    for key in ("xor","bf1","bf2","bf3","bf2_2x","bf4_2x","skel_hit","terminal_hit","notch_fp"):
        row["delta_"+key]=values[key]-g_values[key]
    return row,parts


def known_sources():
    data=[r for r in rows(REC/"samples.csv") if r["stage"]=="dev" and r["dataset"]=="Oxford"]
    assert len(data)==36 and len({r["id"] for r in data})==36
    return data


def read_mask(source):
    """Either the original POLY02 cache or the v1 Oxford downloader supplies identical bytes."""
    paths=[ROOT/source["file"],ROOT/"data/trimaps"/(source["id"]+".png")]
    for path in paths:
        if path.is_file():
            raw=path.read_bytes()
            if sha(raw)!=source["sha256"]: raise ValueError("Mask hash mismatch: "+source["id"])
            return binary_from_bytes(raw,"Oxford")
    raise FileNotFoundError("Run python -X utf8 scripts/prepare_data.py --check to retrieve "+source["id"])


@lru_cache(maxsize=1)
def prior_hashes():
    return {(r["id"],int(r["k"]),r["method"]):r["blob_sha256"] for r in rows(ROOT/"results/poly02/dev/per_image.csv")}


@lru_cache(maxsize=512)
def legacy_blob(name,k,method):
    """Regenerate missing cached original outputs only if they match the pre-existing SHA."""
    path=ROOT/"local/poly02/dev"/name/f"{k}-{method}.poly"
    if path.is_file():
        data=path.read_bytes()
    else:
        source=next(s for s in known_sources() if s["id"]==name)
        mask,curve=exterior(read_mask(source),k)
        vertices,_=fit(mask,curve,k,method,json.loads(CFG.read_text()))
        data=encode(mask.shape,vertices)
    if sha(data)!=prior_hashes()[name,k,method]: raise ValueError("Stored POLY02 hash differs")
    return data


def stored(name,k,method):
    return decode(legacy_blob(name,k,method))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=BASE)
    args=ap.parse_args()
    full=[]
    features=[]
    for i,source in enumerate(known_sources(),1):
        raw=read_mask(source)
        mask,_=exterior(raw,16)
        info=DetailReference(mask)
        for k in (16,32):
            geo=stored(source["id"],k,"geometry")
            gv,gn,gd=info.measurements(geo)
            for method in ("geometry","post_xor","post_guard"):
                pred=geo if method=="geometry" else stored(source["id"],k,method)
                row,parts=compare(info,geo,pred,gv,gn,gd)
                base=dict(id=source["id"],group=source["group"],k=k,method=method)
                full.append(dict(**base,**row))
                features.extend(dict(**base,**r) for r in parts)
        if i%12==0: print("known-source probes",i,flush=True)
    save_rows(args.out/"per_image.csv",full)
    save_rows(args.out/"features.csv",features)
    item=[r for r in full if r["method"]=="post_guard"]
    report={}
    for label,flag in dict(branches_eligible=lambda r:r["branch_count"]>0,
                          branch_long_loss=lambda r:r["branches_long_loss"]>0,
                          contiguous_skeleton_loss=lambda r:r["skeleton_lost_path"]>=r["meaningful_loss_threshold"],
                          notches_eligible=lambda r:r["notch_count"]>0,notches_net4=lambda r:r["notches_net4"]>0,
                          necks_eligible=lambda r:r["geo_connected_necks"]>0,necks_thinner=lambda r:r["necks_thinner"]>0,
                          necks_broken=lambda r:r["necks_broken"]>0,anchor_loss=lambda r:r["anchors_disappeared"]>0,
                          tile_loss=lambda r:r["tile_drops"]>0 and r["delta_bf2"]>=-1e-12,
                          scale_fixed_loss=lambda r:r["delta_bf2_2x"]< -1e-12,
                          scale_relative_loss=lambda r:r["delta_bf4_2x"]< -1e-12).items():
        subset=[r for r in item if flag(r)]
        report[label]=dict(sources=len({r["id"] for r in subset}),groups=len({r["group"] for r in subset}),
                           settings=len(subset),k16=sum(r["k"]==16 for r in subset),k32=sum(r["k"]==32 for r in subset))
    assert all(r["delta_bf2"]>=-1e-12 for r in item)
    (args.out/"diagnosis.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report),flush=True)


if __name__=="__main__": main()
