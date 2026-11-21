"""Full-mask quarter-grid ring codec. Raster parity is evaluated on the whole native canvas."""
from dataclasses import dataclass
import struct
import sys
from pathlib import Path
import contourpy
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
private=ROOT/"local/poly03/deps"
if private.is_dir():
    sys.path.insert(0,str(private))
from shapely.geometry import Polygon

HEADER=struct.Struct("<4sHHH")
RING=struct.Struct("<hH")


class Unsupported(ValueError):
    pass


class GeometryRejected(ValueError):
    """A known simple-ring or laminar-tree predicate rejected the input."""


def supported_shape(shape):
    return len(shape)==2 and all(0<d<=16382 for d in shape) and shape[0]*shape[1]<=4_000_000


def score_mask(raw,pred):
    if not np.any(raw) and not np.any(pred):
        return dict(xor=0,fp=0,fn=0,iou=1.,bf1=1.,bf2=1.,bf3=1.)
    from poly02.core import metrics
    return metrics(raw,pred)


def length(parent,vertices):
    return HEADER.size+RING.size*len(parent)+4*vertices


def polygons(rings):
    if any(len(p)<3 for p in rings):
        raise GeometryRejected("nonsimple_or_flat_ring")
    shapes=[Polygon(p) for p in rings]
    if any(len(p)<3 or not q.is_valid or q.area<=0 for p,q in zip(rings,shapes)):
        raise GeometryRejected("nonsimple_or_flat_ring")
    return shapes


def parents(shapes):
    result=[-1]*len(shapes)
    for i,p in enumerate(shapes):
        containers=[]
        for j,q in enumerate(shapes):
            if j==i or p.disjoint(q): continue
            if not p.boundary.disjoint(q.boundary): raise GeometryRejected("ring_boundaries_meet")
            if q.contains(p): containers.append(j)
            elif not p.contains(q): raise GeometryRejected("rings_cross")
        if containers: result[i]=min(containers,key=lambda j:shapes[j].area)
    return result


def vector_ok(rings,hierarchy):
    try: return ("ok" if parents(polygons(rings))==list(hierarchy) else "nesting_changed")
    except GeometryRejected as exc: return str(exc)


def extract(raw):
    if not supported_shape(raw.shape): raise Unsupported("outside_coordinate_or_implementation_canvas_limit")
    if np.any((raw!=0)&(raw!=1)): raise Unsupported("expected_binary_samples")
    curves=contourpy.contour_generator(z=np.pad(raw.astype(np.float64),1),name="serial",
            line_type="Separate",quad_as_tri=False,corner_mask=False).lines(.25)
    rings=[]
    for curve in curves:
        if not np.array_equal(curve[0],curve[-1]): raise Unsupported("open_isoline")
        grid=curve[:-1]*4
        p=np.rint(grid).astype(np.int32)
        if not np.array_equal(grid,p): raise Unsupported("nonlattice_boundary")
        u=p-np.roll(p,1,axis=0)
        v=np.roll(p,-1,axis=0)-p
        p=p[u[:,0]*v[:,1]!=u[:,1]*v[:,0]]
        if not 3<=len(p)<=65535: raise Unsupported("ring_count_field_or_degenerate_trace")
        rings.append(p)
    if len(rings)>32767: raise Unsupported("parent_field_overflow")
    try:
        rings.sort(key=lambda p:(-Polygon(p).area,*Polygon(p).bounds))
        hierarchy=parents(polygons(rings))
    except GeometryRejected as exc: raise Unsupported(str(exc)) from exc
    return rings,hierarchy


class Renderer:
    """Each call paints a complete padded 4x canvas; samples are pixel centers."""
    def __init__(self,shape):
        self.shape=shape
        h,w=shape
        self.hi=np.zeros((4*h+5,4*w+5),np.uint8) if supported_shape(shape) else None
        self.isolated_calls=0
        self.combined_calls=0

    def ring(self,points):
        h,w=self.shape
        if self.hi is None: raise Unsupported("outside_coordinate_or_implementation_canvas_limit")
        self.hi.fill(0)
        cv2.fillPoly(self.hi,[np.ascontiguousarray(points,np.int32)],1,lineType=cv2.LINE_8)
        self.isolated_calls+=1
        return self.hi[4:4*h+1:4,4:4*w+1:4].copy()

    def combined(self,rings):
        out=np.zeros(self.shape,np.uint8)
        for ring in rings: out^=self.ring(ring)
        self.combined_calls+=1
        return out


