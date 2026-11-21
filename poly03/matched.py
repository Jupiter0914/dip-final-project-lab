"""Production scorers for the matched-time control. Diagnostics are outside timed runs."""
import numpy as np
from .atomic import replace_vertex
from .exchange import proposals
from .maskcodec import vector_ok,digital,correspondence


def full_step(raw,dense,par,render,ref,refs,state,cached,cfg,audit=False):
    items=proposals(dense,refs,state,render,"all",cfg)
    if cached:
        before=[render.ring(p) for p in state]
        current=np.zeros_like(raw)
        for layer in before: current^=layer
    else:
        current=render.combined(state)
    start=int(np.count_nonzero(current!=raw))
    ranked=[]
    for pos,(_,di,dj,ri,rj,xy) in enumerate(items):
        candidate=replace_vertex(state,di,dj,ri,rj,xy)
        if cached:
            # Only exactly identical rings are reused. Every changed ring is redrawn on the full canvas.
            pred=current.copy()
            for i in {di,ri}:
                pred^=before[i]
                pred^=render.ring(candidate[i])
            if audit and not np.array_equal(pred,render.combined(candidate)):
                raise AssertionError("Whole-canvas native parity differs")
        else:
            pred=render.combined(candidate)
        value=int(np.count_nonzero(pred!=raw))
        if value<start:ranked.append((value,pos,candidate,(di,dj,ri,rj,xy)))
    for val,_,trial,move in sorted(ranked,key=lambda x:(x[0],x[1])):
        if vector_ok(trial,par)!="ok":continue
        # Independent complete redraw for the accepted structural check.
        actual=render.combined(trial)
        if correspondence(ref,digital(actual))!="ok":continue
        assert int(np.count_nonzero(raw!=actual))==val
        di,dj,ri,rj,xy=move
        return trial,dict(donor=di,donor_vertex=dj,receiver=ri,receiver_edge=rj,insert=list(xy),before=start,after=val),len(items)
    return state,None,len(items)
