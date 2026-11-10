"""QECO-style MEC environment fitted to the Fogify testbed.

Differences from upstream MEC_Env.py (see research-docs/qeco-fogify/phase3-sim.md):
  - one local device (the testbed has one), two edge servers
  - time: decision slot 10 ms (upstream 100 ms); physics runs in 1 ms ticks
  - local CPU: CFS quota 50 ms / 100 ms (Docker --cpus 0.5) instead of a constant rate
  - offloading: transfer D/B_i + RTT_i (upstream: size / constant rate, no RTT)
  - per edge server: its own RTT_i, B_i and background CPU load L_i, which change
    during an episode (upstream: one constant rate, load = number of UEs sharing it)
  - t_ue_tran is updated (upstream MEC_Env.py:510 writes it into t_ue_comp)

Actions: 0 = local, 1 = edge-server-1, 2 = edge-server-2 (same as upstream).
State (variant "orig", same layout as upstream):
  [task size, local queue (slots), transmit queue (slots), edge backlog x n_edge, energy state = 1]
State (variant "net"): orig + [RTT_i / 100 ms] + [log10(B_i Mbit) / 2] + [L_i]
LSTM input: "orig" = own active tasks per edge server (upstream edge_ue_m),
            "net"  = L_i (edge server CPU load).
"""
import math

import numpy as np

from testbed_model import (CFS_PERIOD_MS, EDGE_CORES, EDGE_OVERHEAD_MS, EDGE_WORK_MS, ITER_REF,
                           LOCAL_QUOTA_MS, LOCAL_WORK_MS, edge_speed)

SIZE_UNIT_KB = 64.0  # task size feature = payload / 64 KB (1 KB .. 256 KB -> 0.016 .. 4, upstream sizes are 1..7)

# Ranges for domain randomization (cover Phase 5 scenarios S1-S4)
RTT_RANGE_MS = (10.0, 250.0)
BW_CHOICES_MBIT = (1.0, 3.0, 10.0, 30.0, 100.0)
LOAD_RANGE = (0.0, 0.9)
PAYLOAD_CHOICES_KB = (1.0, 16.0, 64.0, 256.0)


