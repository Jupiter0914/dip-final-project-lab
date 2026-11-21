"""Cost anatomy and full donor/edge diagnostic on a real low-deletion-cost stall."""
from fractions import Fraction
from time import perf_counter
import json
import numpy as np
from poly02.core import exterior,BoundaryScore,RasterLoss
from poly02.data import CFG,save_rows,read_mask,rows,sha
from poly02.verify import IndependentScore,reference
from src.codec import encode,decode,paint,simple
from .atomic import replace_vertex
from .single import OUT,LOCAL,source_set
from .single_search import Work,State,segment_distance,DIRECTIONS,RADII
from .single_support import expanded


def read_poly(file):
    blob=(LOCAL/file).read_bytes()
    return np.frombuffer(blob,offset=10,dtype="<u2").reshape(-1,2).astype(np.int32)


def cost_row(mask,contour,row):
    p=read_poly(row["stationary_file"])
    current=int(row["stationary_xor"])
    work=Work(mask,BoundaryScore(mask,2),Fraction(0),float("inf"))
    donors,targets,dc=expanded(mask,contour,State(p,current),work)
    insert=[work.score(np.insert(p,j+1,xy,axis=0))-current for j,xy in targets]
    best=None
    count=0
    for i in donors:
        for j,xy in targets:
            if i in (j,(j+1)%len(p)): continue
            candidate=replace_vertex([p],0,int(i),0,j,xy)[0]
            xor=work.score(candidate)
            count+=1
            if best is None or xor<best: best=xor
    return dict(id=row["id"],k=row["k"],start_xor=current,min_delete_cost=dc,best_insert_saving=-min(insert) if insert else "",
                min_joint_delta=best-current if best is not None else "",coupled_pairs=count,
                recipient_edges=len(set(j for j,_ in targets)),distinct_insert_proposals=len(targets))


def independent_scan(mask,p,floor):
    scorer=IndependentScore(mask)
    initial=np.count_nonzero(paint(mask.shape,p)!=mask)
    records=[]
    for j in range(len(p)):
        for radius in RADII:
            for dx,dy in DIRECTIONS:
                point=p[j]+radius*np.array([dx,dy])
                r=dict(vertex=j,radius=radius,dx=int(dx),dy=int(dy),x=int(point[0]),y=int(point[1]))
                if np.any(point<0) or np.any(point>=[mask.shape[1],mask.shape[0]]):
                    r.update(status="outside")
                else:
                    trial=p.copy(); trial[j]=point
                    pred=paint(mask.shape,trial)
                    xor=int(np.count_nonzero(mask!=pred))
                    legal=simple(trial)
                    r.update(xor=xor,valid=bool(legal))
                    if not legal: r["status"]="non_simple"
                    elif xor>=initial: r["status"]="no_strict_xor"
                    else:
                        vals=scorer.measure(pred)
                        r["bf2"]=vals["bf2"]
                        r["status"]="eligible" if vals["bf2"]>=float(floor)-1e-12 else "below_floor"
                records.append(r)
    if any(r["status"]=="eligible" for r in records): raise AssertionError("Incomplete plateau")
    return records


def candidate_grid(mask,contour,p,e):
    a=p[e]
    v=p[(e+1)%len(p)]-a
    n=np.array([-v[1],v[0]],float)/np.linalg.norm(v)
    t,_=segment_distance(contour.astype(float),a.astype(float),a+v)
    projection=a+t[:,None]*v
    shifted=np.array([a+u*v+s*n for u in np.arange(1,8)/8. for s in
                      (-32,-24,-16,-12,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6,7,8,12,16,24,32)])
    q=np.unique(np.rint(np.vstack([contour,.5*(projection+contour),shifted])).astype(np.int32),axis=0)
    inside=np.all((q>=0)&(q<[mask.shape[1],mask.shape[0]]),axis=1)
    return q[inside]


