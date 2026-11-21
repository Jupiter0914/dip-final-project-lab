"""Atomic deletion and insertion using indices in the original rings."""
from operator import index
import numpy as np


def replace_vertex(rings, donor_ring, donor_index, recipient_ring, edge_index, xy):
    """Return new rings. Insert after the start of the original recipient edge.

    Edges incident to the removed point cannot receive the vertex. Every result
    must still be rasterized and checked against the caller's structural rules.
    Untouched ring arrays are shared; the operation does not mutate any input.
    """
    try:
        donor_ring, donor_index, recipient_ring, edge_index = map(
            index, (donor_ring, donor_index, recipient_ring, edge_index))
    except TypeError as exc:
        raise ValueError("Ring and vertex indices must be integers") from exc
    if not (0 <= donor_ring < len(rings) and 0 <= recipient_ring < len(rings)):
        raise ValueError("Ring index outside input")
    donor, receiver = np.asarray(rings[donor_ring]), np.asarray(rings[recipient_ring])
    if not (0 <= donor_index < len(donor) and 0 <= edge_index < len(receiver)):
        raise ValueError("Vertex or edge index outside input")
    if donor_ring == recipient_ring and donor_index in (edge_index, (edge_index + 1) % len(donor)):
        raise ValueError("The receiving edge is incident to the removed vertex")
    if donor_ring != recipient_ring and len(donor) <= 3:
        raise ValueError("Cross-ring transfer would leave fewer than three vertices")
    pt = np.asarray(xy)
    if pt.shape != (2,) or not np.issubdtype(pt.dtype, np.integer):
        raise ValueError("Expected one integer coordinate pair")
    result = list(rings)
    reduced = np.delete(donor, donor_index, axis=0)
    if donor_ring == recipient_ring:
        receiver = reduced
        edge_index -= int(donor_index < edge_index)
    result[donor_ring] = reduced
    result[recipient_ring] = np.insert(receiver, edge_index + 1, pt, axis=0)
    return result
