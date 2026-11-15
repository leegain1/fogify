"""Phase 4.5 rerun with interleaving: edge server compute time drifts between runs
(67.7 ms normally, 80-90 ms in some periods, see phase4_5.md), so policies are run in
rounds (10 tasks per policy per round, 3 rounds) instead of 30 tasks one after another.
Offline-Opt is computed per round (label) from the Always-* runs of that round.

  share : Always-Local before / during / after 80% CPU stress on edge-server-2, 2 rounds
  base  : every policy + Offline-Opt-seq, 3 rounds x 10 tasks

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase45_testbed2.py
"""
import subprocess
import time

import pandas as pd

import driver as dr

dr.start_policy_server()
bed = dr.Testbed()
bed.up()
parts = []
try:
    for k in range(2):
        parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k, label=f"share-r{k}").assign(exp="share", phase="before"))
        bed.stress("edge-server-2", cpu=80, duration=25)
        time.sleep(3)
        parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k, label=f"share-r{k}").assign(exp="share", phase="during"))
        bed.wait_stress_done()
        time.sleep(3)
        parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k, label=f"share-r{k}").assign(exp="share", phase="after"))
        print("share round", k, "done", flush=True)
    for k in range(3):
        for p in dr.POLICY_NAMES + ["Offline-Opt-seq"]:
            parts.append(dr.run_policy(bed, p, n=10, seed=10 + k, label=f"base-r{k}").assign(exp="base"))
        print("base round", k, "done", flush=True)
finally:
    bed.down()
    subprocess.run(["docker", "rm", "-f", "qeco-policy"], capture_output=True)

df = pd.concat(parts, ignore_index=True)
base = df[df.exp == "base"]
df = pd.concat([df, dr.offline_opt(base).assign(exp="base")], ignore_index=True)
df.to_csv("results/P45_testbed2.csv", index=False)
ok = df[df.status == "ok"]
print(ok[ok.exp == "share"].groupby(["label", "phase"]).tct_ms.agg(["median", "mean", "count"]).round(1).to_string())
s = dr.summarize(ok[ok.exp == "base"].assign(label="base"))
s.to_csv("results/P45_base_summary.csv")
print(s.to_string())
e = ok[(ok.exp == "base") & (ok.target != "local")]
print("edge compute per round:", e.groupby("label").server_compute_ms.median().round(1).to_dict())
print("errors:", (df.status != "ok").sum())
