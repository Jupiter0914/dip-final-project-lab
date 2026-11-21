"""Run small closed-curve fixtures against the installed official CGAL package."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from .cgal_bridge import simplify
from src.codec import simple

ROOT=Path(__file__).resolve().parents[1]


def square(x,y,size):
    offsets=[(0,0),(size//2,0),(size,0),(size,size//2),(size,size),(size//2,size),(0,size),(0,size//2)]
    return np.array([(x+i,y+j) for i,j in offsets],np.int32)


def orient(a,b,c):
    return (int(b[0])-int(a[0]))*(int(c[1])-int(a[1]))-(int(b[1])-int(a[1]))*(int(c[0])-int(a[0]))


def intersects(a,b,c,d):
    if any(max(min(a[j],b[j]),min(c[j],d[j]))>min(max(a[j],b[j]),max(c[j],d[j])) for j in (0,1)):
        return False
    return orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0


def nesting(rings):
    for ring in rings:
        assert simple(ring)
    for i,r in enumerate(rings):
        for s in rings[i+1:]:
            assert not any(intersects(a,b,c,d)
                for a,b in zip(r,np.roll(r,-1,axis=0)) for c,d in zip(s,np.roll(s,-1,axis=0)))
    return [[int(cv2.pointPolygonTest(p,tuple(map(float,q[0])),False)) if i!=j else 0
            for j,q in enumerate(rings)] for i,p in enumerate(rings)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"local/poly03/cgal/fixture-replay.json")
    output=parser.parse_args().output
    cases={"outer_hole_island_separate":[square(0,0,96),square(12,12,72)[::-1],square(33,33,20),square(97,30,10)],
           "notch_near_other":[np.array([[0,0],[40,0],[40,4],[8,4],[8,28],[40,28],[40,32],[0,32]],np.int32),square(10,8,16)]}
    checks=[]
    for name,rings in cases.items():
        before=nesting(rings)
        total=sum(map(len,rings))
        for target in [total,total-3,4*len(rings),3*len(rings),3*len(rings)-1]:
            for cost in ("squared","scaled"):
                out,meta=simplify(rings,target,cost=cost)
                if target<3*len(rings):
                    assert not out and meta["status"]=="below_ring_count_bound"
                else:
                    assert len(out)==len(rings) and nesting(out)==before
                    for source,result in zip(rings,out):
                        assert all(tuple(x) in {tuple(p) for p in source} for x in result)
                    if target==total:
                        assert all(np.array_equal(a,b) for a,b in zip(rings,out))
                checks.append(dict(fixture=name,**meta))
    report={"native_calls":sum(r["status"]!="below_ring_count_bound" for r in checks),"checks":checks}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    for r in checks:
        print(r["fixture"],r["cost"],r["target_vertices"],r["output_vertices"],r["status"],round(r["elapsed_ms"],3))


if __name__=="__main__":
    main()
