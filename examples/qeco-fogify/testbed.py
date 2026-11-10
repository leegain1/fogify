"""Helpers for driving the Fogify testbed from the ui (Jupyter) container.

Topology (docker-compose.yaml):
    local (0.5 CPU) ──edge-server-net-1──▶ edge-server-1 (2.0 CPU)
                    └─edge-server-net-2──▶ edge-server-2 (2.0 CPU)

RTT = local-side delay (5 ms, fixed) + edge-server-side delay.
Bandwidth is always written in Mbit ("Mbps" means MB/s in tc / Fogify).
"""
import io
import re
import subprocess
import time

import pandas as pd

from FogifySDK import FogifySDK

LOCAL_SIDE_DELAY_MS = 5
SERVERS = {"edge-server-1": "http://edge-server-1:8080",
           "edge-server-2": "http://edge-server-2:8080"}

# CPU pinning (i5-1240P: CPUs 0-7 = 4 P-cores with HT, 8-15 = 8 E-cores in two
# clusters 8-11 / 12-15 that share L2 and clock). Each node gets its own physical
# cores; the two edge servers sit in different E-core clusters so stress on one
# cannot slow the other through the shared cluster. Fogify itself and the host
# keep the P-cores.
CPUSETS = {"local": "14", "edge-server-1": "8,9", "edge-server-2": "12,13"}

fogify = None


def connect(compose="docker-compose.yaml"):
    global fogify
    fogify = FogifySDK("http://controller:5000", compose)
    return fogify


def container(label):
    """Container ID of a Fogify node (e.g. 'local', 'edge-server-1')."""
    ids = subprocess.run(["docker", "ps", "-qf", f"name=fogify_{label}\\."],
                         capture_output=True, text=True, check=True).stdout.split()
    if not ids:
        raise RuntimeError(f"no container for {label}; deployed?")
    return ids[0]


def pin_cpus(cpusets=CPUSETS):
    """Swarm services cannot set cpuset, so pin the running task containers.
    The CPU quota (NanoCpus) set by Fogify stays as it is."""
    for label, cpus in cpusets.items():
        subprocess.run(["docker", "update", "--cpuset-cpus", cpus, container(label)],
                       capture_output=True, check=True)
    return {label: subprocess.run(["docker", "inspect", "-f", "{{.HostConfig.CpusetCpus}} {{.HostConfig.NanoCpus}}",
                                   container(label)], capture_output=True, text=True).stdout.strip()
            for label in cpusets}


def ping_ms(edge_server, count=5):
    out = subprocess.run(["docker", "exec", container("local"), "ping", "-c", str(count), "-q", edge_server],
                         capture_output=True, text=True).stdout
    m = re.search(r"= [\d.]+/([\d.]+)/", out)
    return float(m.group(1)) if m else float("nan")


def deploy(pin=True, timeout=300):
    fogify.deploy(timeout=timeout)
    # network rules are applied a few seconds after deploy -> wait until RTT shows up
    for _ in range(30):
        if ping_ms("edge-server-1") > 8 and ping_ms("edge-server-2") > 8:
            break
        time.sleep(2)
    return pin_cpus() if pin else None


def set_link(edge_server, rtt_ms=10, bandwidth="100Mbit"):
    """RTT / bandwidth between local and one edge server (edge side delay = RTT - 5 ms)."""
    network = "edge-server-net-" + edge_server.rsplit("-", 1)[1]
    delay = max(rtt_ms - LOCAL_SIDE_DELAY_MS, 0)
    fogify.update_network(edge_server, network,
                          {"bidirectional": {"bandwidth": bandwidth, "latency": {"delay": f"{delay}ms"}}})
    time.sleep(2)


def client_cmd(mode, iter, n, servers, payload, label, interval=None):
    cmd = ["docker", "exec", container("local"), "uvc-client", "run",
           "-mode", mode, "-iter", str(iter), "-n", str(n), "-payload", str(payload),
           "-label", label, "-servers", ",".join(SERVERS[s] for s in servers)]
    if interval:
        cmd += ["-interval", interval]
    return cmd


def run_tasks(mode, iter=1_000_000, n=30, servers=("edge-server-1",), payload=1024, label="", interval=None):
    """Run n tasks from the local node with a fixed mode; one row per task."""
    out = subprocess.run(client_cmd(mode, iter, n, servers, payload, label, interval),
                         capture_output=True, text=True, check=True).stdout
    return pd.read_csv(io.StringIO(out))


def stress(edge_server, cpu, duration):
    """cpu = percent of the node's CPU (Fogify: cpulimit --limit cpus*cpu -- stress --cpu ceil(cpus))."""
    fogify.stress(edge_server, duration=duration, cpu=cpu)
    time.sleep(3)


def wait_stress_done(edge_server):
    while subprocess.run(["docker", "exec", container(edge_server), "pgrep", "stress"],
                         capture_output=True).returncode == 0:
        time.sleep(2)


def p50_p95(df, by, col="tct_ms"):
    ok = df[df.status == "ok"]
    return ok.groupby(by)[col].agg(p50="median", p95=lambda s: s.quantile(0.95), n="count").round(2)
