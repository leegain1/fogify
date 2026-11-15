"""Markdown tables for research-docs/qeco-fogify/phase5.md from the phase5_analyze.py outputs.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase5_tables.py > results/P5_tables.md
"""
import pandas as pd

import driver  # noqa: F401  (puts qeco_sim on sys.path for phase5)

R = "results"
ORDER = ["Always-Local", "Always-Edge1", "Always-Edge2", "Nearest-Edge", "Model-Greedy",
         "QECO-orig (open)", "QECO-net (open)", "QECO-orig", "QECO-net", "QECO-net+", "Offline-Opt"]
tab = pd.read_csv(f"{R}/P5_table.csv")


def md(df):
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if pd.isna(v) else (f"{v:.1f}" if isinstance(v, float) else str(v)) for v in r) + " |")
    return "\n".join(out)


print("## regret by scenario\n")
r = tab.groupby(["policy", "scenario", "payload_kb"]).regret.mean().unstack([1, 2]).reindex(ORDER)
r.columns = [f"{s} {kb}KB" for s, kb in r.columns]
r["all 1KB"] = tab[tab.payload_kb == 1].groupby("policy").regret.mean()
r["all 256KB"] = tab[tab.payload_kb == 256].groupby("policy").regret.mean()
print(md(r.reset_index()))

for kb in (1, 256):
    print(f"\n## p50 / p95 per condition, {kb} KB\n")
    t = tab[tab.payload_kb == kb].copy()
    t["v"] = t.apply(lambda x: f"{x.p50:.0f} / {x.p95:.0f}", axis=1)
    from phase5 import conditions
    conds = [c for _, c, _ in conditions()]
    p = t.pivot_table(index="policy", columns="condition", values="v", aggfunc="first").reindex(ORDER)[conds]
    print(md(p.reset_index()))

print("\n## choice share (local / E1 / E2) of learned policies\n")
t = tab[tab.policy.str.startswith("QECO") | tab.policy.isin(["Model-Greedy", "Offline-Opt"])].copy()
t["v"] = t.apply(lambda x: f"{x.local:.1f}/{x.e1:.1f}/{x.e2:.1f}", axis=1)
t["cond"] = t.condition + " " + t.payload_kb.astype(str) + "KB"
p = t.pivot_table(index="cond", columns="policy", values="v", aggfunc="first")
print(md(p.reset_index()))

print("\n## simulator vs testbed (mean |testbed - sim| ms, by payload)\n")
j = pd.read_csv(f"{R}/P5_sim_vs_testbed.csv")
s = j.assign(a=j.diff_ms.abs()).groupby(["policy", "payload_kb"]).a.mean().unstack().reindex(ORDER).dropna(how="all")
s.columns = [f"{c} KB" for c in s.columns]
s["256 KB, RTT >= 55"] = j[(j.payload_kb == 256) & j.condition.isin(["RTT 55", "RTT 105", "RTT 205"])] \
    .assign(a=lambda x: x.diff_ms.abs()).groupby("policy").a.mean()
print(md(s.reset_index()))

print("\n## decide time p50 (ms)\n")
print(md(tab.groupby("policy").decide_ms.median().reindex(ORDER).reset_index()))
