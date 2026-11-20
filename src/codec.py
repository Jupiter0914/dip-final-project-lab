"""Binary integer polygon format, exact OpenCV rasterizer and geometric validity."""
from functools import lru_cache
import struct

import cv2
import numpy as np

HEADER = struct.Struct("<4sHHH")


def silhouette(trimap):
    """Largest exterior of definite foreground (Oxford label 1), filled at native size."""
    binary = np.ascontiguousarray(trimap == 1, dtype=np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError("No definite foreground")
    outline = max(contours, key=cv2.contourArea).reshape(-1, 2)
    mask = np.zeros_like(binary)
    cv2.drawContours(mask, [outline], -1, 1, cv2.FILLED, cv2.LINE_8)
    if len(outline) < 32 or cv2.contourArea(outline) < 1:
        raise ValueError("Insufficient contour for the requested budgets")
    return mask, outline, dict(components=len(contours), definite_pixels=int(binary.sum()),
                               standardized_difference=cv2.countNonZero(cv2.bitwise_xor(mask,binary)))


def paint(shape, vertices):
    out = np.zeros(shape, np.uint8)
    cv2.fillPoly(out, [np.asarray(vertices, np.int32)], 1, lineType=cv2.LINE_8)
    return out


def cross(a, b):
    return a[..., 0]*b[..., 1] - a[..., 1]*b[..., 0]


@lru_cache(maxsize=64)
def edge_pairs(k):
    i, j = np.triu_indices(k, 2)
    return i[(j-i) < k-1], j[(j-i) < k-1]


def simple(vertices):
    """Exact integer tests including touches between non-adjacent edges."""
    p = np.asarray(vertices, np.int64)
    nxt = np.roll(p, -1, axis=0)
    d = nxt - p
    if (np.all(d == 0, axis=1)).any() or np.sum(cross(p,nxt)) == 0:
        return False
    prev = np.roll(d, 1, axis=0)
    if ((cross(prev,d) == 0) & ((prev*d).sum(axis=1) < 0)).any():
        return False
    i, j = edge_pairs(len(p))
    a, b, c, e = p[i], nxt[i], p[j], nxt[j]
    overlap = np.all(np.maximum(np.minimum(a,b),np.minimum(c,e)) <=
                     np.minimum(np.maximum(a,b),np.maximum(c,e)), axis=1)
    # Sign comparisons avoid overflow from multiplying large cross products.
    s1, s2 = np.sign(cross(b-a,c-a)), np.sign(cross(b-a,e-a))
    s3, s4 = np.sign(cross(e-c,a-c)), np.sign(cross(e-c,b-c))
    return not (overlap & (s1*s2 <= 0) & (s3*s4 <= 0)).any()


def encode(shape, vertices):
    h, w = shape
    p = np.asarray(vertices)
    if p.ndim != 2 or p.shape[1] != 2 or not np.issubdtype(p.dtype, np.integer):
        raise ValueError("Integer (x,y) coordinates required")
    if not (0 < w <= 65535 and 0 < h <= 65535 and 3 <= len(p) <= 65535):
        raise ValueError("Invalid canvas or vertex count")
    if np.any(p < 0) or np.any(p >= [w,h]) or not simple(p):
        raise ValueError("Invalid polygon")
    return HEADER.pack(b"POL1",w,h,len(p)) + p.astype("<u2").tobytes()


def decode(blob):
    magic, w, h, k = HEADER.unpack_from(blob)
    if magic != b"POL1" or len(blob) != HEADER.size + 4*k:
        raise ValueError("Invalid polygon byte stream")
    p = np.frombuffer(blob, "<u2", offset=HEADER.size).reshape(k,2).astype(np.int32)
    if encode((h,w),p) != blob:
        raise ValueError("Noncanonical polygon")
    return paint((h,w),p)
