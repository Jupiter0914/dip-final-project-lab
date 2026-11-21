"""Native-grid, identity-matched region diagnostics outside the encoding clock."""
from dataclasses import dataclass
import numpy as np
from scipy import ndimage

from poly03.full_verify import parse, paint, expected_tree
from poly03.maskcodec import supported_shape
from .prepare import prepare_input

FOUR = ndimage.generate_binary_structure(2, 1)
EIGHT = np.ones((3, 3), dtype=bool)


def _binary_issue(image):
    if not supported_shape(image.shape):
        return "outside_coordinate_or_implementation_canvas_limit"
    if np.any((image != 0) & (image != 1)):
        return "expected_binary_samples"
    return None


def _box_plus_one(box, shape):
    return tuple(slice(max(0, s.start - 1), min(n, s.stop + 1))
                 for s, n in zip(box, shape))


@dataclass
class Labels:
    labels: np.ndarray
    areas: np.ndarray
    boxes: list
    ids: range

    @classmethod
    def make(cls, mask, connectivity, first):
        labels, n = ndimage.label(mask, connectivity)
        areas = np.bincount(labels.ravel(), minlength=n + 1)
        return cls(labels, areas, ndimage.find_objects(labels, max_label=n), range(first, n + 1))


class Layout:
    def __init__(self, raw):
        pad = np.pad(raw.astype(bool, copy=False), 1)
        self.fg = Labels.make(pad, EIGHT, 1)
        self.bg = Labels.make(~pad, FOUR, 2)
        if self.bg.labels[0, 0] != 1:
            raise RuntimeError("Unexpected exterior label")

    def adjacency(self):
        pairs = set()
        for i in self.fg.ids:
            box = _box_plus_one(self.fg.boxes[i - 1], self.fg.labels.shape)
            near = ndimage.binary_dilation(self.fg.labels[box] == i, structure=FOUR)
            pairs.update((i, int(j)) for j in np.unique(self.bg.labels[box][near]) if j)
        return pairs


def _match(ref, pred, kind):
    if len(ref.ids) != len(pred.ids):
        return None, []
    mapping, seen, rows = {}, set(), []
    for i in ref.ids:
        box = ref.boxes[i - 1]
        overlap = pred.labels[box][ref.labels[box] == i]
        labels, counts = np.unique(overlap[overlap >= pred.ids.start], return_counts=True)
        if len(labels) != 1:
            return None, []
        j, hit = int(labels[0]), int(counts[0])
        source_area, out_area = int(ref.areas[i]), int(pred.areas[j])
        if j in seen or 2 * hit < min(source_area, out_area):
            return None, []
        mapping[i] = j
        seen.add(j)
        rows.append(dict(kind=kind, reference_id=i, decoded_id=j, reference_area=source_area,
                         decoded_area=out_area, intersection=hit, recall=hit / source_area,
                         precision=hit / out_area, area_ratio=out_area / source_area,
                         iou=hit / (source_area + out_area - hit)))
    return mapping, rows


def independent_decode(blob,expected_parents=None):
    """Parse PM31 and paint each ring via drawContours rather than the production fillPoly."""
    shape, polygons, parent = parse(blob)
    if not supported_shape(shape):
        raise ValueError("Decoded canvas exceeds implementation limit")
    if expected_parents is not None and list(parent)!=list(expected_parents):
        raise ValueError("Decoded vector roles differ from the original rings")
    if not expected_tree(polygons, parent):
        raise ValueError("Invalid encoded vector geometry")
    out = np.zeros(shape, np.uint8)
    for polygon in polygons:
        np.bitwise_xor(out, paint(shape, polygon), out=out)
    return out


class RegionReference:
    """Cache one reference's two label maps; the caller can cache outputs by (source, SHA)."""
    def __init__(self, raw, preparation=None):
        checked = prepare_input(raw) if preparation is None else preparation
        self.issue = checked.reason if checked.status == "unsupported_representation" else None
        self.parents = checked.parents
        ref = np.asarray(raw)
        self.shape = ref.shape
        self.layout = None if self.issue else Layout(ref)
        self.adjacency = None if self.issue else self.layout.adjacency()

    def evaluate(self, predicted):
        if self.issue:
            return dict(status="unsupported_representation", reason=self.issue, components=[])
        pred = np.asarray(predicted)
        if pred.shape != self.shape or _binary_issue(pred):
            raise ValueError("Prediction is not a binary mask on the reference canvas")
        out = Layout(pred)
        ref = self.layout
        if len(ref.fg.ids) != len(out.fg.ids) or len(ref.bg.ids) != len(out.bg.ids):
            return dict(status="search_no_valid_output", reason="digital_counts", components=[])
        fm, fg = _match(ref.fg, out.fg, "foreground")
        hm, holes = _match(ref.bg, out.bg, "hole")
        if fm is None or hm is None:
            return dict(status="search_no_valid_output", reason="digital_overlap", components=[])
        hm[1] = 1
        if {(fm[i], hm[j]) for i, j in self.adjacency} != out.adjacency():
            return dict(status="search_no_valid_output", reason="digital_adjacency", components=[])
        return dict(status="success", reason="ok", components=fg + holes)

    def evaluate_blob(self, blob):
        if self.issue:
            return dict(status="unsupported_representation", reason=self.issue, components=[])
        return self.evaluate(independent_decode(blob,self.parents))