def pack(shape,rings,hierarchy):
    h,w=shape
    if not(supported_shape(shape) and len(rings)==len(hierarchy)<=32767): raise ValueError("header fields")
    payload=[HEADER.pack(b"PM31",w,h,len(rings))]
    for i,(p,parent) in enumerate(zip(rings,hierarchy)):
        p=np.asarray(p)
        if not (-1<=parent<i and p.ndim==2 and p.shape[1]==2 and 3<=len(p)<=65535 and np.issubdtype(p.dtype,np.integer)):
            raise ValueError("ring header or coordinates")
        if np.any(p<0) or np.any(p>[4*(w+1),4*(h+1)]): raise ValueError("out_of_canvas")
        payload.extend((RING.pack(parent,len(p)),p.astype("<u2").tobytes()))
    return b"".join(payload)


def unpack(blob):
    if len(blob)<HEADER.size: raise ValueError("short header")
    magic,w,h,n=HEADER.unpack_from(blob)
    if magic!=b"PM31" or not (supported_shape((h,w)) and n<=32767): raise ValueError("invalid header")
    offset=HEADER.size
    rings=[]
    hierarchy=[]
    for i in range(n):
        if offset+4>len(blob): raise ValueError("truncated ring")
        parent,k=RING.unpack_from(blob,offset)
        offset+=RING.size
        if not -1<=parent<i or k<3 or offset+4*k>len(blob): raise ValueError("invalid ring")
        p=np.frombuffer(blob,dtype="<u2",count=2*k,offset=offset).reshape(-1,2).astype(np.int32)
        if np.any(p>[4*(w+1),4*(h+1)]): raise ValueError("out_of_canvas")
        rings.append(p)
        hierarchy.append(parent)
        offset+=4*k
    if offset!=len(blob) or vector_ok(rings,hierarchy)!="ok": raise ValueError("invalid geometry or trailing bytes")
    return (h,w),rings,hierarchy


def decode(blob):
    shape,rings,hierarchy=unpack(blob)
    return Renderer(shape).combined(rings)


@dataclass
class Digital:
    fg:np.ndarray
    bg:np.ndarray
    nf:int
    nh:int
    adj:set


def digital(raw):
    mask=np.pad(np.ascontiguousarray(raw,np.uint8),1)
    nf,fg=cv2.connectedComponents(mask,connectivity=8)
    nb,bg=cv2.connectedComponents(1-mask,connectivity=4)
    # bg labels: 0 foreground, 1 padded exterior, 2 onward finite holes.
    assert bg[0,0]==1
    pairs=[]
    for f,b in [(fg[:-1],bg[1:]),(fg[1:],bg[:-1]),(fg[:,:-1],bg[:,1:]),(fg[:,1:],bg[:,:-1])]:
        valid=(f>0)&(b>0)
        pairs.append(f[valid].astype(np.int64)*nb+b[valid])
    ids=np.unique(np.concatenate(pairs))
    return Digital(fg,bg,nf-1,nb-2,{(int(x//nb),int(x%nb)) for x in ids})


def overlap_map(a,b,first,last):
    if last<first: return {}
    width=last+1
    counts=np.bincount((a*width+b).ravel(),minlength=width*width).reshape(width,width)
    block=counts[first:,first:]
    hit=block>0
    if not (np.all(hit.sum(axis=0)==1) and np.all(hit.sum(axis=1)==1)): return None
    mapping={}
    for label,j in enumerate(hit.argmax(axis=1)+first,first):
        if 2*counts[label,j]<min(counts[label,:].sum(),counts[:,j].sum()): return None
        mapping[label]=int(j)
    return mapping


def correspondence(ref,pred):
    if (ref.nf,ref.nh)!=(pred.nf,pred.nh): return "digital_counts"
    f=overlap_map(ref.fg,pred.fg,1,ref.nf)
    h=overlap_map(ref.bg,pred.bg,2,ref.nh+1)
    if f is None or h is None: return "digital_overlap"
    h[1]=1
    if {(f[i],h[j]) for i,j in ref.adj}!=pred.adj: return "digital_adjacency"
    return "ok"
