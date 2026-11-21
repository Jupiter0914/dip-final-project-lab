"""Untimed exact-vs-additive screening audit on a received, decodable checkpoint."""
import numpy as np
from poly03.atomic import replace_vertex
from poly03.maskcodec import correspondence, digital, unpack, vector_ok
from .engine import CFG, forward_subsequence
from .prepare import prepare_input, SUCCESS
from .proposals import candidates_for_method


def audit_screen(raw, budget, blob):
    prep = prepare_input(raw, budget)
    if prep.status != SUCCESS:
        return dict(status=prep.status, reason=prep.reason, proposed_pairs=0)
    shape, state, par = unpack(blob)
    if shape != raw.shape or par != prep.parents or sum(map(len, state)) != prep.target:
        raise ValueError("Checkpoint does not use this reference or rate")
    # Enforce cyclic membership without changing lexicographic indexing of a valid state.
    mapped, mapping, reason = forward_subsequence(prep.dense, state)
    if reason != "ok" or any(x["reversed"] for x in mapping):
        raise ValueError("Expected a native-order DP/exchange checkpoint")
    ren = prep.render
    if correspondence(prep.ref, digital(ren.combined(state))) != "ok":
        raise ValueError("Checkpoint fails reference correspondence")
    candidates, _ = candidates_for_method(prep.dense, prep.ref_masks, state, ren, "exact", CFG)
    def score(p):
        layers = [ren.ring(ring) for ring in p]
        additive = sum(int(np.count_nonzero(a != b)) for a, b in zip(layers, prep.ref_masks))
        full = int(np.count_nonzero(ren.combined(p) != raw))
        return additive, full
    before_add, before_xor = score(state)
    joint = []
    for i, (_, di, dj, ri, ei, xy) in enumerate(candidates):
        trial = replace_vertex(state, di, dj, ri, ei, xy)
        added, full = score(trial)
        valid = False
        if full < before_xor:
            valid = vector_ok(trial, par) == "ok" and correspondence(prep.ref, digital(ren.combined(trial))) == "ok"
        joint.append(dict(order=i, donor=di, vertex=dj, receiver=ri, edge=ei, xy=xy,
                          additive=added, full=full, valid_improvement=valid))
    legal = [a for a in joint if a["valid_improvement"]]
    filtered = [a for a in legal if a["additive"] < before_add]
    best = min(legal, key=lambda a: (a["full"], a["order"])) if legal else None
    add_best = min(filtered, key=lambda a: (a["additive"], a["order"])) if filtered else None
    return dict(status=SUCCESS, before_xor=before_xor, before_add=before_add, proposed_pairs=len(joint),
                xor_improving=sum(a["full"] < before_xor for a in joint),
                skipped_by_add=sum(a["full"] < before_xor and a["additive"] >= before_add for a in joint),
                valid_skipped_by_add=len(legal)-len(filtered), exact_choice=best, additive_choice=add_best,
                choices_differ=best != add_best, candidates=joint)
