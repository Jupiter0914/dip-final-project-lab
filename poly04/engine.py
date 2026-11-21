"""PM31 exchange with immediate synchronous delivery of each completed, verified byte stream."""
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from poly03.atomic import replace_vertex
from poly03.cgal_bridge import simplify
from poly03.maskcodec import correspondence, digital, pack, vector_ok
from .prepare import SUCCESS, NO_OUTPUT, allocation_seed, prepare_input, validate_rings
from .proposals import candidates_for_method

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "configs/poly03/full.json").read_text(encoding="utf-8"))
METHODS = ("seed", "within_old", "within_full_oldtri", "within_full", "cross_oldtri",
           "cross_full_oldtri", "cross", "cgal", "cgal_within", "exact")
cv2.setNumThreads(1)


def forward_subsequence(dense, rings):
    """Orient each CGAL cycle along its dense source; preserve the first native vertex."""
    if len(dense) != len(rings):
        return None, [], "cgal_ring_identity"
    result, mapping = [], []
    for raw, ring in zip(dense, rings):
        lookup = {tuple(x): i for i, x in enumerate(raw.tolist())}
        ids = [lookup.get(tuple(x)) for x in ring]
        if any(i is None for i in ids) or len(set(ids)) != len(ids) or len(ids) < 3:
            return None, mapping, "cgal_not_source_subsequence"
        n = len(raw)
        progress = sum((ids[(i + 1) % len(ids)] - j) % n for i, j in enumerate(ids))
        reverse = progress != n
        if reverse:
            ids = ids[:1] + ids[:0:-1]
            if sum((ids[(i + 1) % len(ids)] - j) % n for i, j in enumerate(ids)) != n:
                return None, mapping, "cgal_noncyclic_subsequence"
        result.append(np.ascontiguousarray(raw[ids]))
        mapping.append(dict(reversed=reverse, dense_indices=ids))
    return result, mapping, "ok"


def cgal_seed(prep, method, result):
    dense, par, render = prep.dense, prep.parents, prep.render
    if not dense:
        rings, meta = [], dict(status="ok", input_vertices=0, output_vertices=0, startup_ms=0.)
    else:
        rings, meta = simplify(dense, prep.target, cost="squared")
    result["raw_cgal_status"] = meta["status"]
    result["cgal_worker"] = meta
    # Hold the native arrays through the timing boundary; archive-only transformations
    # (lists, SHA and any unused native byte stream) happen in finish() after search end.
    result["raw_cgal_rings"] = rings
    if meta["status"] != "ok":
        return None, meta["status"]
    why = validate_rings(prep, rings)
    if why != "ok":
        return None, why
    if method == "cgal":
        return rings, "ok"
    mapped, info, why = forward_subsequence(dense, rings)
    result["mapping"] = info
    if why != "ok":
        return None, why
    # A common PM31 ring rotation/orientation must not change any native pixel.
    if not np.array_equal(render.combined(rings), render.combined(mapped)):
        return None, "cgal_orientation_changed_pixels"
    return mapped, "ok"


def exchange_step(raw, prep, state, method):
    render, refs, par = prep.render, prep.ref_masks, prep.parents
    moves, log = candidates_for_method(prep.dense, refs, state, render, method, CFG)
    current_layers = [render.ring(p) for p in state]
    current = np.zeros(raw.shape, np.uint8)
    for layer in current_layers:
        current ^= layer
    current_xor = int(np.count_nonzero(current != raw))
    exact = method == "exact"
    losses = [] if exact else [int(np.count_nonzero(p != r)) for p, r in zip(current_layers, refs)]
    base_add = None if exact else sum(losses)
    ranked = []
    for i, (_, dr, dj, rr, rj, xy) in enumerate(moves):
        trial = replace_vertex(state, dr, dj, rr, rj, xy)
        additive = base_add
        predicted = current.copy() if exact else None
        for changed in {dr, rr}:
            new_layer = render.ring(trial[changed])
            if not exact:
                additive += int(np.count_nonzero(new_layer != refs[changed])) - losses[changed]
            else:
                predicted ^= current_layers[changed]
                predicted ^= new_layer
        if exact:
            value = int(np.count_nonzero(predicted != raw))
            if value >= current_xor:
                continue
        else:
            value = additive
            if value >= base_add:
                continue
        ranked.append((value, i, trial, (dr, dj, rr, rj, xy), additive))
    log.update(ranked_improving=len(ranked),
               full_checks=0, structural_rejects=0, accepted=0, xor_before=current_xor)
    for _, _, trial, move, additive in sorted(ranked, key=lambda item: item[:2]):
        output = render.combined(trial)
        log["full_checks"] += 1
        new_xor = int(np.count_nonzero(output != raw))
        if new_xor >= current_xor:
            continue
        why = vector_ok(trial, par)
        if why != "ok" or correspondence(prep.ref, digital(output)) != "ok":
            log["structural_rejects"] += 1
            continue
        dr, dj, rr, rj, xy = move
        log.update(accepted=1, cross=int(dr != rr), triangle=int(len(state[dr]) == 3),
                   xor_after=new_xor, additive_before=base_add, additive_after=additive,
                   donor=dr, donor_vertex=dj, receiver=rr, receiver_edge=rj, insert=xy)
        return trial, log
    return state, log


