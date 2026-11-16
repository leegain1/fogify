"""Phase 5 analysis: tables, regret vs Offline-Opt, simulator vs testbed, S3 inversion, S4.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase5_analyze.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import driver as dr
from phase5 import models
from testbed_model import edge_tct_ms  # noqa: E402  (qeco_sim is on sys.path via driver)

R = "results"
FIXED = dr.FIXED
ORDER = ["Always-Local", "Always-Edge1", "Always-Edge2", "Nearest-Edge", "Model-Greedy",
         "QECO-orig (open)", "QECO-net (open)", "QECO-orig", "QECO-net", "QECO-net+", "Offline-Opt"]
COLORS = {p: c for p, c in zip(ORDER, plt.cm.tab20(np.linspace(0, 1, len(ORDER))))}


def stats(g):
    return pd.Series({"p50": g.tct_ms.median(), "p95": g.tct_ms.quantile(0.95), "mean": g.tct_ms.mean(),
                      "n": len(g), "local": (g.action == 0).mean(), "e1": (g.action == 1).mean(),
                      "e2": (g.action == 2).mean(), "decide_ms": g.decide_ms.median(),
                      "errors": (g.status != "ok").sum()})


def static_tables():
    df = pd.read_csv(f"{R}/P5_runs.csv")
    df = df[df.status == "ok"]
    opt = dr.offline_opt(df)
    meta = df.drop_duplicates("label").set_index("label")[["scenario", "condition", "payload_kb"]]
    opt = opt.drop(columns=[c for c in ("scenario", "condition") if c in opt]).join(meta[["scenario", "condition"]], on="label")
    df = pd.concat([df, opt], ignore_index=True)
    key = ["scenario", "condition", "payload_kb"]
    tab = df.groupby(key + ["policy"]).apply(stats).reset_index()
    o = tab[tab.policy == "Offline-Opt"].set_index(key)["mean"]
    tab["regret"] = tab.apply(lambda r: r["mean"] - o[tuple(r[k] for k in key)], axis=1)
    tab = tab.round(2)
    tab.to_csv(f"{R}/P5_table.csv", index=False)

    summ = tab.groupby(["policy", "payload_kb"]).regret.mean().unstack().reindex(ORDER).round(1)
    by_s = tab.groupby(["scenario", "policy", "payload_kb"]).regret.mean().unstack([0, 2]).reindex(ORDER).round(1)
    summ.to_csv(f"{R}/P5_regret_summary.csv")
    by_s.to_csv(f"{R}/P5_regret_by_scenario.csv")
    print("mean regret (ms) over S1-S3 conditions\n", summ.to_string())
    print(by_s.to_string())

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, kb in zip(axes, (1, 256)):
        s = summ[kb].drop("Offline-Opt")
        ax.barh(s.index, s.values, color=[COLORS[p] for p in s.index])
        ax.set_title(f"payload {kb} KB"); ax.set_xlabel("mean regret vs Offline-Opt (ms), S1-S3")
        ax.grid(axis="x", alpha=0.3); ax.invert_yaxis()
    fig.suptitle("Fogify: mean regret over S1-S3 conditions (n = 30 per condition)")
    plt.tight_layout(); plt.savefig(f"{R}/P5_regret.png", dpi=110)

    # per condition TCT p50 / p95, per scenario and payload
    fig, axes = plt.subplots(2, 3, figsize=(18, 9))
    for i, kb in enumerate((1, 256)):
        for j, scen in enumerate(("S1", "S2", "S3")):
            ax = axes[i, j]
            t = tab[(tab.payload_kb == kb) & (tab.scenario == scen)]
            conds = list(dict.fromkeys(df[df.scenario == scen].condition))
            x = np.arange(len(conds))
            for p in ORDER:
                y = t[t.policy == p].set_index("condition").reindex(conds)
                ax.plot(x, y.p50, marker="o", ms=3, color=COLORS[p], label=p,
                        lw=2.5 if p in ("Offline-Opt", "QECO-net+") else 1)
            ax.set_xticks(x); ax.set_xticklabels(conds, fontsize=8); ax.set_yscale("log")
            ax.set_title(f"{scen}, {kb} KB: TCT p50 (ms)"); ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=7, ncol=2)
    plt.tight_layout(); plt.savefig(f"{R}/P5_tct.png", dpi=110)
    return df, tab


def sim_vs_testbed(tab):
    """Simulator (closed loop, Phase 3.5 eval) vs Fogify mean TCT for the same policy and condition."""
    sim = pd.read_csv(f"{R}/P35_eval_sim.csv")
    m = models()
    chosen = {n: int(d.split("_s")[1]) for n, (v, d) in m.items() if "_s" in d}
    sim = sim[sim.apply(lambda r: r.policy not in chosen or r.seed == chosen[r.policy], axis=1)]
    sim["condition"] = sim.condition.str.replace(r"E1 load (0\.\d+|0)$",
                                                 lambda mo: f"E1 load {round(float(mo.group(1)) * 100)}", regex=True)
    j = tab.merge(sim[["scenario", "condition", "payload_kb", "policy", "tct_mean", "share_local"]],
                  on=["scenario", "condition", "payload_kb", "policy"], how="inner")
    j = j.rename(columns={"mean": "testbed_mean", "tct_mean": "sim_mean", "local": "testbed_local",
                          "share_local": "sim_local"})
    j["diff_ms"] = j.testbed_mean - j.sim_mean
    j["diff_pct"] = 100 * j.diff_ms / j.sim_mean
    j = j.round(2)
    j.to_csv(f"{R}/P5_sim_vs_testbed.csv", index=False)
    s = j.groupby("policy").agg(mean_abs_diff_ms=("diff_ms", lambda x: x.abs().mean()),
                                mean_diff_ms=("diff_ms", "mean"), mean_abs_pct=("diff_pct", lambda x: x.abs().mean()),
                                local_share_gap=("testbed_local", "mean")).round(1)
    s["local_share_sim"] = j.groupby("policy").sim_local.mean().round(2)
    s = s.reindex([p for p in ORDER if p in s.index])
    s.to_csv(f"{R}/P5_sim_vs_testbed_summary.csv")
    print("simulator vs testbed\n", s.to_string())

    fig, ax = plt.subplots(figsize=(6, 6))
    for p in s.index:
        g = j[j.policy == p]
        ax.scatter(g.sim_mean, g.testbed_mean, s=14, color=COLORS[p], label=p)
    lim = [50, max(j.sim_mean.max(), j.testbed_mean.max()) * 1.1]
    ax.plot(lim, lim, "k:", lw=1); ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("simulator mean TCT (ms)"); ax.set_ylabel("Fogify mean TCT (ms)")
    ax.set_title("simulator prediction vs Fogify (S1-S3, 1 / 256 KB)"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(f"{R}/P5_sim_vs_testbed.png", dpi=110)
    return j


def s3_inversion(df, tab):
    """S3: edge-server-1 (RTT 10, load L) vs edge-server-2 (RTT 50, idle) vs local."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5))
    loads = sorted(int(c.rsplit(" ", 1)[1]) for c in tab[tab.scenario == "S3"].condition.unique())
    out = []
    for c, kb in enumerate((1, 256)):
        ax = axes[0, c]
        t = tab[(tab.scenario == "S3") & (tab.payload_kb == kb)].copy()
        t["load"] = t.condition.str.extract(r"(\d+)$").astype(int)
        for p, mk in (("Always-Local", "s"), ("Always-Edge1", "o"), ("Always-Edge2", "^"), ("Offline-Opt", "x")):
            g = t[t.policy == p].sort_values("load")
            ax.plot(g.load, g["mean"], marker=mk, color=COLORS[p], label=f"{p} (mean)")
            if p != "Offline-Opt":
                ax.fill_between(g.load, g.p50, g.p95, color=COLORS[p], alpha=0.12)
        xs = np.linspace(0, 85, 86)
        e1 = [edge_tct_ms(1_000_000, kb, 10.5, 100, x / 100) for x in xs]
        e2 = edge_tct_ms(1_000_000, kb, 50.5, 100, 0)
        ax.plot(xs, e1, "--", color=COLORS["Always-Edge1"], lw=1, label="model: edge-server-1")
        ax.axhline(e2, ls="--", color=COLORS["Always-Edge2"], lw=1, label="model: edge-server-2")
        cross_model = next((x for x, y in zip(xs, e1) if y > e2), None)
        g1 = t[t.policy == "Always-Edge1"].set_index("load")["mean"]
        g2 = t[t.policy == "Always-Edge2"].set_index("load")["mean"]
        d = (g1 - g2).reindex(loads)
        cross = None
        for a, b in zip(loads, loads[1:]):     # linear interpolation of the sign change
            if d[a] <= 0 < d[b]:
                cross = a + (b - a) * (-d[a]) / (d[b] - d[a])
        if cross is not None:
            ax.axvline(cross, color="k", lw=1, ls=":")
            ax.text(cross, ax.get_ylim()[1] * 0.95, f" measured {cross:.0f}%", fontsize=8, va="top")
        out.append({"payload_kb": kb, "inversion_load_measured_pct": None if cross is None else round(cross, 1),
                    "inversion_load_model_pct": cross_model})
        ax.set_xlabel("edge-server-1 CPU load (%)"); ax.set_ylabel("TCT (ms), band p50-p95")
        ax.set_title(f"S3, {kb} KB: edge-server-1 (RTT 10) vs edge-server-2 (RTT 50)")
        ax.grid(alpha=0.3); ax.legend(fontsize=7)
        # which location each policy picked
        ax = axes[1, c]
        pols = ["Nearest-Edge", "Model-Greedy", "QECO-net (open)", "QECO-net", "QECO-net+", "Offline-Opt"]
        w = 0.13
        for i, p in enumerate(pols):
            g = t[t.policy == p].set_index("load").reindex(loads)
            x = np.arange(len(loads)) + (i - len(pols) / 2) * w
            ax.bar(x, g.local, w, color="tab:gray")
            ax.bar(x, g.e1, w, bottom=g.local, color="tab:red")
            ax.bar(x, g.e2, w, bottom=g.local + g.e1, color="tab:blue")
            for xi in x:
                ax.text(xi, 1.02, str(i + 1), ha="center", fontsize=7)
        ax.set_xticks(range(len(loads))); ax.set_xticklabels([f"{l}%" for l in loads]); ax.set_ylim(0, 1.12)
        ax.set_title(f"S3, {kb} KB: choice share (gray local, red E1, blue E2)", fontsize=9)
        ax.set_xlabel("edge-server-1 CPU load   |   " + ", ".join(f"{i + 1}={p}" for i, p in enumerate(pols)), fontsize=7)
    plt.tight_layout(); plt.savefig(f"{R}/P5_s3_inversion.png", dpi=110)
    pd.DataFrame(out).to_csv(f"{R}/P5_s3_inversion.csv", index=False)
    print(pd.DataFrame(out).to_string())


