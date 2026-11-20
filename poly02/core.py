"""POLY02 area objectives and boundary-protected refinement on native integer pixels."""
from fractions import Fraction
import cv2
import numpy as np

from src.baselines import dp_indices, rdp_indices, root_contour
from src.codec import simple, paint
from src.method import DIRECTIONS, refine as geometric_refine, safe_indices

KERNEL=np.ones((3,3),np.uint8)


def exterior(binary,k):
    raw=np.ascontiguousarray(binary!=0,dtype=np.uint8)
    curves,_=cv2.findContours(raw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    if not curves:
        raise ValueError("Empty foreground")
    contour=max(curves,key=cv2.contourArea).reshape(-1,2)
    if k<3 or len(contour)<k or cv2.contourArea(contour)<1:
        raise ValueError(f"Outline samples or area insufficient for requested K={k}")
    mask=np.zeros_like(raw)
    cv2.drawContours(mask,[contour],-1,1,cv2.FILLED,cv2.LINE_8)
    return mask,contour


def shape_info(raw,mask):
    raw=np.ascontiguousarray(raw!=0,dtype=np.uint8)
    components=cv2.connectedComponents(raw,connectivity=8)[0]-1
    # One 4-connected exterior background component after padding.
    holes=cv2.connectedComponents(1-np.pad(raw,1),connectivity=4)[0]-2
    return dict(components=components,holes=holes,raw_area=int(raw.sum()),area=int(mask.sum()),
                added=int(np.count_nonzero(mask>raw)),removed=int(np.count_nonzero(mask<raw)))


def boundary(mask):
    return mask-cv2.erode(mask,KERNEL,borderType=cv2.BORDER_CONSTANT,borderValue=0)


def disk(r):
    y,x=np.ogrid[-r:r+1,-r:r+1]
    return np.asarray(x*x+y*y<=r*r,np.uint8)


class BoundaryScore:
    def __init__(self,mask,r):
        self.ref=boundary(mask)
        self.size=cv2.countNonZero(self.ref)
        self.kernel=disk(r)
        self.near=cv2.dilate(self.ref,self.kernel)

    def exact(self,pred):
        edge=boundary(pred)
        count=cv2.countNonZero(edge)
        hit_pred=cv2.countNonZero(cv2.bitwise_and(edge,self.near))
        hit_ref=cv2.countNonZero(cv2.bitwise_and(self.ref,cv2.dilate(edge,self.kernel)))
        den=hit_pred*self.size+hit_ref*count
        return Fraction(2*hit_pred*hit_ref,den) if den else Fraction(0)


def metrics(mask,pred):
    fp=int(np.count_nonzero(pred>mask))
    fn=int(np.count_nonzero(mask>pred))
    hits=cv2.countNonZero(mask)-fn
    return dict(xor=fp+fn,fp=fp,fn=fn,iou=hits/(hits+fp+fn),
                **{f"bf{r}":float(BoundaryScore(mask,r).exact(pred)) for r in (1,2,3)})


class RasterLoss:
    def __init__(self,mask):
        self.target=mask
        self.area=cv2.countNonZero(mask)
        self.render=np.empty_like(mask)
        self.work=np.empty_like(mask)

    def score(self,poly,objective):
        self.render.fill(0)
        cv2.fillPoly(self.render,[poly],1,lineType=cv2.LINE_8)
        if objective=="xor":
            return cv2.countNonZero(cv2.bitwise_xor(self.render,self.target,dst=self.work))
        hit=cv2.countNonZero(cv2.bitwise_and(self.render,self.target,dst=self.work))
        return -Fraction(hit,self.area+cv2.countNonZero(self.render)-hit)


def initial(points,k,grid,rdp=False):
    if len(points)<k:
        raise ValueError(f"Not enough samples for K={k}")
    ids=rdp_indices(points,k) if rdp else dp_indices(points,k,grid)
    if simple(points[ids]):
        return ids,0
    if not rdp:
        ids=rdp_indices(points,k)
        if simple(points[ids]):
            return ids,1
    try:
        return safe_indices(points,k),2
    except (ValueError,IndexError) as exc:
        raise ValueError(f"Greedy insertion did not find a legal ring at K={k}") from exc


def local_search(mask,start,radii,objective,guard=False,trace=None):
    poly=start.copy()
    loss=RasterLoss(mask)
    current=loss.score(poly,objective)
    start_cost=float(current)
    scorer=BoundaryScore(mask,2) if guard else None
    floor=scorer.exact(loss.render) if guard else None
    stats=dict(proposals=0,accepted=0,invalid=0,boundary_rejected=0)
    h,w=mask.shape
    for sweep,radius in enumerate(radii):
        order=range(len(poly)) if sweep%2==0 else reversed(range(len(poly)))
        for j in order:
            old=poly[j].copy()
            choices=[]
            for direction in DIRECTIONS:
                xy=old+radius*direction
                if 0<=xy[0]<w and 0<=xy[1]<h:
                    poly[j]=xy
                    choices.append((loss.score(poly,objective),xy))
            poly[j]=old
            stats["proposals"]+=len(choices)
            # Python stable sort preserves v1's original eight-direction tie order.
            for cost,xy in sorted(choices,key=lambda p:p[0]):
                if cost>=current:
                    break
                poly[j]=xy
                if not simple(poly):
                    stats["invalid"]+=1
                    poly[j]=old
                    continue
                observed=None
                if guard:
                    predicted=paint(mask.shape,poly)
                    observed=scorer.exact(predicted)
                rejected=guard and observed<floor
                if trace is not None:
                    after=poly.copy()
                    before=poly.copy()
                    before[j]=old
                    trace.append(dict(sweep=sweep,step=radius,vertex=j,accepted=not rejected,
                                      old_xy=old.tolist(),new_xy=xy.tolist(),before=before.tolist(),after=after.tolist(),
                                      before_cost=float(current),trial_cost=float(cost),
                                      floor=float(floor) if guard else None,bf2=float(observed) if guard else None))
                if rejected:
                    stats["boundary_rejected"]+=1
                    poly[j]=old
                    continue
                current=cost
                stats["accepted"]+=1
                break
    stats.update(start_cost=start_cost,final_cost=float(current),floor_bf2=float(floor) if guard else "")
    return poly,stats


def sequential_iou(mask,points,k,sm_start):
    m=min(len(points),max(sm_start,k+1))
    if m<=k:
        raise ValueError("SM needs an initial ring with more than K sampled vertices")
    ids,fallback=initial(points,m,0,rdp=True)
    poly=points[ids]
    loss=RasterLoss(mask)
    proposals=invalid=0
    while len(poly)>k:
        choices=[]
        for j in range(len(poly)):
            cand=np.delete(poly,j,axis=0)
            choices.append((loss.score(cand,"iou"),j))
        proposals+=len(choices)
        for _,j in sorted(choices):
            cand=np.delete(poly,j,axis=0)
            if simple(cand):
                poly=cand
                break
            invalid+=1
        else:
            raise ValueError("SM found no legal single-vertex deletion")
    return poly,dict(initial_vertices=m,fallback=fallback,proposals=proposals,accepted=m-k,invalid=invalid)


def fit(mask,contour,k,method,cfg,trace=None):
    points=root_contour(contour)
    if method=="sm_iou":
        return sequential_iou(mask,points,k,cfg["sm_start"])
    grid=-1 if method=="full_dp" else cfg["grid"]
    ids,fallback=initial(points,k,grid,rdp=method=="rdp")
    poly=points[ids]
    radii=cfg["radii"]
    stats=dict(fallback=fallback,initial_vertices=k)
    if method in ("rdp","grid_dp","full_dp"):
        return poly,stats
    if method in ("geometry","post_xor","post_guard"):
        poly,geo=geometric_refine(mask,points,ids,radii,"geometry")
        stats.update(geo_proposals=geo["proposals"],geo_accepted=geo["accepted"])
        if method=="geometry":
            return poly,stats
    if method not in ("raster","local_iou","post_xor","post_guard"):
        raise ValueError(method)
    objective="iou" if method=="local_iou" else "xor"
    result,search=local_search(mask,poly,radii,objective,guard=(method=="post_guard"),trace=trace)
    return result,{**stats,**search}