def strong(mask,contour,row,output):
    p=read_poly(row["stationary_file"])
    old=int(row["stationary_xor"])
    bf=BoundaryScore(mask,2)
    src_poly=read_poly_baseline(row["id"],len(p))
    floor=bf.exact(paint(mask.shape,src_poly))
    loss=RasterLoss(mask)
    scan=independent_scan(mask,p,floor)
    save_rows(output/"single_move_certificate.csv",scan)
    best_raw=None
    best_desc=None
    best_admissible=old
    best_admissible_desc=None
    k=len(p)
    totals=dict(candidates=0,strict_raw=0,strict_legal=0,strict_floor=0)
    table=[]
    start=perf_counter()
    vertices={tuple(x):i for i,x in enumerate(p)}
    for e in range(k):
        available=candidate_grid(mask,contour,p,e)
        # Existing coordinates may be inserted only when that exact donor is removed.
        existing=np.array([vertices.get(tuple(x),-1) for x in available])
        inserts=[loss.score(np.insert(p,e+1,xy,axis=0),"xor") for xy,owner in zip(available,existing) if owner<0]
        for donor in range(k):
            if donor in (e,(e+1)%k): continue
            best=None; best_xy=None
            count=good=legal=protected=0
            for xy in available[(existing<0)|(existing==donor)]:
                trial=replace_vertex([p],0,donor,0,e,xy)[0]
                cost=loss.score(trial,"xor")
                count+=1
                if best is None or cost<best: best,best_xy=cost,xy.copy()
                if cost<old:
                    good+=1
                    if not simple(trial):continue
                    legal+=1
                    observed=bf.exact(paint(mask.shape,trial))
                    if observed<floor: continue
                    protected+=1
                    if cost<best_admissible:
                        best_admissible=cost
                        best_admissible_desc=(donor,e,xy.copy())
            totals["candidates"]+=count
            totals["strict_raw"]+=good
            totals["strict_legal"]+=legal
            totals["strict_floor"]+=protected
            if best_raw is None or best<best_raw:
                best_raw,best_desc=best,(donor,e,best_xy.copy())
            table.append(dict(donor=donor,edge=e,evaluated=count,min_raw_xor=best,x=int(best_xy[0]),y=int(best_xy[1]),
                              strict_raw=good,strict_legal=legal,strict_bf2=protected,
                              donor_alone_xor=loss.score(np.delete(p,donor,axis=0),"xor"),
                              best_insert_alone_xor=min(inserts)))
        if e%8==7:
            print("exhaustive real case",row["id"],e+1,k,totals,flush=True)
    save_rows(output/"all_donor_edge_scores.csv",table)
    donor,edge,xy=best_admissible_desc if best_admissible_desc else best_desc
    trial=replace_vertex([p],0,donor,0,edge,xy)[0]
    predicted=paint(mask.shape,trial)
    middle=np.delete(p,donor,axis=0)
    value=dict(id=row["id"],k=k,shape=mask.shape,stationary=p.tolist(),stationary_sha=sha(encode(mask.shape,p)),
               floor=[floor.numerator,floor.denominator],stationary_xor=old,best_unconstrained=best_raw,
               best_guarded_incumbent=best_admissible,donor=donor,edge=edge,insert_xy=xy.tolist(),
               deletion_only_xor=int(np.count_nonzero(paint(mask.shape,middle)!=mask)),
               insertion_only_xor=int(np.count_nonzero(paint(mask.shape,np.insert(p,edge+1,xy,axis=0))!=mask)),
               final_trial=trial.tolist(),final_xor=int(np.count_nonzero(predicted!=mask)),simple=bool(simple(trial)),
               final_bf2=float(bf.exact(predicted)),stationary_bf2=float(bf.exact(paint(mask.shape,p))),
               certified_directed_neighbors=len(scan),in_bounds_neighbors=sum(r["status"]!="outside" for r in scan),
               eligible_point_neighbors=sum(r["status"]=="eligible" for r in scan),
               elapsed_s=perf_counter()-start,**totals)
    (output/"real_case.json").write_text(json.dumps(value,indent=2),encoding="utf-8")
    return value


def read_poly_baseline(name,k):
    # Rebuild the immutable geometric start to fix the floor independently of POLY02 intermediates.
    from poly02.core import fit
    src=next(r for r in source_set()[0] if r["id"]==name)
    mask,contour=exterior(read_mask(src),k)
    return fit(mask,contour,k,"geometry",json.loads(CFG.read_text()))[0]


def positive_control():
    mask=np.zeros((17,17),np.uint8)
    # Reference has a small top protrusion and a much deeper bottom notch.
    target=np.array([[2,3],[7,2],[12,3],[12,13],[7,7],[2,13]],np.int32)
    mask=paint(mask.shape,target)
    before=target[[0,1,2,3,5]]
    after=replace_vertex([before],0,1,0,3,[7,7])[0]
    assert simple(before) and simple(after) and np.array_equal(after,target[[0,2,3,4,5]])
    cut=np.delete(before,1,0)
    xor=lambda q:int(np.count_nonzero(paint(mask.shape,q)!=mask))
    assert xor(cut)>xor(before)>xor(after)
    return dict(analytic_only=True,source=target.tolist(),before=before.tolist(),after=after.tolist(),
                donor=1,receiver_edge=3,reference_xor=xor(target),before_xor=xor(before),
                intermediate_xor=xor(cut),final_xor=xor(after))


def main():
    output=OUT/"cost_audit"
    output.mkdir(parents=True,exist_ok=False)
    all_rows=rows(OUT/"support/per_image.csv")
    if (OUT/"support_rest/per_image.csv").exists(): all_rows+=rows(OUT/"support_rest/per_image.csv")
    sources={r["id"]:r for r in source_set()[0]}
    costs=[]
    for row in all_rows:
        m,c=exterior(read_mask(sources[row["id"]]),int(row["k"]))
        costs.append(cost_row(m,c,row))
    save_rows(output/"isolated_vs_joint.csv",costs)
    selected=min((r for r in all_rows if r["k"]=="32"),key=lambda r:(int(r["min_deletion_cost"]),r["id"]))
    mask,c=exterior(read_mask(sources[selected["id"]]),32)
    (output/"analytic_control.json").write_text(json.dumps(positive_control(),indent=2),encoding="utf-8")
    print("costs done; full real case",selected["id"],selected["min_deletion_cost"],flush=True)
    strong(mask,c,selected,output)


if __name__=="__main__":
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.output:
        OUT=a.output.resolve();LOCAL=OUT/"polygons"
    main()
