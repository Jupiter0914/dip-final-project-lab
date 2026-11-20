"""Fixed-vertex outline simplification by maximum distance and squared line error."""
import heapq
import numpy as np


def root_contour(contour):
    # A deterministic extreme point provides a cut for the closed-ring DP.
    p = np.asarray(contour, dtype=np.int32)
    far = np.argmax(np.sum((p.astype(np.float64)-p[0])**2, axis=1))
    return np.roll(p, -int(far), axis=0)


def rdp_indices(points, k):
    """Douglas–Peucker N: split the arc having the largest point-to-segment error."""
    n = len(points)
    path = np.vstack([points, points[0]]).astype(np.float64)
    opposite = int(np.argmax(np.sum((path-path[0])**2,axis=1)))
    queue = []

    def push(a,b):
        if b-a < 2:
            return
        segment = path[b]-path[a]
        delta = path[a+1:b]-path[a]
        projection = np.clip(delta@segment / max(segment@segment,1),0,1)
        squared = np.sum((delta-projection[:,None]*segment)**2,axis=1)
        i = int(np.argmax(squared))
        heapq.heappush(queue, (-squared[i],a,b,a+i+1))

    selected = [0,opposite]
    push(0,opposite)
    push(opposite,n)
    while len(selected) < k:
        _, a, b, idx = heapq.heappop(queue)
        selected.append(idx)
        push(a,idx)
        push(idx,b)
    return np.array(sorted(selected))


def moments(points):
    x,y = points.astype(np.float64).T
    terms = np.stack((np.ones_like(x), x, y, x*x, x*y, y*y),axis=1)
    return np.vstack((np.zeros(6),np.cumsum(terms,axis=0)))


def line_error(stats,a,b):
    """Sum squared perpendicular distances on an arc via its six coordinate sums."""
    dx,dy = (b-a)[...,0], (b-a)[...,1]
    nx,ny = -dy,dx
    offset = -(nx*a[...,0] + ny*a[...,1])
    terms = (offset**2, 2*offset*nx, 2*offset*ny, nx**2, 2*nx*ny, ny**2)
    energy = sum(stats[...,i]*term for i,term in enumerate(terms))
    length2 = dx*dx + dy*dy
    return np.where(length2>0, np.maximum(energy,0) / np.maximum(length2,1), np.inf)


def dp_indices(points,k,grid):
    """Exact K-segment minimum ISE on the published candidate grid and fixed cut."""
    n=len(points)
    if grid == -1:
        ids=np.arange(n+1)
    else:
        rdp=rdp_indices(points,k)
        ids=np.unique(np.r_[rdp, np.linspace(0,n,min(n,k*grid)+1,dtype=int)])
    p=np.vstack((points,points[0]))[ids].astype(np.float64)
    prefix=moments(points)[ids]
    if grid == -1:
        # Build the full native-contour graph in strips to bound peak memory.
        edge=np.full((len(ids),len(ids)),np.inf)
        for start in range(0,len(ids),24):
            end=min(start+24,len(ids))
            arc=prefix[None,start+1:,:]-prefix[start:end,None,:]
            edge[start:end,start+1:]=line_error(arc,p[start:end,None,:],p[None,start+1:,:])
        for i in range(len(ids)):
            edge[i,:i+1]=np.inf
    else:
        arc=prefix[None,:,:]-prefix[:,None,:]
        edge=line_error(arc,p[:,None,:],p[None,:,:])
        edge[np.tril_indices(len(ids))]=np.inf
    distance=np.full(len(ids),np.inf)
    distance[0]=0
    parent=np.zeros((k+1,len(ids)),int)
    for m in range(1,k+1):
        cost=distance[:,None]+edge
        parent[m]=np.argmin(cost,axis=0)
        distance=np.min(cost,axis=0)
    if not np.isfinite(distance[-1]):
        raise ValueError("No feasible DP path")
    last=len(ids)-1
    result=[]
    for m in range(k,0,-1):
        last=parent[m,last]
        result.append(ids[last])
    return np.array(result[::-1])
