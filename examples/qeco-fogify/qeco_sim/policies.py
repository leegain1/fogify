"""Rule / model-based offloading policies (no TensorFlow), shared by the simulator
evaluation and the Fogify driver. Action: 0 = local, 1 = edge-server-1, 2 = edge-server-2.

cond: list of {"rtt": ms, "bw": Mbit, "load": 0..1} per edge server (observed state).
"""
from testbed_model import edge_tct_ms, local_tct_fluid_ms

ACTIONS = ["local", "edge-server-1", "edge-server-2"]


def always_local(cond, iter, kb):
    return 0


def always_edge1(cond, iter, kb):
    return 1


def always_edge2(cond, iter, kb):
    return 2


def nearest_edge(cond, iter, kb):
    """Rule: the edge server with the smallest RTT (ignores load and bandwidth)."""
    return 1 + min(range(len(cond)), key=lambda i: cond[i]["rtt"])


def model_greedy_estimates(cond, iter, kb):
    """T_local (fluid formula) and T_edge,i = T_comp(L_i) + RTT_i + D/B_i + overhead."""
    return [local_tct_fluid_ms(iter)] + [edge_tct_ms(iter, kb, c["rtt"], c["bw"], c["load"]) for c in cond]


def model_greedy(cond, iter, kb):
    est = model_greedy_estimates(cond, iter, kb)
    return min(range(len(est)), key=est.__getitem__)


RULES = {"Always-Local": always_local, "Always-Edge1": always_edge1, "Always-Edge2": always_edge2,
         "Nearest-Edge": nearest_edge, "Model-Greedy": model_greedy}
