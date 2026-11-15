"""Task arrival process shared by the simulator (mec_env.py, arrival="closed") and
the Fogify driver (driver.run_policy), so both see the same kind of workload.

Closed loop: the next task is created only after the previous one has finished,
after an idle gap drawn from an exponential distribution (mean 200 ms), like a
real-time app that sends the next frame when the previous result is back.
"""
import numpy as np

GAP_MEAN_MS = 200.0


def draw_gap_ms(rng, mean_ms=GAP_MEAN_MS):
    """One idle gap (ms) between the end of a task and the start of the next one."""
    return float(rng.exponential(mean_ms)) if mean_ms > 0 else 0.0


def gap_sequence_ms(seed, n, mean_ms=GAP_MEAN_MS):
    """n gaps from a seeded generator: same seed -> same sequence for every policy."""
    rng = np.random.default_rng(seed)
    return np.array([draw_gap_ms(rng, mean_ms) for _ in range(n)])