def encode(raw, budget, method, on_checkpoint, max_ms=200, max_rounds=8):
    """on_checkpoint(bytes, event) runs before any later search. A failure yields no event."""
    t0 = time.perf_counter_ns()
    if method not in METHODS or not callable(on_checkpoint) or max_ms < 0 or max_rounds < 0:
        raise ValueError("Invalid method, callback, deadline, or round cap")
    elapsed = lambda: (time.perf_counter_ns() - t0) / 1e6
    result = dict(method=method, start_ns=t0, status=None, reason=None, seed_ms=None,
                  rounds=0, proposed_pairs=0, accepted_moves=0, cross_moves=0, triangle_moves=0,
                  raw_cgal_blob=None, raw_cgal_sha256="", raw_cgal_status="", mapping=[], round_log=[])
    prep = prepare_input(raw, budget)
    result.update(rings=prep.rings, lower_bound=prep.lower_bound, target_vertices=prep.target,
                  high_vertices=prep.high_vertices)
    def finish(status, reason):
        result.update(status=status, reason=reason, end_ms=elapsed())
        if "raw_cgal_rings" in result:
            native = result["raw_cgal_rings"]
            if result["raw_cgal_blob"] is None and len(native) == prep.rings and all(len(p) >= 3 for p in native):
                result["raw_cgal_blob"] = pack(raw.shape, native, prep.parents)
            if result["raw_cgal_blob"] is not None:
                result["raw_cgal_sha256"] = hashlib.sha256(result["raw_cgal_blob"]).hexdigest()
            result["raw_cgal_rings"] = [p.tolist() for p in native]
        result["return_ms"] = elapsed()
        return result
    if prep.status != SUCCESS:
        return finish(prep.status, prep.reason)
    if method in ("cgal", "cgal_within"):
        state, reason = cgal_seed(prep, method, result)
    else:
        state, reason = allocation_seed(prep, CFG)
    if state is None:
        return finish(NO_OUTPUT, reason)
    result["seed_ms"] = elapsed()

    def deliver(round_number):
        blob = pack(raw.shape, state, prep.parents)
        serialized_ms = elapsed()
        event = dict(start_ns=t0, round=round_number, payload_bytes=len(blob), serialized_ms=serialized_ms,
                     proposed_pairs=result["proposed_pairs"], accepted_moves=result["accepted_moves"],
                     cross_moves=result["cross_moves"], triangle_moves=result["triangle_moves"])
        event["delivered_ms"] = elapsed()
        on_checkpoint(blob, event)
        if round_number == 0 and method in ("cgal", "cgal_within") and not any(m["reversed"] for m in result["mapping"]):
            result["raw_cgal_blob"] = blob
    deliver(0)
    if method not in ("seed", "cgal"):
        for step in range(1, max_rounds + 1):
            if elapsed() > max_ms:
                break
            state, log = exchange_step(raw, prep, state, method)
            result["rounds"] += 1
            result["proposed_pairs"] += log["proposed_pairs"]
            log["round"] = step
            result["round_log"].append(log)
            if not log["accepted"]:
                break
            result["accepted_moves"] += 1
            result["cross_moves"] += log["cross"]
            result["triangle_moves"] += log["triangle"]
            deliver(step)
    return finish(SUCCESS, "ok")
