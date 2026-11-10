"""Phase 4 driver: runs in the Fogify ui container and lets a policy choose the
execution location of every task on the real testbed.

    local node   : uvc-client agent (:8081)  POST /run?target=local|edge1|edge2
    qeco-policy  : QECO models (TF) on :8090, started by start_policy_server()
    observation  : RTT_i  <- agent /probe (HTTP GET /hello round trip), every 0.5 s
                   B_i    <- value set by the driver (set_link)
                   L_i    <- cAdvisor CPU usage of the edge server container minus the
                             compute time of our own tasks there, / 2 cores
"""
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.request

import numpy as np
import pandas as pd

import testbed as tb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "qeco_sim"))
from policies import RULES, model_greedy_estimates   # noqa: E402
from testbed_model import edge_tct_ms, local_tct_fluid_ms   # noqa: E402

CONTROL_NET = "fogemulator_default"      # ui, controller, cAdvisor and (after connect) the local node
HOST_DIR = os.environ.get("QECO_HOST_DIR", "/home/user/fogify/examples/qeco-fogify")  # for docker run -v
EDGES = ["edge-server-1", "edge-server-2"]
TARGETS = ["local", "edge1", "edge2"]
EDGE_CORES = 2.0
SLOT_MS = 10
POLICY_NAMES = list(RULES) + ["QECO-orig", "QECO-net", "Oracle"]


def _http(url, data=None, timeout=60):
    if isinstance(data, dict):
        req = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url, data)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _ip(container, net=CONTROL_NET):
    return subprocess.run(["docker", "inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{net}").IPAddress}}}}',
                           container], capture_output=True, text=True, check=True).stdout.strip()


