"""Testbed physics shared by the simulator (mec_env.py), Model-Greedy and the
sim-vs-testbed comparison. Units: ms, KB, Mbit/s.

Calibrated on Phase 1 (pinned cores, iter = 1M, RTT ~10 ms, 100Mbit, n = 30):
  edge server compute (server_compute_ms) p50 67.7 ms on one E-core (tasks back to back)
  edge server under 80% stress: compute 123.7 ms
  local TCT (0.5 CPU quota): bimodal ~122 / ~177 ms (one or two CFS throttles)
Updated in Phase 4.5 (closed loop, idle gap mean 200 ms, agent):
  edge server compute p50 71.3 ms: after an idle gap the E-core is ~3.6 ms slower
  than back to back (67.7). Phase 1's "overhead 0.9 ms" was RTT measured with ping;
  with the RTT the agent observes (/probe), TCT - compute - RTT = 0.3..0.5 ms.
Updated again in Phase 4.5 after fixing the CPU (host/cpu_perf.sh on: performance governor,
no C6+ on E-cores; E-cores at ~3.1 GHz): edge server compute 72.1 ms with or without an
idle gap (std 0.4 ms, no drift), 124.4 ms under 80% stress, TCT - compute - RTT = 0.15 ms.
Local unchanged (back to back 121 / 170 ms pattern, closed loop mean 97-100 ms).
"""
import math

ITER_REF = 1_000_000
EDGE_WORK_MS = 72.1          # CPU time of one iter=1M task on one E-core (edge server), CPU fixed (Phase 4.5)
# before fixing the CPU: 67.7 back to back, 71.3 after an idle gap, 80-90 in slow periods
LOCAL_WORK_MS = 70.0         # same task on the local node (fitted to the bimodal local TCT, see phase3 doc)
EDGE_OVERHEAD_MS = 0.15      # HTTP + scheduling not covered by RTT / transfer / compute (Phase 4.5; Phase 3: 0.9)
# Docker --cpus 0.2 -> 20 ms per 100 ms period (Phase 3.5: edge server ~5x faster than local;
# Phase 1-4.5: --cpus 0.5 -> 50 ms, edge server only ~1.3x faster)
LOCAL_QUOTA_MS, CFS_PERIOD_MS = 20.0, 100.0
EDGE_CORES = 2               # edge server quota 2.0 CPU; one task uses one core
STRESS_COMPUTE_MS = 124.4    # compute under 80% stress (Phase 4.5, CPU fixed; Phase 1: 123.7)
STRESS_ALPHA = (1 - EDGE_WORK_MS / STRESS_COMPUTE_MS) / 0.8   # speed = 1 - alpha * load (fit at load 0.8)


def edge_speed(load):
    """Relative speed of one task on an edge server with background CPU load in [0, 1)."""
    return max(1.0 - STRESS_ALPHA * load, 0.05)


def transfer_ms(payload_kb, bw_mbit):
    """Serialization time of the request body (the response is a 64-byte hash)."""
    return payload_kb * 1024 * 8 / (bw_mbit * 1000.0)


def edge_tct_ms(iter, payload_kb, rtt_ms, bw_mbit, load):
    """Expected TCT of offloading one task to an idle (no own queue) edge server.
    T = RTT + D/B + T_comp(L) + overhead. TCP slow start is not modeled."""
    comp = EDGE_WORK_MS * iter / ITER_REF / edge_speed(load)
    return rtt_ms + transfer_ms(payload_kb, bw_mbit) + comp + EDGE_OVERHEAD_MS


def local_tct_ms(iter, quota_left_ms=LOCAL_QUOTA_MS, offset_ms=0.0):
    """Local TCT under a CFS quota: run while quota is left in the current period,
    then wait for the next period. offset_ms = position inside the current period."""
    work = LOCAL_WORK_MS * iter / ITER_REF
    t, q, pos = 0.0, quota_left_ms, offset_ms
    while True:
        run = min(work, q, CFS_PERIOD_MS - pos)
        work -= run
        t += run
        pos += run
        q -= run
        if work <= 1e-9:
            return t
        t += CFS_PERIOD_MS - pos      # throttled (or period ended) -> next period
        pos, q = 0.0, LOCAL_QUOTA_MS


def local_tct_fluid_ms(iter):
    """Formula estimate used by Model-Greedy: work / (quota / period) (= 140 ms for iter 1M).
    Ignores CFS throttling granularity, which makes the real TCT bimodal (~120 / ~170)."""
    return LOCAL_WORK_MS * iter / ITER_REF / (LOCAL_QUOTA_MS / CFS_PERIOD_MS)


def back_to_back_local(iter, n):
    """TCTs of n local tasks run back to back (like `uvc-client run -mode local`),
    starting at a period boundary. Reproduces the bimodal distribution."""
    out, pos, q = [], 0.0, LOCAL_QUOTA_MS
    for _ in range(n):
        work = LOCAL_WORK_MS * iter / ITER_REF
        t = 0.0
        while True:
            run = min(work, q, CFS_PERIOD_MS - pos)
            work -= run; t += run; pos += run; q -= run
            if work <= 1e-9:
                break
            t += CFS_PERIOD_MS - pos
            pos, q = 0.0, LOCAL_QUOTA_MS
        out.append(t)
        if pos >= CFS_PERIOD_MS:
            pos, q = 0.0, LOCAL_QUOTA_MS
    return out


if __name__ == "__main__":
    xs = sorted(back_to_back_local(ITER_REF, 30))
    print("local back-to-back:", [round(x) for x in xs])
    print("local fluid:", round(local_tct_fluid_ms(ITER_REF), 1))
    print("edge idle, RTT 10, 100Mbit, 1KB:", round(edge_tct_ms(ITER_REF, 1, 10, 100, 0), 1))
    print("edge load 0.8:", round(edge_tct_ms(ITER_REF, 1, 10, 100, 0.8), 1), "alpha", round(STRESS_ALPHA, 3))
