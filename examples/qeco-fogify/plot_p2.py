"""Phase 2: compare our upstream run with the upstream reference logs.

    docker run --rm -u 1000:1000 -v $PWD:/w -w /w qeco-tf:0.1 python plot_p2.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RUNS = {"ours (upstream code, this PC)": "results/P2_upstream",
        "upstream reference (TrainedModel_20UE_2EN_RandomMode)": "upstream/reference_20UE_2EN_RandomMode"}
METRICS = ["QoE", "Delay", "Energy", "Drop"]
W = 20  # moving average window (episodes)


def load(path, metric):
    with open(f"{path}/{metric}.txt") as f:
        return pd.Series([float(x) for x in f.read().split()])


data = {name: pd.DataFrame({m: load(p, m) for m in METRICS}) for name, p in RUNS.items()}

fig, axes = plt.subplots(len(METRICS), 1, figsize=(8, 11), sharex=True)
for ax, m in zip(axes, METRICS):
    for name, df in data.items():
        ax.plot(df[m], alpha=0.15)
        ax.plot(df[m].rolling(W).mean(), label=name, color=ax.lines[-1].get_color())
    ax.set_ylabel(m); ax.grid(alpha=0.3)
axes[0].legend(fontsize=8)
axes[-1].set_xlabel("episode")
fig.suptitle(f"QECO upstream training (20 UE, 2 edge servers), {W}-episode moving average")
plt.tight_layout(); plt.savefig("results/P2_upstream_curves.png", dpi=110)

rows = []
for name, df in data.items():
    for lo, hi in [(0, 50), (len(df) - 50, len(df))]:
        rows.append({"run": name, "episodes": f"{lo}-{hi - 1}", **df.iloc[lo:hi].mean().round(2).to_dict()})
summary = pd.DataFrame(rows)
summary.to_csv("results/P2_upstream_summary.csv", index=False)
print(summary.to_string(index=False))