def start_policy_server():
    subprocess.run(["docker", "rm", "-f", "qeco-policy"], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", "qeco-policy", "--network", CONTROL_NET, "-u", "1000:1000",
                    "-v", f"{HOST_DIR}:/w", "-w", "/w/qeco_sim", "qeco-tf:0.1", "python", "policy_server.py"],
                   check=True, capture_output=True)
    for _ in range(60):
        try:
            _http("http://qeco-policy:8090/reset", {"variant": "net"}, timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("policy server did not start")


class Testbed:
    """Deployed topology + agent + observer thread."""

    def __init__(self):
        tb.connect()
        self.bw = {e: 100.0 for e in EDGES}
        self.own = {e: [] for e in EDGES}       # (end_ts_s, compute_ms) of our tasks per edge server
        self.obs = {"rtt": {e: 10.0 for e in EDGES}, "load": {e: 0.0 for e in EDGES}}
        self._stop = threading.Event()

    def up(self):
        print("deploy", tb.deploy())
        local = tb.container("local")
        subprocess.run(["docker", "network", "connect", CONTROL_NET, local], capture_output=True)
        self.agent = f"http://{_ip(local)}:8081"
        self.edge_ids = {e: subprocess.run(["docker", "inspect", "-f", "{{.Id}}", tb.container(e)],
                                           capture_output=True, text=True).stdout.strip() for e in EDGES}
        self._stop.clear()
        self.thread = threading.Thread(target=self._observe_loop, daemon=True)
        self.thread.start()
        time.sleep(3)

    def down(self):
        self._stop.set()
        tb.fogify.undeploy()

    # ------------------------------------------------------------ actions on the testbed
    def set_link(self, edge, rtt_ms=10, bw_mbit=100):
        tb.set_link(edge, rtt_ms=rtt_ms, bandwidth=f"{bw_mbit:g}Mbit")
        self.bw[edge] = float(bw_mbit)

    def stress(self, edge, cpu, duration):
        tb.fogify.stress(edge, duration=duration, cpu=cpu)

    def wait_stress_done(self):
        for e in EDGES:
            tb.wait_stress_done(e)

    def run(self, target, iter, payload):
        r = _http(f"{self.agent}/run?target={target}&iter={iter}&payload={payload}", b"")
        if target != "local" and "server_compute_ms" in r:
            self.own[EDGES[TARGETS.index(target) - 1]].append((time.time(), r["server_compute_ms"]))
        return r

    # ------------------------------------------------------------ observation
    def _cpu_load(self, edge):
        d = _http(f"http://cadvisor:8080/api/v1.3/docker/{self.edge_ids[edge]}", timeout=3)
        st = list(d.values())[0]["stats"]
        a, b = st[-2], st[-1]
        ta, tb_ = (pd.Timestamp(x["timestamp"]).timestamp() for x in (a, b))
        used_ms = (b["cpu"]["usage"]["total"] - a["cpu"]["usage"]["total"]) / 1e6
        own_ms = sum(c for t, c in self.own[edge] if ta < t <= tb_ + 0.05)
        self.own[edge] = [(t, c) for t, c in self.own[edge] if t > ta - 5]
        return float(np.clip((used_ms - own_ms) / ((tb_ - ta) * 1000 * EDGE_CORES), 0, 1))

    def _observe_loop(self):
        while not self._stop.is_set():
            for i, e in enumerate(EDGES):
                try:
                    r = _http(f"{self.agent}/probe?target=edge{i + 1}", timeout=5)
                    if "rtt_ms" in r:
                        self.obs["rtt"][e] = r["rtt_ms"]
                    self.obs["load"][e] = self._cpu_load(e)
                except Exception as ex:   # keep the last value
                    print("observe:", e, ex)
            self._stop.wait(0.5)

    def cond(self):
        """Observed state in the simulator's format (list per edge server)."""
        return [{"rtt": self.obs["rtt"][e], "bw": self.bw[e], "load": self.obs["load"][e]} for e in EDGES]


class QecoClient:
    """Builds the QECO state from testbed observations, like mec_env.TestbedMEC._observe.
    Tasks are run one at a time, so local / transmit / edge queues are empty at each decision."""

    SIZE_UNIT_KB = 64.0

    def __init__(self, variant):
        self.variant = variant
        self.last = None

    def reset(self):
        _http("http://qeco-policy:8090/reset", {"variant": self.variant})
        self.last = None

    def decide(self, cond, kb):
        obs = [kb / self.SIZE_UNIT_KB, 0.0, 0.0, 0.0, 0.0, 1.0]
        if self.variant == "net":
            obs += [c["rtt"] / 100.0 for c in cond] + [math.log10(c["bw"]) / 2.0 for c in cond] + [c["load"] for c in cond]
            lstm_now = [c["load"] for c in cond]
        else:
            lstm_now = [0.0, 0.0]          # own active tasks per edge server (none between tasks)
        now = time.time()
        k = 10 if self.last is None else int(np.clip(round((now - self.last) * 1000 / SLOT_MS), 1, 10))
        self.last = now
        r = _http("http://qeco-policy:8090/act", {"variant": self.variant, "obs": obs, "lstm": [lstm_now] * k})
        return r["action"], r["q"]


def predicted_tct(action, cond, iter, kb):
    """Simulator-model prediction for the chosen location (no queueing):
    local = fluid CFS formula, edge = RTT + D/B + T_comp(L) + overhead."""
    if action == 0:
        return local_tct_fluid_ms(iter)
    c = cond[action - 1]
    return edge_tct_ms(iter, kb, c["rtt"], c["bw"], c["load"])


def run_policy(bed, policy, n=30, iter=1_000_000, payload_kb=1, gap_mean_ms=200, seed=0, label="", warmup=1):
    """Run n tasks with one policy. Gaps between tasks are exponential (same sequence
    for every policy with the same seed). Returns one row per task."""
    rng = np.random.default_rng(seed)
    gaps = rng.exponential(gap_mean_ms, size=n + warmup) / 1000
    qeco = QecoClient(policy.split("-")[1]) if policy.startswith("QECO") else None
    if qeco:
        qeco.reset()
    rows = []
    for k in range(n + warmup):
        time.sleep(gaps[k])
        cond = bed.cond()
        q = None
        t_dec = time.time()
        if policy == "Oracle":
            res = [bed.run(t, iter, payload_kb * 1024) for t in TARGETS]
            tcts = [r["tct_ms"] if r["status"] == "ok" else math.inf for r in res]
            action = int(np.argmin(tcts))
            r = res[action]
            extra = {f"tct_{t}": v for t, v in zip(TARGETS, tcts)}
        else:
            if qeco:
                action, q = qeco.decide(cond, payload_kb)
            else:
                action = RULES[policy](cond, iter, payload_kb)
            r = bed.run(TARGETS[action], iter, payload_kb * 1024)
            extra = {}
        if k < warmup:
            continue
        est = model_greedy_estimates(cond, iter, payload_kb)
        rows.append({"ts_unix_ms": r["ts_unix_ms"], "label": label, "policy": policy, "task": k - warmup,
                     "iter": iter, "payload_kb": payload_kb, "gap_ms": round(gaps[k] * 1000, 1),
                     "action": action, "target": TARGETS[action], "tct_ms": r["tct_ms"],
                     "server_compute_ms": r.get("server_compute_ms"), "status": r["status"],
                     "decide_ms": round((time.time() - t_dec) * 1000 - r["tct_ms"], 1) if policy != "Oracle" else None,
                     "pred_tct_ms": round(predicted_tct(action, cond, iter, payload_kb), 1),
                     "est_local_ms": round(est[0], 1), "est_e1_ms": round(est[1], 1), "est_e2_ms": round(est[2], 1),
                     "q": json.dumps(q) if q else "",
                     **{f"obs_rtt{i + 1}": round(c["rtt"], 2) for i, c in enumerate(cond)},
                     **{f"obs_bw{i + 1}": c["bw"] for i, c in enumerate(cond)},
                     **{f"obs_load{i + 1}": round(c["load"], 3) for i, c in enumerate(cond)},
                     **extra})
    return pd.DataFrame(rows)
