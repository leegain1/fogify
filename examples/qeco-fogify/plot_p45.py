"""Phase 4.5 figure: results/P45_testbed.csv (run 1), P45_repeat_r1.csv, P45_testbed2.csv
(interleaved run, used for the tables) and P45_sim_check.csv."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

r1 = pd.read_csv("results/P45_testbed.csv")
rep = pd.read_csv("results/P45_repeat_r1.csv")
df = pd.read_csv("results/P45_testbed2.csv")
df = df[df.status == "ok"]
fig, ax = plt.subplots(1, 4, figsize=(18, 4.4))

# (a) edge server compute time per measurement block (drift between periods)
blocks, names = [], []
for l in ("gap0", "gap200", "gap1000"):
    blocks.append(r1[r1.label == l].server_compute_ms); names.append(f"run1\n{l}")
for k in (0, 1):
    for m, short in (("uvc-client run (back to back)", "b2b"), ("agent (gap 200)", "gap200")):
        g = rep[(rep.method == m) & (rep["round"] == k) & (rep.target == "edge1")]
        blocks.append(g.server_compute_ms); names.append(f"rep r{k}\n{short}")
e = df[(df.exp == "base") & (df.target != "local") & (df.policy != "Offline-Opt")]
for l in sorted(e.label.unique()):
    blocks.append(e[e.label == l].server_compute_ms); names.append(f"run2\n{l[5:]}")
ax[0].boxplot(blocks, labels=names)
ax[0].tick_params(axis="x", labelsize=7)
ax[0].axhline(67.7, color="gray", ls=":", label="Phase 1 (67.7)"); ax[0].legend(fontsize=8)
ax[0].set_ylabel("edge server compute (ms)"); ax[0].set_title("(a) edge server compute, iter 1M")

# (b) local TCT before / during / after stress on edge-server-2 (2 rounds)
s = df[df.exp == "share"]
ph = ["before", "during", "after"]
ax[1].boxplot([s[s.phase == p].tct_ms for p in ph], labels=["before", "edge-server-2\n80% stress", "after"])
ax[1].set_ylabel("local TCT (ms)"); ax[1].set_title("(b) local (core 14) vs stress on cores 12,13")

# (c) base condition, all policies (p50 bar, p95 marker)
b = df[df.exp == "base"]
st = b.groupby("policy").tct_ms.agg(p50="median", p95=lambda x: x.quantile(0.95)).sort_values("p50")
ax[2].barh(st.index, st.p50, color=["tab:green" if p.startswith("Offline") else "tab:blue" for p in st.index])
ax[2].plot(st.p95, st.index, "k|", ms=12, label="p95")
ax[2].set_xlabel("TCT p50 (ms)"); ax[2].set_title("(c) base: RTT 10, 100Mbit, 1 KB"); ax[2].legend()

# (d) sim (closed loop) vs testbed for the fixed policies
c = pd.read_csv("results/P45_sim_check.csv")
x = range(len(c))
ax[3].bar([i - 0.2 for i in x], c.testbed_mean, 0.4, label="Fogify")
ax[3].bar([i + 0.2 for i in x], c.sim_closed_mean, 0.4, label="simulator (closed loop)")
ax[3].plot([i + 0.2 for i in x], c.sim_open_mean, "rx", label="simulator (open loop, Phase 3)")
ax[3].set_xticks(list(x)); ax[3].set_xticklabels(c.policy, fontsize=8)
ax[3].set_ylabel("mean TCT (ms)"); ax[3].set_title("(d) simulator vs testbed"); ax[3].legend(fontsize=8)
for a in ax:
    a.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("results/P45_testbed.png", dpi=110)
