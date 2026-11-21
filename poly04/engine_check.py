"""Targeted PM31 checks on synthetic arrays and the already inspected POLY03 development set."""
import argparse
import csv
import hashlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

from poly02.data import read_mask, rows
from poly03 import anytime, export, full_run, full_verify, phase_control, repair
from poly03.atomic import replace_vertex
from poly03.full_data import MANIFEST
from poly03.maskcodec import Renderer, decode, pack
from . import engine
from .engine_audit import audit_screen
from .prepare import BELOW, NO_OUTPUT, SUCCESS, UNSUPPORTED, prepare_input
from .proposals import candidates_for_method, individual_scores

ROOT = Path(__file__).resolve().parents[1]


def verify_states():
    blank = np.zeros((9, 11), np.uint8)
    one = blank.copy()
    one[2, 3] = 1
    diagonal = one.copy()
    diagonal[3, 4] = 1
    hole = np.ones_like(one)
    hole[3, 5] = 0
    invalid = np.zeros((1, 16383), np.uint8)
    tests = [
        ("empty", blank, 10, SUCCESS), ("pixel", one, 128, SUCCESS),
        ("diagonal", diagonal, 128, SUCCESS), ("single_hole", hole, 256, SUCCESS),
        ("below", one, 12, BELOW), ("wide", invalid, 128, UNSUPPORTED),
        ("wrong_dimension", np.zeros((3, 3, 3), np.uint8), 256, UNSUPPORTED),
        ("nonbinary", np.full((3, 4), 2, np.uint8), 256, UNSUPPORTED),
    ]
    for label, raw, budget, expected in tests:
        p = prepare_input(raw, budget)
        assert p.status == expected, label
        recorded = []
        r = engine.encode(raw, budget, "cross", lambda b, e: recorded.append((b, e)), max_rounds=0)
        assert r["status"] == expected and bool(recorded) == (expected == SUCCESS)
        if expected == SUCCESS:
            assert np.array_equal(raw, decode(recorded[0][0]))
        assert anytime.init(raw, budget)[1] == expected
        assert repair.solve(raw, budget, "cost_order")[0]["status"] == expected
        assert phase_control.solve(raw, budget)[0]["status"] == expected
        assert export.encode_one(raw, budget, rounds=0)[1]["status"] == expected
        if expected != SUCCESS:
            source = dict(id=label, dataset="fixture", stratum="fixture", components=0, holes=0)
            with patch.object(full_run, "read_mask", return_value=raw):
                results, _, _ = full_run.run_one(source, budget, None, None, anytime.CFG)
            assert len(results) == len(full_run.METHODS) and all(x["status"] == expected for x in results)
    with patch("poly04.prepare.extract", side_effect=RuntimeError("deliberate program fault")):
        for fun in (lambda: anytime.init(one, 100), lambda: engine.encode(one, 100, "seed", lambda *a: None),
                    lambda: repair.solve(one, 100, "cost_order"), lambda: export.encode_one(one, 100)):
            try:
                fun()
            except RuntimeError as exc:
                assert str(exc) == "deliberate program fault"
            else:
                raise AssertionError("Unexpected errors must propagate")
    with patch("poly03.maskcodec.parents", side_effect=ValueError("deliberate predicate fault")):
        try:
            prepare_input(one, 100)
        except ValueError as exc:
            assert str(exc) == "deliberate predicate fault"
        else:
            raise AssertionError("Unexpected ValueError must propagate")
    # Lossless support must be checked even when the requested budget is too low.
    with patch.object(Renderer, "ring", lambda self, points: np.zeros(self.shape, np.uint8)):
        p = prepare_input(one, 1)
        assert p.status == UNSUPPORTED and p.reason == "full_precision_pixel_mismatch"
    for m in ("cgal", "cgal_within"):
        with patch.object(engine, "simplify", return_value=([], dict(status="cgal_rejected", detail="fixture"))):
            events = []
            result = engine.encode(one, 128, m, lambda *x: events.append(x))
            assert result["status"] == NO_OUTPUT and not events
    return [label for label, *_ in tests]


