"""Check geometry primitives against direct small exact calculations."""
import itertools
import numpy as np
from study import ROOT
from src.baselines import moments,line_error,dp_indices
from src.codec import encode,decode,paint,simple

p=np.array([(1,1),(2,0),(4,1),(6,2),(7,4),(6,6),(3,7),(1,6),(0,3)],np.int32)
q=np.vstack((p,p[0])).astype(float)
def explicit(i,j):
    d=q[j]-q[i]
    u=q[i:j]-q[i]
    return np.sum((u[:,0]*d[1]-u[:,1]*d[0])**2)/sum(d*d)
prefix=moments(p)
for i,j in itertools.combinations(range(len(q)),2):
    if np.array_equal(q[i],q[j]):
        continue
    assert np.isclose(explicit(i,j),line_error(prefix[j]-prefix[i],q[i],q[j]))
def loss(ids):
    return sum(explicit(i,j) for i,j in zip(ids,ids[1:]+[len(p)]))
ids=dp_indices(p,4,4).tolist()
best=min(loss([0]+list(t)) for t in itertools.combinations(range(1,len(p)),3))
assert np.isclose(loss(ids),best)
assert np.isclose(loss(dp_indices(p,4,-1).tolist()),best)
assert simple(p)
assert not simple(np.array([[0,0],[4,4],[0,4],[4,0]]))
assert not simple(np.array([[0,0],[2,0],[1,0],[3,3],[0,2]]))
blob=encode((9,9),p)
assert len(blob)==10+4*len(p) and np.array_equal(decode(blob),paint((9,9),p))
print("All arc costs, exhaustive fixed-K optimum, crossing checks and byte round trip passed.")
