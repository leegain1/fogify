"""Phase 4.5: simulator (open loop = Phase 3, closed loop = Phase 4.5) vs Fogify on the
base condition (RTT 10.5 ms (observed), 100Mbit, no load, 1 KB), fixed policies and
Offline-Opt. Testbed numbers: results/P45_base_summary.csv (phase45_testbed2.py).

    docker run --rm -u 1000:1000 -v $PWD:/w -w /w/qeco_sim qeco-tf:0.1 python phase45_sim.py
"""
import os

import numpy as np
import pandas as pd

from eval_sim import run
from policies import RULES

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
COND = [{"rtt": 10.5, "bw": 100, "load": 0}] * 2
SEEDS = range(5)

tb = pd.read_csv(os.path.join(RES, "P45_base_summary.csv")).set_index("policy")
rows = []
for arr in ("open", "closed"):
    for seed in SEEDS:
        per = {p: run("orig", COND, 1.0, RULES[p], seed=seed, arrival=arr)[0]
               for p in ("Always-Local", "Always-Edge1", "Always-Edge2")}
        per["Offline-Opt"] = np.vstack(list(per.values())).min(axis=0)
        for p, t in per.items():
            rows.append({"arrival": arr, "seed": seed, "policy": p, "mean": t.mean(),
                         "p50": np.median(t), "p95": np.percentile(t, 95)})
d = pd.DataFrame(rows).groupby(["policy", "arrival"])[["mean", "p50", "p95"]].mean().unstack("arrival")
out = pd.DataFrame({"testbed_mean": tb["mean"], "testbed_p50": tb["p50"], "testbed_p95": tb["p95"],
                    "sim_closed_mean": d[("mean", "closed")], "sim_closed_p50": d[("p50", "closed")],
                    "sim_closed_p95": d[("p95", "closed")], "sim_open_mean": d[("mean", "open")],
                    "sim_open_p95": d[("p95", "open")]}).dropna().round(1)
out.index.name = "policy"
out.to_csv(os.path.join(RES, "P45_sim_check.csv"))
print(out.to_string())
