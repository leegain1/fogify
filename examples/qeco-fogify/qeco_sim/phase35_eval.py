"""Phase 3.5: evaluate the closed-loop QECO models (3 variants x seeds) and the Phase 3
open-loop models on the closed-loop simulator, same conditions as Phase 3 (S1-S3, 1 / 256 KB).

    docker run --rm -u 1000:1000 -v $PWD:/w -w /w/qeco_sim qeco-tf:0.1 python phase35_eval.py

Outputs: results/P35_eval_sim.csv (one row per model, condition, payload),
         results/P35_eval_summary.csv (mean +- std over seeds), results/P35_eval_sim.png
"""
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eval_sim import grid, run
from policies import RULES
from qeco_agent import QecoPolicy

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
NAME = {"orig": "QECO-orig", "net": "QECO-net", "netplus": "QECO-net+"}
SHOWN_RULES = ["Always-Local", "Always-Edge1", "Always-Edge2", "Nearest-Edge", "Model-Greedy"]


def models():
    """(policy name, seed, variant, QecoPolicy). Open-loop trained models are 'QECO-orig (open)'."""
    out = []
    for d in sorted(glob.glob(os.path.join(RES, "P35_*_s[0-9]"))):
        if os.path.exists(os.path.join(d, "model", "checkpoint")):
            q = QecoPolicy(d)
            out.append((NAME[q.meta["variant"]], q.meta["seed"], q.meta["variant"], q))
    for v in ("orig", "net"):   # mismatch group: trained with open-loop arrivals (Phase 3 setup, same physics)
        q = QecoPolicy(os.path.join(RES, f"P35_open_{v}"))
        out.append((f"{NAME[v]} (open)", 0, v, q))
    return out


def main():
    ms = models()
    rows = []
    for scen, name, kb, cond in grid():
        per = {p: run("orig", cond, kb, RULES[p], arrival="closed") for p in RULES}
        fixed = np.vstack([per["Always-Local"][0], per["Always-Edge1"][0], per["Always-Edge2"][0]])
        opt = fixed.min(axis=0)
        res = [(p, 0, per[p]) for p in RULES] + [("Offline-Opt", 0, (opt, fixed.argmin(axis=0)))]
        for pol, seed, v, q in ms:
            res.append((pol, seed, run(v, cond, kb, None, q, arrival="closed")))
        for pol, seed, (tct, act) in res:
            rows.append({"scenario": scen, "condition": name, "payload_kb": kb, "policy": pol, "seed": seed,
                         "tct_mean": tct.mean(), "tct_p50": np.median(tct), "tct_p95": np.percentile(tct, 95),
                         "regret": tct.mean() - opt.mean(), "share_local": (act == 0).mean(),
                         "share_e1": (act == 1).mean(), "share_e2": (act == 2).mean()})
        print(scen, name, kb, flush=True)
    df = pd.DataFrame(rows).round(3)
    df.to_csv(os.path.join(RES, "P35_eval_sim.csv"), index=False)

    # per model (policy, seed): average regret over S1-S3; then mean / std over seeds
    per_seed = df.groupby(["policy", "seed", "payload_kb"]).agg(
        regret=("regret", "mean"), share_local=("share_local", "mean")).reset_index()
    acts = df.groupby(["policy", "seed"])[["share_local", "share_e1", "share_e2"]].mean().max(axis=1)
    per_seed["one_action"] = per_seed.apply(lambda r: acts[(r.policy, r.seed)] >= 0.98, axis=1)
    mid = df[df.condition.isin(["RTT 55", "RTT 105"])].groupby(["policy", "seed", "payload_kb"]).regret.mean()
    per_seed["regret_rtt55_105"] = per_seed.apply(lambda r: mid[(r.policy, r.seed, r.payload_kb)], axis=1)
    per_seed.to_csv(os.path.join(RES, "P35_eval_per_seed.csv"), index=False)
    summ = per_seed.groupby(["policy", "payload_kb"]).agg(
        regret_mean=("regret", "mean"), regret_std=("regret", "std"),
        mid_mean=("regret_rtt55_105", "mean"), mid_std=("regret_rtt55_105", "std"),
        n_seeds=("seed", "size"), one_action_seeds=("one_action", "sum")).round(1).reset_index()
    summ.to_csv(os.path.join(RES, "P35_eval_summary.csv"), index=False)
    print(summ.to_string())

    order = SHOWN_RULES + ["QECO-orig (open)", "QECO-net (open)", "QECO-orig", "QECO-net", "QECO-net+"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, kb in zip(axes, (1.0, 256.0)):
        s = summ[summ.payload_kb == kb].set_index("policy").reindex(order)
        ax.barh(s.index, s.regret_mean, xerr=s.regret_std.fillna(0), capsize=3,
                color=["tab:orange" if p.startswith("QECO") else "tab:blue" for p in s.index])
        ax.set_title(f"payload {kb:.0f} KB"); ax.set_xlabel("mean regret vs Offline-Opt (ms), S1-S3 avg")
        ax.grid(axis="x", alpha=0.3); ax.invert_yaxis()
    fig.suptitle("Simulator, closed loop (idle gap mean 200 ms, 90 tasks per condition), QECO: mean +- std over seeds")
    plt.tight_layout(); plt.savefig(os.path.join(RES, "P35_eval_sim.png"), dpi=110)


if __name__ == "__main__":
    main()