class TestbedMEC:
    def __init__(self, variant="orig", n_edge=2, slot_ms=10, n_slots=1000, max_delay_ms=3000,
                 arrive_prob=0.03, change_prob=1 / 200, iter=ITER_REF, seed=None):
        assert variant in ("orig", "net")
        self.variant, self.n_edge = variant, n_edge
        self.slot_ms, self.n_slots = slot_ms, n_slots
        self.max_delay_ms = max_delay_ms
        self.max_delay_slots = int(math.ceil(max_delay_ms / slot_ms))
        self.n_time = n_slots + self.max_delay_slots
        self.arrive_prob, self.change_prob, self.iter = arrive_prob, change_prob, iter
        self.rng = np.random.default_rng(seed)

        self.n_actions = 1 + n_edge
        self.n_features = 4 + n_edge + (3 * n_edge if variant == "net" else 0)
        self.n_lstm_state = n_edge

    # ---------------------------------------------------------------- conditions
    def sample_condition(self):
        load = 0.0 if self.rng.random() < 0.4 else self.rng.uniform(*LOAD_RANGE)
        return {"rtt": float(self.rng.uniform(*RTT_RANGE_MS)),
                "bw": float(self.rng.choice(BW_CHOICES_MBIT)),
                "load": float(load)}

    def _maybe_change(self):
        if self.fixed or self.rng.random() >= self.change_prob:
            return
        i = self.rng.integers(self.n_edge)
        key = self.rng.choice(["rtt", "bw", "load"])
        self.cond[i][key] = self.sample_condition()[key]

    # ---------------------------------------------------------------- episode
    def reset(self, conditions=None, payloads=None, arrivals=None):
        """conditions: list of dicts {rtt, bw, load} per edge server (fixed for the
        episode) or None for random, changing conditions. payloads / arrivals let an
        evaluation replay the same task sequence for every policy."""
        self.fixed = conditions is not None
        self.cond = [dict(c) for c in conditions] if self.fixed else [self.sample_condition() for _ in range(self.n_edge)]
        if arrivals is None:
            arrivals = self.rng.random(self.n_slots) < self.arrive_prob
        if payloads is None:
            payloads = self.rng.choice(PAYLOAD_CHOICES_KB, size=self.n_slots)
        self.arrive_kb = np.zeros(self.n_time)
        self.arrive_kb[:self.n_slots] = np.where(arrivals, payloads, 0.0)

        self.time_count = 0
        self.now_ms = 0.0
        self.phase_ms = float(self.rng.uniform(0, CFS_PERIOD_MS))  # CFS period phase
        self.quota = LOCAL_QUOTA_MS
        self.local_q, self.tx_q = [], []
        self.in_flight = []                          # (arrive_at_edge_ms, task)
        self.edge_active = [[] for _ in range(self.n_edge)]
        self.returning = []                          # (done_ms, task)
        self.process_delay = np.zeros(self.n_time)   # ms, set when a task finishes or is dropped
        self.unfinish_task = np.zeros(self.n_time)
        self.task_action = -np.ones(self.n_time)
        self.task_cond = [None] * self.n_time
        self.drop_count = 0
        return self._observe()

    def _task(self, slot, kb, action):
        work_scale = self.iter / ITER_REF
        return {"slot": slot, "t0": slot * self.slot_ms, "kb": kb, "action": action,
                "edge": action - 1, "local_work": LOCAL_WORK_MS * work_scale,
                "edge_work": EDGE_WORK_MS * work_scale, "bits": kb * 1024 * 8}

    def _finish(self, task, t_ms):
        delay = t_ms - task["t0"]
        if delay > self.max_delay_ms:
            delay, unfinished = self.max_delay_ms, 1
        else:
            unfinished = 0
        self.process_delay[task["slot"]] = delay
        self.unfinish_task[task["slot"]] = unfinished

    # ---------------------------------------------------------------- physics
    def _period_pos(self, t):
        return (t + self.phase_ms) % CFS_PERIOD_MS

    def _tick(self, t):
        """Advance 1 ms starting at absolute time t."""
        if self._period_pos(t) < 1.0:  # new CFS period starts in this tick
            self.quota = LOCAL_QUOTA_MS
        # local CPU (FIFO, quota limited)
        if self.local_q and self.quota > 0:
            task = self.local_q[0]
            run = min(1.0, self.quota, task["local_work"])
            task["local_work"] -= run
            self.quota -= run
            if task["local_work"] <= 1e-9:
                self.local_q.pop(0)
                self._finish(task, t + run)
        # uplink (FIFO serialization; propagation is a pure delay)
        if self.tx_q:
            task = self.tx_q[0]
            c = self.cond[task["edge"]]
            rate = c["bw"] * 1000.0  # bits per ms
            if task["bits"] <= rate:
                frac = task["bits"] / rate
                task["bits"] = 0.0
                self.tx_q.pop(0)
                self.in_flight.append((t + frac + c["rtt"] / 2, task))
            else:
                task["bits"] -= rate
        # arrivals at edge servers
        still = []
        for at, task in self.in_flight:
            if at < t + 1.0:
                self.edge_active[task["edge"]].append(task)
            else:
                still.append((at, task))
        self.in_flight = still
        # edge servers (processor sharing over EDGE_CORES, slowed by background load)
        for i, active in enumerate(self.edge_active):
            if not active:
                continue
            speed = edge_speed(self.cond[i]["load"]) * min(1.0, EDGE_CORES / len(active))
            for task in list(active):
                if task["edge_work"] <= speed:
                    frac = task["edge_work"] / speed
                    task["edge_work"] = 0.0
                    active.remove(task)
                    self.returning.append((t + frac + self.cond[i]["rtt"] / 2 + EDGE_OVERHEAD_MS, task))
                else:
                    task["edge_work"] -= speed
        # results back at the local device
        still = []
        for at, task in self.returning:
            if at < t + 1.0:
                self._finish(task, at)
            else:
                still.append((at, task))
        self.returning = still

    def _busy(self):
        return bool(self.local_q or self.tx_q or self.in_flight or self.returning
                    or any(self.edge_active))

    def _drop_late(self, t):
        """Drop tasks older than max_delay (upstream: process_delay = MAX_DELAY, unfinished)."""
        def late(task):
            return t - task["t0"] > self.max_delay_ms
        for q in (self.local_q, self.tx_q):
            for task in [x for x in q if late(x)]:
                q.remove(task); self._drop(task)
        for lst in (self.in_flight, self.returning):
            for item in [x for x in lst if late(x[1])]:
                lst.remove(item); self._drop(item[1])
        for active in self.edge_active:
            for task in [x for x in active if late(x)]:
                active.remove(task); self._drop(task)

    def _drop(self, task):
        self.process_delay[task["slot"]] = self.max_delay_ms
        self.unfinish_task[task["slot"]] = 1
        self.drop_count += 1

    # ---------------------------------------------------------------- RL interface
    def step(self, action):
        """Apply the action for the task arriving in the current slot (ignored if none),
        simulate one slot, and return the next observation."""
        slot = self.time_count
        kb = self.arrive_kb[slot]
        if kb > 0:
            a = int(action)
            task = self._task(slot, kb, a)
            self.task_action[slot] = a
            self.task_cond[slot] = [dict(c) for c in self.cond]
            (self.local_q if a == 0 else self.tx_q).append(task)

        t_end = self.now_ms + self.slot_ms
        if self._busy():
            t = self.now_ms
            while t < t_end - 1e-9:
                self._tick(t)
                t += 1.0
            self._drop_late(t_end)
        else:  # idle: only the CFS quota needs updating
            if self._period_pos(self.now_ms) + self.slot_ms >= CFS_PERIOD_MS:
                self.quota = LOCAL_QUOTA_MS
        self.now_ms = t_end
        self.time_count += 1
        self._maybe_change()

        done = self.time_count >= self.n_time
        if done:  # anything still running is unfinished (upstream does the same)
            for slot_i in np.where((self.arrive_kb > 0) & (self.process_delay == 0))[0]:
                self.process_delay[slot_i] = self.max_delay_ms
                self.unfinish_task[slot_i] = 1
        obs, lstm = self._observe() if not done else (np.zeros(self.n_features), self._lstm())
        return obs, lstm, done

    def _lstm(self):
        if self.variant == "net":
            return np.array([c["load"] for c in self.cond])
        own = np.zeros(self.n_edge)
        for i, active in enumerate(self.edge_active):
            own[i] = len(active)
        for _, task in self.in_flight:
            own[task["edge"]] += 1
        return own

    def _observe(self):
        lstm = self._lstm()
        kb = self.arrive_kb[self.time_count] if self.time_count < self.n_time else 0
        if kb == 0:
            return np.zeros(self.n_features), lstm
        local_wait = sum(t["local_work"] for t in self.local_q) / (LOCAL_QUOTA_MS / CFS_PERIOD_MS) / self.slot_ms
        tx_wait = sum(t["bits"] / (self.cond[t["edge"]]["bw"] * 1000.0) for t in self.tx_q) / self.slot_ms
        backlog = np.zeros(self.n_edge)
        for i, active in enumerate(self.edge_active):
            backlog[i] += sum(t["edge_work"] for t in active)
        for _, task in self.in_flight:
            backlog[task["edge"]] += task["edge_work"]
        for t in self.tx_q:
            backlog[t["edge"]] += t["edge_work"]
        obs = [kb / SIZE_UNIT_KB, local_wait, tx_wait, *(backlog / self.slot_ms), 1.0]
        if self.variant == "net":
            obs += [c["rtt"] / 100.0 for c in self.cond]
            obs += [math.log10(c["bw"]) / 2.0 for c in self.cond]
            obs += [c["load"] for c in self.cond]
        return np.array(obs, dtype=float), lstm
