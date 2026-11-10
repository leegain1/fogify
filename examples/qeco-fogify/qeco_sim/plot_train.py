"""Training curves of QECO-orig / QECO-net (results/P3_<variant>/train_log.csv)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
W = 20

fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
for v in ("orig", "net"):
    d = pd.read_csv(os.path.join(RES, f"P3_{v}", "train_log.csv"))
    for ax, col, label in zip(axes, ["qoe_avg", "tct_avg_ms", "share_local"],
                              ["QoE per task", "mean TCT (ms)", "share of local actions"]):
        ax.plot(d.episode, d[col], alpha=0.15)
        ax.plot(d.episode, d[col].rolling(W).mean(), color=ax.lines[-1].get_color(), label=f"QECO-{v}")
        ax.set_ylabel(label); ax.grid(alpha=0.3)
axes[0].legend(); axes[-1].set_xlabel("episode")
fig.suptitle(f"QECO on the testbed-fitted simulator ({W}-episode moving average)\n"
             "conditions (RTT, bandwidth, edge server load) are random and change within episodes")
plt.tight_layout(); plt.savefig(os.path.join(RES, "P3_train_curves.png"), dpi=110)
