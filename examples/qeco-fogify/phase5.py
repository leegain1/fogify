"""Phase 5: policy comparison on Fogify, S1-S3 (static conditions) and S4 (conditions
change while the tasks run). iter 1M, payload 1 KB and 256 KB, n = 30 per condition.
CPU fixed (host/cpu_perf.sh on). Background load only on edge-server-1 (phase4_5.md, plan A).

Policies (10 on the testbed + Offline-Opt computed per task from the Always-* runs):
  rules  : Always-Local, Always-Edge1, Always-Edge2, Nearest-Edge, Model-Greedy
  QECO   : "(open)" = trained with open-loop arrivals (Phase 3 setup, same physics), mismatch group ①
           QECO-orig / QECO-net = Phase 3.5 closed-loop retraining (group ②)
           QECO-net+ = + local CPU state (group ③)
Interleaving: per condition 3 rounds x 10 tasks per policy (edge server speed drifted
between periods before the CPU was fixed; this keeps any drift equal for all policies).
Results are appended per condition, so a rerun skips finished conditions.

    docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase5.py [static|s4|all]
"""
import json
import os
import subprocess
import sys
import threading
import time

import pandas as pd

import driver as dr
import testbed as tb

# P5_OUT / P5_PAYLOADS / QECO_COMPOSE select a variant run, e.g. the 256 KB rerun with TCP slow
# start after idle turned off: QECO_COMPOSE=docker-compose-noss.yaml P5_PAYLOADS=256
# P5_OUT=results/P5_noss_runs.csv python phase5.py static
OUT = os.environ.get("P5_OUT", "results/P5_runs.csv")
OUT_S4 = "results/P5_s4.csv"
ROUNDS, PER_ROUND = 3, 10
ALL_PAYLOADS = (1, 256)
PAYLOADS = tuple(int(x) for x in os.environ.get("P5_PAYLOADS", "1,256").split(","))


# S3 loads; 90% was added after the main run (1 KB) to show the loss of Nearest-Edge well past the
# inversion point (~72%): P5_S3_LOADS=90 P5_PAYLOADS=1 P5_ONLY=S3 python phase5.py static
S3_LOADS = tuple(int(x) for x in os.environ.get("P5_S3_LOADS", "0,30,60,80").split(","))
ONLY = os.environ.get("P5_ONLY")


def conditions():
    """(scenario, condition name, [(rtt, bw, load) for edge-server-1, edge-server-2])."""
    for rtt in (10, 30, 55, 105, 205):
        yield "S1", f"RTT {rtt}", [(rtt, 100, 0), (rtt, 100, 0)]
    for bw in (100, 10, 1):
        yield "S2", f"BW {bw}", [(10, bw, 0), (10, bw, 0)]
    for load in S3_LOADS:
        yield "S3", f"E1 load {load}", [(10, 100, load), (50, 100, 0)]


def models():
    """Phase 3.5 model per variant: the seed with the best validation TCT (chosen on the
    validation episodes, not on the evaluation)."""
    m = {"QECO-orig (open)": ("orig", "P35_open_orig"), "QECO-net (open)": ("net", "P35_open_net")}
    for v, name in (("orig", "QECO-orig"), ("net", "QECO-net"), ("netplus", "QECO-net+")):
        best = min((json.load(open(f"results/P35_{v}_s{s}/meta.json")).get("best_val_tct_ms", 1e9), s)
                   for s in range(3))
        m[name] = (v, f"P35_{v}_s{best[1]}")
    return m


def stop_stress(edge="edge-server-1"):
    CURRENT.pop("load", None)
    subprocess.run(["docker", "exec", tb.container(edge), "pkill", "-f", "stress"], capture_output=True)
    subprocess.run(["docker", "exec", tb.container(edge), "pkill", "-f", "cpulimit"], capture_output=True)
    # killed stress / cpulimit stay as zombies (uvc-server as PID 1 does not reap them), so
    # testbed.wait_stress_done (pgrep) would wait forever: wait for live processes only
    for _ in range(30):
        ps = subprocess.run(["docker", "exec", tb.container(edge), "ps", "-o", "stat,comm"],
                            capture_output=True, text=True).stdout.splitlines()[1:]
        if not any(l.split()[0][0] != "Z" and ("stress" in l or "cpulimit" in l) for l in ps if l.split()):
            return
        time.sleep(1)


CURRENT = {}   # what apply() last set: {edge: (rtt, bw)}, "load": edge-server-1 load


def direct_stress(load, edge="edge-server-1"):
    """Same command Fogify runs for a stress action (cpulimit --limit cpus*cpu -i -- stress --cpu
    ceil(cpus), edge server = 2 CPU), but exec'd directly: the Fogify API call took 10-30 s
    to take effect, too slow for the 20 s segments of S4."""
    subprocess.run(["docker", "exec", "-d", tb.container(edge), "cpulimit", "--limit", str(int(2 * load)), "-i",
                    "--", "stress", "--cpu", "2"], check=True, capture_output=True)


