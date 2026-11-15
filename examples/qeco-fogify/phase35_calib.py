"""Phase 3.5 calibration after setting the local node to 0.2 CPU (clock_speed 417 MHz).
Base condition (RTT 10 ms, 100Mbit, 1 KB, iter 1M), CPU fixed (host/cpu_perf.sh on).

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase35_calib.py
"""
import pandas as pd

import driver as dr
import testbed as tb

bed = dr.Testbed()
bed.up()
parts = []
try:
    for k in range(2):
        d = tb.run_tasks("local", n=30, label="b2b")
        parts.append(d[["tct_ms", "status"]].assign(block=f"local b2b r{k}"))
        parts.append(dr.run_policy(bed, "Always-Local", n=30, seed=1 + k).assign(block=f"local gap200 r{k}"))
        parts.append(dr.run_policy(bed, "Always-Edge1", n=30, seed=1 + k).assign(block=f"edge gap200 r{k}"))
        print("round", k, flush=True)
finally:
    bed.down()
df = pd.concat(parts, ignore_index=True)
df.to_csv("results/P35_calib.csv", index=False)
ok = df[df.status == "ok"]
print(ok.groupby("block").tct_ms.describe(percentiles=[.05, .5, .95]).round(1).to_string())
print(ok.groupby("block").server_compute_ms.median().round(1).to_string())
