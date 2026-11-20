"""Encode one outer silhouette at a fixed integer vertex budget."""
import cv2
import numpy as np
from .baselines import root_contour, rdp_indices, dp_indices, moments, line_error
from .codec import simple

DIRECTIONS = np.array([(x,y) for y in (-1,0,1) for x in (-1,0,1) if x or y], dtype=np.int32)


def refine(mask, contour, ids, radii, objective):
    """Try the same eight integer moves for both objectives. Accept only a better valid ring."""
    poly = contour[ids].copy()
    h,w = mask.shape
    rendered = np.empty_like(mask)
    diff = np.empty_like(mask)
    arc = np.diff(moments(contour)[np.r_[ids,len(contour)]],axis=0)
    checked = accepted = 0

    def raster_error():
        rendered.fill(0)
        cv2.fillPoly(rendered,[poly],1,lineType=cv2.LINE_8)
        cv2.bitwise_xor(rendered,mask,dst=diff)
        return cv2.countNonZero(diff)

    raster_cost = raster_error() if objective == "raster" else 0
    for sweep, radius in enumerate(radii):
        order = range(len(poly)) if sweep%2 == 0 else reversed(range(len(poly)))
        for j in order:
            origin = poly[j].copy()
            candidates = origin + radius * DIRECTIONS
            inside = np.all((candidates >= 0) & (candidates < [w,h]),axis=1)
            candidates = candidates[inside]
            checked += len(candidates)
            if objective == "raster":
                current = raster_cost
                costs = []
                for point in candidates:
                    poly[j] = point
                    costs.append(raster_error())
            else:
                left,right = poly[j-1].astype(float),poly[(j+1)%len(poly)].astype(float)
                moves = np.vstack([origin,candidates]).astype(float)
                values = line_error(arc[j-1],left,moves) + line_error(arc[j],moves,right)
                current, costs = values[0], values[1:]
            poly[j] = origin
            for i in np.argsort(costs,kind="stable"):
                if costs[i] >= current - 1e-9:
                    break
                poly[j] = candidates[i]
                if simple(poly):
                    accepted += 1
                    if objective == "raster":
                        raster_cost = costs[i]
                    break
                poly[j] = origin
    return poly, dict(proposals=checked, accepted=accepted)


def safe_indices(points,k):
    """Start from a triangle and reject any insertion that crosses the current ring."""
    ids=rdp_indices(points,3).tolist()
    while len(ids)<k:
        candidates=[]
        for left,right in zip(ids,ids[1:]+[len(points)]):
            idx=np.arange(left+1,right)
            if not len(idx):
                continue
            a=points[left].astype(float)
            v=points[right%len(points)]-a
            d=points[idx]-a
            t=np.clip(d@v/max(v@v,1),0,1)
            error=np.sum((d-t[:,None]*v)**2,axis=1)
            candidates.extend(zip(-error,idx))
        for _,i in sorted(candidates):
            trial=sorted(ids+[int(i)])
            if simple(points[trial]):
                ids=trial
                break
        else:
            raise ValueError("No simple K-vertex ring exists on the sampled foreground")
    return np.asarray(ids)


def fit(mask, contour, k, method, grid, radii):
    method = {"full_dp":"dp", "geometry_long":"geometry"}.get(method,method)
    points = root_contour(contour)
    ids = rdp_indices(points,k) if method == "rdp" else dp_indices(points,k,grid)
    stats = dict(fallback=0, proposals=0, accepted=0)
    if not simple(points[ids]):
        ids = rdp_indices(points,k)
        stats["fallback"] = 1
    if not simple(points[ids]):
        ids = safe_indices(points,k)
        stats['fallback'] = 2
    if method in ("raster","geometry"):
        polygon, search = refine(mask,points,ids,radii,method)
        stats.update(search)
    elif method in ("rdp","dp"):
        polygon = points[ids]
    else:
        raise ValueError(method)
    return polygon,stats
