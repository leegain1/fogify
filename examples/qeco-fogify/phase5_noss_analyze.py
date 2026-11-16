"""256 KB with TCP slow start after idle turned off (docker-compose-noss.yaml) vs on (Phase 5 run).

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase5_noss_analyze.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import driver as dr
from phase5_analyze import ORDER, COLORS, stats
from testbed_model import edge_tct_ms, local_tct_fluid_ms  # noqa: E402

R = "results"
KEY = ["scenario", "condition", "payload_kb"]


def table(path):
    df = pd.read_csv(path)
    df = df[(df.status == "ok") & (df.payload_kb == 256)]
    df = pd.concat([df, dr.offline_opt(df)], ignore_index=True)
    tab = df.groupby(KEY + ["policy"]).apply(stats).reset_index()
    o = tab[tab.policy == "Offline-Opt"].set_index(KEY)["mean"]
    tab["regret"] = tab.apply(lambda r: r["mean"] - o[tuple(r[k] for k in KEY)], axis=1)
    return tab


on, off = table(f"{R}/P5_runs.csv"), table(f"{R}/P5_noss_runs.csv")
both = pd.concat([on.assign(slow_start="on"), off.assign(slow_start="off")]).round(2)
both.to_csv(f"{R}/P5_noss_table.csv", index=False)

reg = both.groupby(["policy", "slow_start", "scenario"]).regret.mean().unstack([1, 2]).reindex(ORDER).round(1)
reg[("on", "all")] = both[both.slow_start == "on"].groupby("policy").regret.mean()
reg[("off", "all")] = both[both.slow_start == "off"].groupby("policy").regret.mean()
reg = reg.round(1)
reg.to_csv(f"{R}/P5_noss_regret.csv")
print("256 KB mean regret (ms)\n", reg.to_string())

# edge server TCT vs formula and break-even (S1, S2)
rows = []
for scen in ("S1", "S2"):
    for cond in both[both.scenario == scen].condition.unique():
        r = {"scenario": scen, "condition": cond}
        rtt = float(cond.split()[1]) if cond.startswith("RTT") else 10.0
        bw = float(cond.split()[1]) if cond.startswith("BW") else 100.0
        for ss in ("on", "off"):
            t = both[(both.slow_start == ss) & (both.condition == cond) & (both.scenario == scen)].set_index("policy")
            r[f"local_{ss}"] = t.loc["Always-Local", "mean"]
            r[f"edge1_{ss}"] = t.loc["Always-Edge1", "mean"]
            r[f"edge1_p95_{ss}"] = t.loc["Always-Edge1", "p95"]
        r["edge_formula"] = edge_tct_ms(1_000_000, 256, rtt + 0.5, bw, 0)
        rows.append(r)
be = pd.DataFrame(rows).round(1)
be.to_csv(f"{R}/P5_noss_breakeven.csv", index=False)
print(be.to_string(index=False))

# simulator vs testbed (|testbed - sim| for the same policy and condition), 256 KB
sim = pd.read_csv(f"{R}/P5_sim_vs_testbed.csv")[["scenario", "condition", "payload_kb", "policy", "sim_mean"]]
j = off.merge(sim, on=KEY + ["policy"])
j_on = on.merge(sim, on=KEY + ["policy"])
sv = pd.DataFrame({"on": j_on.assign(a=(j_on["mean"] - j_on.sim_mean).abs()).groupby("policy").a.mean(),
                   "off": j.assign(a=(j["mean"] - j.sim_mean).abs()).groupby("policy").a.mean()}).reindex(ORDER).dropna().round(1)
sv.to_csv(f"{R}/P5_noss_sim_vs_testbed.csv")
print("|testbed - sim| 256 KB (ms)\n", sv.to_string())

fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
s1 = be[be.scenario == "S1"].assign(rtt=lambda x: x.condition.str.split().str[1].astype(int)).sort_values("rtt")
ax[0].plot(s1.rtt, s1.local_off, "s-", color=COLORS["Always-Local"], label="Always-Local")
ax[0].plot(s1.rtt, s1.edge1_on, "o--", color=COLORS["Always-Edge1"], label="Always-Edge1, slow start ON (default)")
ax[0].plot(s1.rtt, s1.edge1_off, "o-", color=COLORS["Always-Edge1"], label="Always-Edge1, slow start OFF")
xs = np.linspace(5, 210, 100)
ax[0].plot(xs, [edge_tct_ms(1_000_000, 256, x + 0.5, 100, 0) for x in xs], "k:", lw=1, label="formula: RTT + D/B + compute")
ax[0].axhline(local_tct_fluid_ms(1_000_000), color="gray", ls=":", lw=1, label="formula: local (350 ms)")
ax[0].set_xlabel("RTT (ms)"); ax[0].set_ylabel("mean TCT (ms)"); ax[0].set_title("S1, 256 KB: TCT vs RTT")
ax[0].legend(fontsize=7); ax[0].grid(alpha=0.3)
pols = [p for p in ORDER if p != "Offline-Opt"]
x = np.arange(len(pols))
ax[1].barh(x - 0.2, [reg.loc[p, ("on", "all")] for p in pols], 0.4, label="slow start ON", color="tab:gray")
ax[1].barh(x + 0.2, [reg.loc[p, ("off", "all")] for p in pols], 0.4, label="slow start OFF", color="tab:blue")
ax[1].set_yticks(x); ax[1].set_yticklabels(pols, fontsize=8); ax[1].invert_yaxis(); ax[1].set_xscale("symlog")
ax[1].set_xlabel("mean regret vs Offline-Opt (ms), S1-S3, 256 KB"); ax[1].legend(fontsize=8); ax[1].grid(axis="x", alpha=0.3)
plt.tight_layout(); plt.savefig(f"{R}/P5_noss.png", dpi=110)