def offline_fixture():
    """Exercise the historical audit input path including unsupported/empty/failure rows."""
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        manifest = folder/"manifest.csv"
        images = dict(wide=np.zeros((1, 16383), np.uint8), empty=np.zeros((3, 2), np.uint8),
                      pixel=np.array([[0, 1], [0, 0]], np.uint8))
        blob = pack(images["empty"].shape, [], [])
        stream = [
            ("main", dict(id="wide", budget="128", status=UNSUPPORTED, reason="outside_coordinate_or_implementation_canvas_limit")),
            ("main", dict(id="pixel", budget="0", status=BELOW)),
            ("main", dict(id="pixel", budget="30", status=NO_OUTPUT)),
            ("main", dict(id="empty", budget="10", status=SUCCESS, blob="empty.pm3", sha256=hashlib.sha256(blob).hexdigest(),
                          xor="0", iou="1", file_bytes="10")),
        ]
        archive = folder/"outputs.zip"
        with ZipFile(archive, "w") as z:
            z.writestr("results/empty.pm3", blob)
        def fixture_rows(path):
            if path == manifest:
                return [dict(id=i) for i in images]
            if path.name == "allocation_candidates.csv":
                return [dict(id="empty", counts="", additive_xor=0, whole_xor=0, vector="ok", digital="ok")]
            if path.name == "per_image.csv":
                return [dict(id="wide", budget="128", rep="0", method="additive", deadline_ms="100", status=UNSUPPORTED),
                        dict(id="pixel", budget="0", rep="0", method="additive", deadline_ms="100", status=BELOW)]
            return []
        with (patch.object(full_verify, "MANIFEST", manifest), patch.object(full_verify, "ARCHIVE", archive),
              patch.object(full_verify, "rows", fixture_rows),
              patch.object(full_verify, "read_mask", lambda row: images[row["id"]]),
              patch.object(full_verify, "read_records", lambda: iter(stream))):
            report = full_verify.check()
        assert report["scored_rows"] == 1 and report["sources"] == 3 and report["independent_allocation_candidates"] == 1
        return report["scored_rows"]


def candidate_checks():
    # Two different-sized cycles with a triangle donor and multiple interior edge samples.
    raw = np.zeros((30, 42), np.uint8)
    raw[3:14, 2:17] = 1
    raw[7:13, 12:17] = 0
    raw[17:25, 21:38] = 1
    p = prepare_input(raw, 256)
    state = [r[np.linspace(0, len(r), num=k, endpoint=False, dtype=int)] for r, k in zip(p.dense, (3, 4))]
    for m in ("within_full_oldtri", "within_full", "cross_full_oldtri", "cross", "exact"):
        triangle = m not in ("within_full_oldtri", "cross_full_oldtri")
        cross = m.startswith("cross") or m == "exact"
        d, q = individual_scores(p.dense, p.ref_masks, state, p.render, triangle)
        brute = []
        for a, di, dj in d:
            for b, ri, ei, xy in q:
                if di != ri and (not cross or len(state[di]) == 3):
                    continue
                if di == ri and dj in (ei, (ei + 1) % len(state[ri])):
                    continue
                brute.append((a+b, di, dj, ri, ei, xy))
        found, counts = candidates_for_method(p.dense, p.ref_masks, state, p.render, m, engine.CFG)
        assert found == sorted(brute)[:24] and len(brute) == counts["eligible_pairs"]
        if triangle:
            # Test triangle availability without being truncated away by better cross moves.
            tri, _ = candidates_for_method(p.dense[:1], p.ref_masks[:1], state[:1], p.render, m, engine.CFG)
            assert tri and all(len(replace_vertex(state[:1], *v[1:])[0]) == 3 for v in tri)
        assert all(di == ri or len(state[di]) > 3 for _, di, _, ri, _, _ in found)


    # One source rectangle, one deliberately thin but valid triangle. The opposite
    # edge receives a new point and the result remains a legal three-vertex file.
    rect = np.zeros((12, 20), np.uint8)
    rect[2:10, 2:18] = 1
    prep = prepare_input(rect, 26)
    state = [prep.dense[0][[0, 1, 2]]]
    updated, step = engine.exchange_step(rect, prep, state, "within_full")
    assert step["accepted"] and step["triangle"] and not step["cross"]
    assert len(pack(rect.shape, updated, prep.parents)) == 26
    assert (step["xor_before"],step["xor_after"]) == (126,56)
    return dict(before=step["xor_before"], after=step["xor_after"], bytes=26)


