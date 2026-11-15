"""Phase 4.5 repeatability check: Phase 1 method (uvc-client run, back to back) and
the agent (closed loop, gap 200 ms) in the same deployment, base condition, n = 30.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase45_repeat.py <tag>
"""
import sys

import pandas as pd

import driver as dr
import testbed as tb

tag = sys.argv[1] if len(sys.argv) > 1 else "r1"
bed = dr.Testbed()
bed.up()
rows = []
try:
    for k in range(2):
        d = tb.run_tasks("edge-server", n=30, servers=("edge-server-1",), label="run")
        rows.append(pd.DataFrame({"method": "uvc-client run (back to back)", "target": "edge1", "round": k,
                                  "tct_ms": d.tct_ms, "server_compute_ms": d.server_compute_ms}))
        for p, t in (("Always-Edge1", "edge1"), ("Always-Local", "local")):
            d = dr.run_policy(bed, p, n=30, seed=1, label="rep")
            rows.append(pd.DataFrame({"method": "agent (gap 200)", "target": t, "round": k,
                                      "tct_ms": d.tct_ms, "server_compute_ms": d.server_compute_ms}))
finally:
    bed.down()
df = pd.concat(rows).assign(tag=tag)
df.to_csv(f"results/P45_repeat_{tag}.csv", index=False)
print(df.groupby(["method", "target", "round"])[["tct_ms", "server_compute_ms"]].median().round(2).to_string())
