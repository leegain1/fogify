"""Phase 4.5 recalibration after fixing the CPU (host/cpu_perf.sh on: performance governor,
no C6+ on E-cores). Base condition (RTT 10 ms, 100Mbit, 1 KB, iter 1M), n = 30 per block.

  edge   : uvc-client run back to back vs agent (gap 200), 2 rounds; agent under 80% stress
  local  : uvc-client run back to back (bimodal CFS pattern -> local work) and agent (gap 200)
  share  : Always-Local before / during / after 80% stress on edge-server-2

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase45_calib.py
"""
import time

import pandas as pd

import driver as dr
import testbed as tb


def block(df, name, **kw):
    return df.assign(block=name, **kw)


bed = dr.Testbed()
bed.up()
parts = []
try:
    for k in range(2):
        d = tb.run_tasks("edge-server", n=30, servers=("edge-server-1",), label="b2b")
        parts.append(block(d[["tct_ms", "server_compute_ms", "status"]], f"edge b2b r{k}", target="edge1"))
        parts.append(block(dr.run_policy(bed, "Always-Edge1", n=30, seed=1 + k), f"edge gap200 r{k}"))
        d = tb.run_tasks("local", n=30, label="b2b")
        parts.append(block(d[["tct_ms", "status"]], f"local b2b r{k}", target="local"))
        parts.append(block(dr.run_policy(bed, "Always-Local", n=30, seed=1 + k), f"local gap200 r{k}"))
        print("round", k, flush=True)
    bed.stress("edge-server-1", cpu=80, duration=30)
    time.sleep(3)
    parts.append(block(dr.run_policy(bed, "Always-Edge1", n=30, seed=5), "edge1 gap200 stress80"))
    bed.wait_stress_done()
    time.sleep(3)
    for k in range(2):
        parts.append(block(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k), f"share r{k}", phase="before"))
        bed.stress("edge-server-2", cpu=80, duration=25)
        time.sleep(3)
        parts.append(block(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k), f"share r{k}", phase="during"))
        bed.wait_stress_done()
        time.sleep(3)
        parts.append(block(dr.run_policy(bed, "Always-Local", n=30, seed=20 + k), f"share r{k}", phase="after"))
        print("share", k, flush=True)
finally:
    bed.down()
df = pd.concat(parts, ignore_index=True)
df.to_csv("results/P45_calib.csv", index=False)
ok = df[df.status == "ok"]
print(ok.groupby(["block", "phase"], dropna=False)[["tct_ms", "server_compute_ms"]]
      .agg(["median", "mean"]).round(1).to_string())
