"""Phase 4.5 testbed runs (RTT 10 ms, 100Mbit, no load, iter 1M, 1 KB, n = 30).

  gap   : Always-Edge1 with idle gap mean 0 / 200 / 1000 ms
          (why edge server TCT grew from 79.0 (Phase 1) to 82.6 ms (Phase 4))
  share : Always-Local before / during 80% CPU stress on edge-server-2
          (local core 14 and edge-server-2 cores 12,13 are in the same E-core cluster)
  base  : every policy + Offline-Opt (new: from the separate Always-* runs)
          and Offline-Opt-seq (Phase 4 method) for comparison

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase45_testbed.py
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
    print("observed:", bed.cond(), flush=True)
    # gap test
    for g in (0, 200, 1000):
        parts.append(dr.run_policy(bed, "Always-Edge1", n=30, gap_mean_ms=g, seed=3, label=f"gap{g}").assign(exp="gap"))
        print("gap", g, "done", flush=True)
    # local / edge-server-2 cluster sharing
    parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=2, label="E2stress-before").assign(exp="share"))
    bed.stress("edge-server-2", cpu=80, duration=60)
    time.sleep(3)
    parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=2, label="E2stress-during").assign(exp="share"))
    print("share done, load seen on edge-server-2:", bed.cond()[1]["load"], flush=True)
    bed.wait_stress_done()
    time.sleep(5)
    # base condition, all policies
    for p in dr.POLICY_NAMES + ["Offline-Opt-seq"]:
        parts.append(dr.run_policy(bed, p, n=30, seed=1, label="P45-base").assign(exp="base"))
        print(p, "done", flush=True)
finally:
    bed.down()
    subprocess.run(["docker", "rm", "-f", "qeco-policy"], capture_output=True)

df = pd.concat(parts, ignore_index=True)
base = df[df.exp == "base"]
df = pd.concat([df, dr.offline_opt(base).assign(exp="base")], ignore_index=True)
df.to_csv("results/P45_testbed.csv", index=False)
s = dr.summarize(df)
s.to_csv("results/P45_testbed_summary.csv")
print(s.to_string())
print("errors:", (df.status != "ok").sum())