def apply(bed, links, settle_s=6, direct=False):
    """Set links and edge-server-1 load; only what changed. settle_s: wait for the tc rules
    and the cAdvisor load (1-2 s behind) before tasks run (S4: 0, the lag is part of it)."""
    for e, (rtt, bw, _) in zip(dr.EDGES, links):
        if CURRENT.get(e) != (rtt, bw):
            bed.set_link(e, rtt_ms=rtt, bw_mbit=bw)
            CURRENT[e] = (rtt, bw)
    load = links[0][2]
    if CURRENT.get("load", -1) != load:
        stop_stress()
        if load and direct:
            direct_stress(load)
        elif load:
            bed.stress("edge-server-1", cpu=load, duration=1800)
        CURRENT["load"] = load
    time.sleep(settle_s)


def run_static(bed, policies):
    done = set(pd.read_csv(OUT).label.unique()) if os.path.exists(OUT) else set()
    for kb in PAYLOADS:
        for j, (scen, name, links) in enumerate(conditions()):
            ci = ALL_PAYLOADS.index(kb) * len(list(conditions())) + j + 1   # same seeds as the full run
            if ONLY and scen != ONLY:
                continue
            labels = [f"{scen}|{name}|{kb}KB|r{k}" for k in range(ROUNDS)]
            if all(l in done for l in labels):
                continue
            apply(bed, links)
            print(scen, name, kb, "observed", [{k: round(v, 2) for k, v in c.items()} for c in bed.cond()], flush=True)
            parts = []
            for k, label in enumerate(labels):
                order = policies[k % len(policies):] + policies[:k % len(policies)]   # rotate the order per round
                for p in order:
                    parts.append(dr.run_policy(bed, p, n=PER_ROUND, payload_kb=kb, seed=1000 * ci + k, label=label)
                                 .assign(scenario=scen, condition=name, round=k,
                                         set_rtt1=links[0][0], set_rtt2=links[1][0], set_bw=links[0][1],
                                         set_load1=links[0][2]))
            df = pd.concat(parts, ignore_index=True)
            df.to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            print("  done", time.strftime("%H:%M:%S"), "errors", (df.status != "ok").sum(), flush=True)
    stop_stress()


# S4: one timeline per policy; conditions change while the tasks run (edge-server-1 and 2 links,
# edge-server-1 load). 6 segments x 20 s.
S4_SEGMENT_S = 20
S4_TIMELINE = [  # (edge-server-1 (rtt, bw, load), edge-server-2 (rtt, bw, load))
    ((10, 100, 0), (30, 100, 0)),
    ((105, 100, 0), (30, 100, 0)),
    ((10, 100, 80), (30, 100, 0)),
    ((10, 100, 0), (205, 100, 0)),
    ((55, 100, 60), (55, 100, 0)),
    ((10, 10, 0), (30, 100, 0)),
]


def run_s4(bed, policies, kb=1):
    done = set(pd.read_csv(OUT_S4).policy.unique()) if os.path.exists(OUT_S4) else set()
    for p in policies:
        if p in done:
            continue
        apply(bed, list(S4_TIMELINE[0]), direct=True)
        stop = threading.Event()
        marks = []

        def timeline():
            # a segment starts when its links and load are in place (set_link takes ~2 s per link)
            for i, links in enumerate(S4_TIMELINE):
                if i:
                    apply(bed, list(links), settle_s=0, direct=True)
                marks.append((time.time(), i))
                if stop.wait(S4_SEGMENT_S):
                    return
            stop.set()

        th = threading.Thread(target=timeline, daemon=True)
        th.start()
        rows = []
        k = 0
        while not stop.is_set():   # run until the timeline ends; each chunk keeps the same gap sequence per policy
            rows.append(dr.run_policy(bed, p, n=10, payload_kb=kb, seed=500 + k, label=f"S4|{k}", warmup=0))
            k += 1
        th.join()
        df = pd.concat(rows, ignore_index=True)
        t = df.ts_unix_ms / 1000
        df["segment"] = [max([i for ts, i in marks if ts <= x] or [0]) for x in t]
        df["t_s"] = t - marks[0][0]
        df.to_csv(OUT_S4, mode="a", header=not os.path.exists(OUT_S4), index=False)
        print("S4", p, len(df), "tasks", time.strftime("%H:%M:%S"), flush=True)
    stop_stress()


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    m = models()
    print("models:", m, flush=True)
    dr.start_policy_server(m)
    policies = list(dr.RULES) + list(m)
    bed = dr.Testbed()
    bed.up()
    try:
        if what in ("static", "all"):
            run_static(bed, policies)
        if what in ("s4", "all"):
            run_s4(bed, policies)
    finally:
        try:
            stop_stress()
        except Exception as ex:
            print("stop_stress:", ex)
        bed.down()
        subprocess.run(["docker", "rm", "-f", "qeco-policy"], capture_output=True)


if __name__ == "__main__":
    main()
