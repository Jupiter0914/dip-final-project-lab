"""Exact top-K candidate preordering from full-canvas individual deletion/insertion scores."""
import heapq
import itertools
from collections import Counter, defaultdict
import numpy as np


def individual_scores(dense, refs, state, render, triangles):
    donors = []
    receivers = []
    for ri, (source, truth, ring) in enumerate(zip(dense, refs, state)):
        base = np.count_nonzero(render.ring(ring) != truth)
        index = {tuple(xy): i for i, xy in enumerate(source.tolist())}
        for j, point in enumerate(ring):
            if triangles or len(ring) > 3:
                # For a triangle the K-1 proxy is LINE_8's two-point trace. It is
                # never encoded; only the final same-ring three-point polygon qualifies.
                cut = np.delete(ring, j, axis=0)
                loss = int(np.count_nonzero(render.ring(cut) != truth) - base)
                donors.append((loss, ri, j))
            following = (j + 1) % len(ring)
            begin, end = index[tuple(point)], index[tuple(ring[following])]
            count = (end - begin - 1) % len(source)
            if not count:
                continue
            arc = source[(begin + np.arange(1, count + 1)) % len(source)]
            segment = (ring[following] - point).astype(float)
            offset = arc - point
            fraction = np.clip(offset @ segment / max(1., segment @ segment), 0, 1)
            distance2 = np.sum((offset - fraction[:, None] * segment) ** 2, axis=1)
            for q in sorted({int(distance2.argmax()), len(arc) // 2}):
                xy = tuple(map(int, arc[q]))
                trial = np.insert(ring, j + 1, xy, axis=0)
                gain = int(np.count_nonzero(render.ring(trial) != truth) - base)
                receivers.append((gain, ri, j, xy))
    return donors, receivers


def shortlist(items, n):
    ordered = sorted(items)
    per_ring = {}
    for entry in ordered:
        per_ring.setdefault(entry[1], entry)
    return sorted(set(ordered[:n] + list(per_ring.values())))


def sorted_pairs(donors, receivers, state, cross, limit):
    # Each donor supplies a sorted stream: adding its fixed error preserves receiver
    # order, including lexical tie breaks. An exact k-way merge avoids a quadratic sort.
    receivers = sorted(receivers)
    by_ring = defaultdict(list)
    per_edge = Counter()
    for item in receivers:
        by_ring[item[1]].append(item)
        per_edge[item[1], item[2]] += 1

    def for_donor(d, allowed):
        loss, ri, j = d
        for gain, si, edge, xy in allowed:
            if ri == si and (j == edge or j == (edge + 1) % len(state[si])):
                continue
            yield loss + gain, ri, j, si, edge, xy

    streams = []
    eligible = 0
    for d in donors:
        _, ri, j = d
        allowed = receivers if cross and len(state[ri]) > 3 else by_ring[ri]
        eligible += len(allowed) - per_edge[ri, j] - per_edge[ri, (j - 1) % len(state[ri])]
        streams.append(for_donor(d, allowed))
    return list(itertools.islice(heapq.merge(*streams), limit)), eligible


def candidates_for_method(dense, refs, state, render, method, cfg):
    historical = method in ("within_old", "cross_oldtri")
    triangles = method not in ("within_old", "cross_oldtri", "within_full_oldtri", "cross_full_oldtri")
    cross = method in ("cross", "cross_oldtri", "cross_full_oldtri", "exact") and len(state) > 1
    donors, receivers = individual_scores(dense, refs, state, render, triangles)
    all_donors, all_receivers = len(donors), len(receivers)
    if historical:
        donors = shortlist(donors, cfg["donor_shortlist"])
        receivers = shortlist(receivers, cfg["receiver_shortlist"])
    pairs, eligible = sorted_pairs(donors, receivers, state, cross, cfg["final_pairs_per_round"])
    return pairs, dict(donors=all_donors, receivers=all_receivers, eligible_pairs=eligible,
                       proposed_pairs=len(pairs), proposed_cross=sum(p[1] != p[3] for p in pairs),
                       proposed_triangles=sum(len(state[p[1]]) == 3 for p in pairs))
