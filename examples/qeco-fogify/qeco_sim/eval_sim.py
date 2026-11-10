"""Evaluate trained QECO models and rule policies in the simulator on fixed
conditions that mirror the Phase 5 scenarios (S1-S3), random arrivals (same
sequence and CFS phase for every policy). A fixed 300 ms gap would lock the task
start to one position in the 100 ms CFS period, so local TCT would depend on luck.

    docker run --rm -u 1000:1000 -v $PWD:/w -w /w/qeco_sim qeco-tf:0.1 python eval_sim.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mec_env import TestbedMEC
from policies import RULES
from qeco_agent import QecoPolicy

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
N_SLOTS, ARRIVE_PROB = 3000, 0.03   # 30 s episode, random arrivals (mean gap ~330 ms) -> ~90 tasks per condition


def grid():
    for kb in (1.0, 256.0):
        for rtt in (10, 30, 55, 105, 205):
            yield "S1", f"RTT {rtt}", kb, [{"rtt": rtt, "bw": 100, "load": 0}] * 2
        for bw in (100, 10, 1):
            yield "S2", f"BW {bw}", kb, [{"rtt": 10, "bw": bw, "load": 0}] * 2
        for load in (0, 0.3, 0.6, 0.8):
            yield "S3", f"E1 load {load}", kb, [{"rtt": 10, "bw": 100, "load": load}, {"rtt": 50, "bw": 100, "load": 0}]


def run(variant, cond, kb, decide, qeco=None, seed=0):
    env = TestbedMEC(variant=variant, n_slots=N_SLOTS, seed=seed)
    obs, lstm = env.reset(conditions=cond, payloads=np.full(N_SLOTS, kb), arrivals=np.random.default_rng(seed + 123).random(N_SLOTS) < ARRIVE_PROB)
    if qeco:
        qeco.reset()
    done = False
    while not done:
        if obs.sum() == 0:
            a = 0
        else:
            a = qeco.act(obs) if qeco else decide(env.cond, env.iter, kb)
        obs, lstm, done = env.step(a)
        if qeco:
            qeco.update_lstm(lstm)
    s = np.where(env.arrive_kb > 0)[0]
    return env.process_delay[s], env.task_action[s]


def main():
    import sys
    # default: results/P3_orig, results/P3_net; or pass run dirs (variant read from meta.json)
    dirs = sys.argv[1:] or [os.path.join(RES, f"P3_{v}") for v in ("orig", "net")]
    models = {}
    for d in dirs:
        q = QecoPolicy(d)
        models[f"QECO-{q.meta['variant']}" if not sys.argv[1:] else os.path.basename(d.rstrip("/"))] = (q.meta["variant"], q)
    rows = []
    for scen, name, kb, cond in grid():
        per = {}
        for pol, fn in RULES.items():
            per[pol] = run("orig", cond, kb, fn)
        for pol, (v, q) in models.items():
            per[pol] = run(v, cond, kb, None, q)
        # Oracle: per task, the best of the three fixed locations (same arrivals and CFS phase)
        fixed = np.vstack([per["Always-Local"][0], per["Always-Edge1"][0], per["Always-Edge2"][0]])
        per["Oracle"] = (fixed.min(axis=0), fixed.argmin(axis=0))
        for pol, (tct, act) in per.items():
            rows.append({"scenario": scen, "condition": name, "payload_kb": kb, "policy": pol,
                         "tct_p50": np.median(tct), "tct_p95": np.percentile(tct, 95), "tct_mean": tct.mean(),
                         "regret_mean": tct.mean() - per["Oracle"][0].mean(),
                         "share_local": (act == 0).mean(), "share_e1": (act == 1).mean(), "share_e2": (act == 2).mean()})
    df = pd.DataFrame(rows).round(2)
    if sys.argv[1:]:
        print(df.groupby(["payload_kb", "policy"])[["tct_mean", "regret_mean"]].mean().round(1).unstack(0).to_string())
        return
    df.to_csv(os.path.join(RES, "P3_eval_sim.csv"), index=False)

    summary = df.groupby(["payload_kb", "policy"])[["tct_mean", "regret_mean"]].mean().round(1).unstack(0)
    print(summary.to_string())
    summary.to_csv(os.path.join(RES, "P3_eval_sim_summary.csv"))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, kb in zip(axes, (1.0, 256.0)):
        piv = df[df.payload_kb == kb].pivot_table(index="policy", values="regret_mean", aggfunc="mean").sort_values("regret_mean")
        piv.plot.barh(ax=ax, legend=False)
        ax.set_title(f"payload {kb:.0f} KB"); ax.set_xlabel("mean regret vs Oracle (ms), S1-S3 avg"); ax.grid(axis="x", alpha=0.3)
    fig.suptitle("Simulator evaluation (fixed conditions, random arrivals ~1 task / 330 ms)")
    plt.tight_layout(); plt.savefig(os.path.join(RES, "P3_eval_sim.png"), dpi=110)


if __name__ == "__main__":
    main()
