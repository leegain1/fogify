"""Phase 1: edge server CPU isolation (cpuset) + experiment D rerun.

Runs D (80% CPU stress on edge-server-1 only) twice: without pinning (as in
uvc-sha256) and with CPUSETS pinning. Pass criterion: edge-server-2 TCT p50
during stress within 5% of before.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase1_isolation.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import testbed as tb

N, ITER, STRESS_S = 30, 1_000_000, 90


def run_d(pinned):
    tag = "pinned" if pinned else "unpinned"
    rows = []
    for phase in ["before", "stress"]:
        if phase == "stress":
            tb.stress("edge-server-1", cpu=80, duration=STRESS_S)
        for es in ["edge-server-1", "edge-server-2"]:
            df = tb.run_tasks("edge-server", iter=ITER, n=N, servers=(es,), label=f"D-{phase}")
            df["cpuset"], df["phase"] = tag, phase
            rows.append(df)
    tb.wait_stress_done("edge-server-1")
    # local processing once per condition, for reference
    loc = tb.run_tasks("local", iter=ITER, n=N, label="D-local")
    loc["cpuset"], loc["phase"] = tag, "before"
    rows.append(loc)
    return pd.concat(rows)


tb.connect()
out = []
for pinned in [False, True]:
    print("deploy, pinned =", pinned, tb.deploy(pin=pinned))
    print("RTT", tb.ping_ms("edge-server-1"), tb.ping_ms("edge-server-2"))
    out.append(run_d(pinned))
    tb.fogify.undeploy()

D = pd.concat(out)
D.to_csv("results/P1_D_isolation.csv", index=False)
s = tb.p50_p95(D, ["cpuset", "target", "phase"])
s_comp = tb.p50_p95(D, ["cpuset", "target", "phase"], col="server_compute_ms")
print(s)
print(s_comp)

p50 = s["p50"].unstack()
p50["change_%"] = ((p50["stress"] / p50["before"] - 1) * 100).round(1)
print(p50)
p50.to_csv("results/P1_D_summary.csv")

fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
ok = D[(D.status == "ok") & (D["mode"] == "edge-server")]
for ax, tag in zip(axes, ["unpinned", "pinned"]):
    med = ok[ok.cpuset == tag].groupby(["target", "phase"]).tct_ms.median().unstack()[["before", "stress"]]
    med.index = [i.replace("http://", "").replace(":8080", "") for i in med.index]
    med.plot.bar(ax=ax, rot=0)
    ax.set_title(f"{tag}"); ax.set_xlabel(""); ax.grid(axis="y", alpha=0.3)
axes[0].set_ylabel("TCT p50 (ms)")
fig.suptitle("80% CPU stress on edge-server-1 only (iter = 1M, n = 30)")
plt.tight_layout(); plt.savefig("results/P1_D_isolation.png", dpi=120)