def development_checks():
    sources = {r["id"]:r for r in rows(MANIFEST)}
    ref_rows = rows(ROOT/"results/poly03/full/per_image.csv")
    recorded = [r for r in ref_rows if r["method"] == "feasible_add" and int(r["budget"]) == 256]
    count = 0
    for prior in recorded:
        raw = read_mask(sources[prior["id"]])
        event = []
        result = engine.encode(raw, 256, "seed", lambda b,e:event.append(b))
        assert result["status"] == prior["status"]
        if event:
            assert hashlib.sha256(event[0]).hexdigest() == prior["sha256"]
            count += 1
    first = read_mask(next(iter(sources.values())))
    delivered = []
    def receive(blob, e):
        now = time.perf_counter_ns()
        delivered.append((blob, e, (now - e["start_ns"]) / 1e6))
    original = engine.exchange_step
    def after_first_delivery(*args):
        assert delivered, "Consumer must receive the first file before search begins"
        return original(*args)
    with patch.object(engine, "exchange_step", after_first_delivery):
        r = engine.encode(first, 256, "within_full", receive, max_ms=1e6, max_rounds=2)
    assert len(delivered)>1 and all(e["serialized_ms"] <= e["delivered_ms"] <= got <= r["end_ms"] for _,e,got in delivered)
    assert all(delivered[j][2]<delivered[j+1][1]["serialized_ms"] for j in range(len(delivered)-1))
    audit = audit_screen(first, 256, delivered[0][0])
    assert audit["proposed_pairs"] == 24
    # Candidate combination equality tested above; here check an entire two-round historical path.
    old_state, old_status = anytime.init(first, 256)
    dense, par, ren, ref, refs, state = old_state
    for _ in range(2):
        state, action, _, _ = anytime.lazy_step(first,dense,par,ren,ref,refs,state,within=True)
        if action is None: break
    actual=[]
    engine.encode(first,256,"within_old",lambda b,e:actual.append(b),max_ms=1e6,max_rounds=2)
    assert actual[-1]==pack(first.shape,state,par)
    # Preserving the first CGAL vertex and cyclically reversing a backwards ring is enough.
    rev=[np.concatenate([p[:1],p[:0:-1]]) for p in state]
    oriented, mapping, why=engine.forward_subsequence(dense,rev)
    assert why=="ok" and all(m["reversed"] for m in mapping)
    assert np.array_equal(ren.combined(rev),ren.combined(oriented))
    return dict(dev_sources_checked=len(recorded),DP_initial_blobs_identical=count,
                remaining_original_statuses_unchanged=len(recorded)-count,ordinary_old_within_two_rounds_byte_match=True,
                synchronous_delivery_events=len(delivered),exact_supplement_candidates=audit["proposed_pairs"],
                backwards_mapping_pixel_equal=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    args = p.parse_args()
    status = verify_states()
    independent = offline_fixture()
    triangle_witness = candidate_checks()
    report = dict(status_fixtures=status, offline_four_status_fixture=True, offline_empty_files_checked=independent,
                  arbitrary_errors_propagate=True, matched_exhaustive_top24=True, triangle_has_final_same_ring_moves=True,
                  triangle_never_cross_donor=True, actual_tri_replacement=triangle_witness, **development_checks())
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text,encoding="utf-8")
    print(text)


if __name__=="__main__":
    main()