def s4():
    if not os.path.exists(f"{R}/P5_s4.csv"):
        return
    df = pd.read_csv(f"{R}/P5_s4.csv")
    df = df[df.status == "ok"]
    # Offline-Opt per segment: k-th task of the segment, min over the three Always-* runs
    df["k"] = df.groupby(["policy", "segment"]).cumcount()
    fx = df[df.policy.isin(FIXED)].pivot_table(index=["segment", "k"], columns="policy", values="tct_ms").dropna()
    opt = fx.min(axis=1).rename("tct_ms").reset_index().assign(policy="Offline-Opt")
    allp = pd.concat([df, opt], ignore_index=True)
    seg = allp.groupby(["segment", "policy"]).tct_ms.agg(["mean", "median", "size"]).reset_index()
    o = seg[seg.policy == "Offline-Opt"].set_index("segment")["mean"]
    seg["regret"] = seg["mean"] - seg.segment.map(o)
    seg.round(2).to_csv(f"{R}/P5_s4_segments.csv", index=False)
    tot = seg.groupby("policy").regret.mean().reindex(ORDER).dropna().round(1)
    tot.to_csv(f"{R}/P5_s4_regret.csv")
    print("S4 mean regret over segments\n", tot.to_string())
    fig, ax = plt.subplots(2, 1, figsize=(12, 8))
    for p in ORDER:
        g = df[df.policy == p]
        if len(g):
            ax[0].plot(g.t_s, g.tct_ms.rolling(5, min_periods=1).median(), color=COLORS[p], label=p,
                       lw=2 if p == "QECO-net+" else 1)
    from phase5 import S4_SEGMENT_S, S4_TIMELINE
    starts = df.groupby("segment").t_s.min()   # actual segment starts (changes take ~2 s per link)
    for i, (a, b) in enumerate(S4_TIMELINE):
        x0 = starts.get(i, i * S4_SEGMENT_S)
        ax[0].axvline(x0, color="k", lw=0.5)
        ax[0].text(x0 + 1, ax[0].get_ylim()[1], f"E1 {a[0]}ms/{a[1]}M/{a[2]}%\nE2 {b[0]}ms", fontsize=7, va="top")
    ax[0].set_yscale("log"); ax[0].set_ylabel("TCT (ms), rolling median of 5"); ax[0].legend(fontsize=7, ncol=3)
    ax[0].set_xlabel("time (s)"); ax[0].grid(alpha=0.3)
    ax[1].barh(tot.index, tot.values, color=[COLORS[p] for p in tot.index]); ax[1].invert_yaxis()
    ax[1].set_xlabel("S4 mean regret vs Offline-Opt over 6 segments (ms)"); ax[1].grid(axis="x", alpha=0.3)
    plt.tight_layout(); plt.savefig(f"{R}/P5_s4.png", dpi=110)


if __name__ == "__main__":
    df, tab = static_tables()
    sim_vs_testbed(tab)
    s3_inversion(df, tab)
    s4()
