"""Phase 4: every policy runs through the same driver on the base condition
(RTT 10 ms, 100Mbit, no load), n = 30, iter = 1M, payload 1 KB.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase4_baseline.py
"""
import subprocess

import pandas as pd

import driver as dr

dr.start_policy_server()
bed = dr.Testbed()
bed.up()
try:
    print("observed:", bed.cond())
    df = pd.concat([dr.run_policy(bed, p, n=30, label="P4-base", seed=1) for p in dr.POLICY_NAMES])
finally:
    bed.down()
    subprocess.run(["docker", "rm", "-f", "qeco-policy"], capture_output=True)

df.to_csv("results/P4_baseline.csv", index=False)
ok = df[df.status == "ok"]
s = ok.groupby("policy").agg(p50=("tct_ms", "median"), p95=("tct_ms", lambda x: x.quantile(0.95)),
                             mean=("tct_ms", "mean"), n=("tct_ms", "size"),
                             local=("action", lambda a: (a == 0).mean()), e1=("action", lambda a: (a == 1).mean()),
                             e2=("action", lambda a: (a == 2).mean()), decide_ms=("decide_ms", "median")).round(2)
s.to_csv("results/P4_baseline_summary.csv")
print(s.to_string())
print("errors:", (df.status != "ok").sum())
