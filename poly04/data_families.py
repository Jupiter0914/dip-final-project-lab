"""Conservative, input-only family graph for mask and full-photo near-duplicates."""
from dataclasses import dataclass
import math
import re
import cv2
import numpy as np
from scipy.spatial import cKDTree
from .data_known import d4,trimmed,native_family
from .data import pixels

BITCOUNT=np.unpackbits(np.arange(256,dtype=np.uint8)[:,None],axis=1).sum(axis=1).astype(np.uint8)


@dataclass
class Shape:
    bits:np.ndarray
    aspect:float
    canonical:str


def shape(mask):
    cropped=trimmed(mask)
    h,w=cropped.shape
    occupancy=cv2.resize(cropped.astype(np.float32),(64,64),interpolation=cv2.INTER_AREA)
    return Shape(np.uint8(occupancy>=.5),w/h,native_family(mask))


def coarse(bits):
    return bits.reshape(8,8,8,8).sum(axis=(1,3),dtype=np.int32).ravel()


def dct_hash(gray):
    block=cv2.dct(gray.astype(np.float32))[:8,:8].ravel()[1:]
    bits=np.r_[False,block>=np.median(block)]
    return np.packbits(bits,bitorder="big").view(">u8")[0]


class Families:
    def __init__(self,n):
        self.parent=np.arange(n)
        self.edges={}

    def root(self,i):
        while self.parent[i]!=i:
            self.parent[i]=self.parent[self.parent[i]]
            i=int(self.parent[i])
        return int(i)

    def add(self,i,j,reason,score=1.0):
        i,j=map(int,(i,j))
        if i==j:return
        pair=tuple(sorted((i,j)))
        key=(*pair,reason)
        self.edges[key]=max(float(score),self.edges.get(key,-1.0))
        a,b=self.root(i),self.root(j)
        if a!=b:self.parent[max(a,b)]=min(a,b)


def exact_links(nodes,features,graph):
    for field in ("raw_sha256","pixel_sha256","tight_d4_sha256","rgb_sha256","exif_unique_id"):
        seen={}
        for i,row in enumerate(nodes):
            val=row.get(field)
            if not val:continue
            if val in seen:graph.add(i,seen[val],field)
            else:seen[val]=i


def mask_links(nodes,features,graph):
    base=np.stack([f.bits for f in features])
    packed=np.packbits(base.reshape(len(base),-1),axis=1)
    areas=base.sum(axis=(1,2)).astype(int)
    aspects=np.log([f.aspect for f in features])
    tree=cKDTree(np.stack([coarse(b) for b in base]))
    lookup={(r["dataset"],r["id"]):i for i,r in enumerate(nodes)}
    for i,(r,f) in enumerate(zip(nodes,features)):
        probe=r["dataset"]=="PaperProbe"
        threshold=.85 if probe else .92
        family_threshold=1.40 if probe else 1.18
        adj=[]
        if r["dataset"]=="LEMS":
            cat=r["category"]
            num=re.fullmatch(re.escape(cat)+r"(\d+)",r["id"])
            if num:
                nn=num[1]
                for off in (-1,1):
                    j=lookup.get(("LEMS",cat+str(int(nn)+off).zfill(len(nn))))
                    if j is not None and j<i:adj.append(j)
        for ori,(b,log_aspect) in enumerate(zip(d4(f.bits),[aspects[i]]*2+[-aspects[i]]*2+[aspects[i]]*2+[-aspects[i]]*2)):
            # Differences of block populations lower-bound full XOR. Every candidate
            # satisfying the target IoU is within (1-IoU)*4096 in this safe prefilter.
            near=np.asarray(tree.query_ball_point(coarse(b),r=math.ceil((1-threshold)*4096),p=1),dtype=int)
            if probe:near=near[near!=i]
            else:near=near[near<i]
            near=near[np.abs(aspects[near]-log_aspect)<=math.log(family_threshold)]
            bits=np.packbits(b.ravel())
            if len(near):
                inter=BITCOUNT[np.bitwise_and(packed[near],bits)].sum(axis=1)
                union=areas[near]+areas[i]-inter
                similarity=np.divide(inter,union,out=np.ones(len(near),float),where=union!=0)
                for j,s in zip(near[similarity>=threshold],similarity[similarity>=threshold]):
                    graph.add(i,j,"publication_mask" if probe else "normalized_mask",s)
            for j in adj:
                if abs(aspects[j]-log_aspect)>math.log(1.25):continue
                hit=int(BITCOUNT[np.bitwise_and(bits,packed[j])].sum())
                similarity=hit/max(1,int(areas[i])+int(areas[j])-hit)
                if similarity>=.80:graph.add(i,j,"adjacent_LEMS_series",similarity)


def photo_links(indices,photos,graph):
    """Full photographs, sampled using the same EXIF-corrected 32x32 RGB grid."""
    if not indices:return
    arrays=np.stack([photos[i] for i in indices])
    grays=np.array([cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) for a in arrays])
    hashes=np.array([dct_hash(a) for a in grays],dtype=np.uint64)
    for k,(i,img) in enumerate(zip(indices,arrays)):
        if k==0:continue
        for oriented in d4(img):
            g=cv2.cvtColor(oriented,cv2.COLOR_RGB2GRAY)
            distant=np.bitwise_count(hashes[:k]^np.uint64(dct_hash(g)))
            for pos in np.flatnonzero(distant<=10):
                a=g.ravel().astype(float);b=grays[pos].ravel().astype(float)
                a-=a.mean();b-=b.mean()
                norm=np.linalg.norm(a)*np.linalg.norm(b)
                corr=float((a@b)/norm) if norm else 0
                if corr<.94:continue
                delta=oriented.astype(float)-arrays[pos].astype(float)
                delta-=delta.mean(axis=(0,1),keepdims=True)
                if float(np.sqrt(np.mean(delta**2)))<=22:
                    graph.add(i,indices[pos],"photo_phash_corr",corr)


def fixtures():
    x=np.zeros((28,38),np.uint8);x[3:20,6:9]=1;x[16:20,6:30]=1;x[6:9,7:20]=1
    z=np.zeros((35,33),np.uint8);z[2:30,2:28]=1;z[9:20,9:22]=0
    a=cv2.resize(x,(76,56),interpolation=cv2.INTER_NEAREST)[:,::-1]
    b=np.pad(np.rot90(x),((12,4),(3,8)))
    frames=[x,np.ascontiguousarray(a),b,z]
    fs=[shape(m) for m in frames]
    nodes=[dict(dataset="fixture",id=str(i),category="synthetic",tight_d4_sha256=f.canonical,pixel_sha256=pixels(m)) for i,(m,f) in enumerate(zip(frames,fs))]
    g=Families(len(nodes));exact_links(nodes,fs,g);mask_links(nodes,fs,g)
    assert g.root(0)==g.root(1)==g.root(2) and g.root(0)!=g.root(3)
    rng=np.random.default_rng(27)
    view=np.uint8(rng.integers(0,210,(32,32,3)))
    g=Families(3)
    photo_links([0,1,2],{0:view,1:np.rot90(view[:,::-1])+8,2:rng.integers(0,230,(32,32,3),dtype=np.uint8)},g)
    assert g.root(0)==g.root(1) and g.root(0)!=g.root(2)
    print("Translation, scale, reflection, right-angle rotation and brightness witnesses matched; distinct controls retained.")


if __name__=="__main__":fixtures()
