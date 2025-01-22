import math
from typing import List

import numpy as np


def cosine_distance(a: List[float], b: List[float]):
    """
    cosine_distance calculates the cosine distance between two vectors, which
    are assumed to be a 1-d array of floats. Returns 1.0 if either vector is
    all zeros.
    """
    # Convert the vectors to ensure 1D shapes
    a = np.array(a).flatten()
    b = np.array(b).flatten()

    uv = np.dot(a, b)
    uu = np.dot(a, a)
    vv = np.dot(b, b)

    # Possible (but unlikely) division by zero protection
    if uu == 0 or vv == 0:
        return 1.0

    dist = uv / math.sqrt(uu * vv)

    return np.clip(dist, 0.0, 2.0)
