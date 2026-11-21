"""One input/status contract for PM31 encoders, checkpoint timers and offline audit."""
from dataclasses import dataclass
from operator import index

import numpy as np
from poly03.allocation import candidates, curves, optimal, perimeter_counts
from poly03.maskcodec import Renderer, Unsupported, correspondence, digital, extract, length, supported_shape, vector_ok

SUCCESS = "success"
UNSUPPORTED = "unsupported_representation"
BELOW = "below_proved_lower_bound"
NO_OUTPUT = "search_no_valid_output"


@dataclass
class Preparation:
    status: str
    reason: str
    dense: list | None = None
    parents: list | None = None
    render: Renderer | None = None
    ref: object = None
    ref_masks: list | None = None
    lower_bound: int | None = None
    target: int | None = None
    high_vertices: int | None = None

    @property
    def rings(self):
        return None if self.dense is None else len(self.dense)


def prepare_input(raw, budget=None):
    """None means check support and exact representation, without imposing a rate."""
    if budget is not None:
        budget = index(budget)
        if budget < 0:
            raise ValueError("The byte budget must be nonnegative")
    try:
        if not isinstance(raw, np.ndarray) or not supported_shape(raw.shape):
            raise Unsupported("outside_coordinate_or_implementation_canvas_limit")
        if raw.dtype.kind not in "buif":
            raise Unsupported("expected_numeric_binary_samples")
        dense, parents = extract(raw)
        render = Renderer(raw.shape)
        ref_masks = [render.ring(p) for p in dense]
        high = np.zeros(raw.shape, np.uint8)
        for layer in ref_masks:
            high ^= layer
        if not np.array_equal(high, raw):
            raise Unsupported("full_precision_pixel_mismatch")
    except Unsupported as exc:
        return Preparation(UNSUPPORTED, str(exc))

    vertices = sum(map(len, dense))
    minimum = length(parents, 3 * len(dense))
    if budget is not None and budget < minimum:
        return Preparation(BELOW, "header+ring_metadata+three_vertices_per_ring", dense, parents,
                           render, None, ref_masks, minimum, None, vertices)
    target = vertices if budget is None else min(vertices, (budget - length(parents, 0)) // 4)
    return Preparation(SUCCESS, "ok", dense, parents, render, digital(raw), ref_masks, minimum, target, vertices)


def validate_rings(prep, rings):
    if sum(map(len, rings)) != prep.target or len(rings) != prep.rings:
        return "wrong_vertex_or_ring_count"
    vector = vector_ok(rings, prep.parents)
    if vector != "ok":
        return vector
    return correspondence(prep.ref, digital(prep.render.combined(rings)))


def allocation_seed(prep, cfg):
    """First legal allocation from the finite POLY03 candidates() pool, in additive-error order."""
    if prep.status != SUCCESS:
        return None, prep.reason
    if not prep.dense:
        return [], "ok"
    banks = curves(prep.dense, prep.ref_masks, prep.render, prep.target)
    dp = optimal(banks, prep.target)
    per = perimeter_counts(prep.dense, prep.target)
    for counts in candidates(banks, dp, per, prep.target, cfg):
        state = [b[k].points for b, k in zip(banks, counts)]
        if validate_rings(prep, state) == "ok":
            return state, "ok"
    return None, "no_valid_allocation_in_pool"
