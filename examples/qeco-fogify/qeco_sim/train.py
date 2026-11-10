"""Train QECO (upstream D3QN, unchanged) on the testbed-fitted environment.

Loop follows upstream main.py train(): one decision per slot with a task,
transition stored when the task's delay becomes known, learn every 10 steps
after step 200. Differences: one local device, reward uses delay only
(energy state = 1 in upstream QoE_Function), per-episode metrics go to a CSV.

    docker run --rm -u 1000:1000 -v $PWD:/w -w /w/qeco_sim qeco-tf:0.1 \
        python train.py --variant orig --episodes 1000 --out ../results/P3_orig
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "upstream"))
from Config import Config                         # noqa: E402  upstream hyperparameters
from D3QN import DuelingDoubleDeepQNetwork        # noqa: E402  upstream model, unchanged
from main import QoE_Function                     # noqa: E402  upstream reward
from mec_env import TestbedMEC                    # noqa: E402

MIN_MEMORY = 100
GAMMA = None     # set from --gamma (None = upstream 0.9)
DELAY_UNIT_MS = 100.0   # QoE uses delay in upstream slot units (0.1 s) so the reward scale stays comparable


REWARD = "qoe"   # set from --reward


def reward(env, slot):
    if REWARD == "delay":   # pure delay, scaled to ~ -1 per 100 ms (dropped task -> -max_delay)
        return -env.process_delay[slot] / DELAY_UNIT_MS
    delay = env.process_delay[slot] / DELAY_UNIT_MS
    max_delay = env.max_delay_ms / DELAY_UNIT_MS
    # energy state 1 -> cost = 2 * delay (energy terms are multiplied by 0)
    return QoE_Function(delay, max_delay, env.unfinish_task[slot], 1.0, 0.0, 0.0, [0.0], [0.0])


def make_agent(env):
    return DuelingDoubleDeepQNetwork(env.n_actions, env.n_features, env.n_lstm_state, env.n_time,
                                     learning_rate=Config.LEARNING_RATE,
                                     reward_decay=GAMMA if GAMMA is not None else Config.REWARD_DECAY,
                                     e_greedy=Config.E_GREEDY,
                                     replace_target_iter=Config.N_NETWORK_UPDATE,
                                     memory_size=Config.MEMORY_SIZE)


def run_episode(env, agent, episode, learn, rl_step, **reset_kw):
    """One episode; returns (rl_step, per-task records). learn=False -> greedy evaluation."""
    obs, lstm = env.reset(**reset_kw)
    history = {}
    rewarded = np.zeros(env.n_time, bool)
    while True:
        if obs.sum() == 0:
            action = 0
        else:
            action = agent.choose_action(obs)
        obs_, lstm_, done = env.step(action)
        agent.update_lstm(lstm_)
        slot = env.time_count - 1
        if env.arrive_kb[slot] > 0:
            history[slot] = (obs, lstm, action, obs_, lstm_)
        for s in np.where((~rewarded) & (env.process_delay > 0))[0]:
            if learn and s in history:
                o, l, a, o_, l_ = history[s]
                agent.store_transition(o, l, a, reward(env, s), o_, l_)
            rewarded[s] = True
        rl_step += 1
        obs, lstm = obs_, lstm_
        # upstream: rl_step > 200 with 20 UEs. With one device few transitions exist by
        # then and D3QN.learn() needs memory_counter > n_lstm_step, so wait for 100 stored.
        if learn and getattr(agent, "memory_counter", 0) >= MIN_MEMORY and rl_step % 10 == 0:
            agent.learn()
        if done:
            break
    slots = np.where(env.arrive_kb > 0)[0]
    records = [{"slot": int(s), "kb": float(env.arrive_kb[s]), "action": int(env.task_action[s]),
                "tct_ms": float(env.process_delay[s]), "unfinished": int(env.unfinish_task[s]),
                "qoe": float(reward(env, s)), "cond": env.task_cond[s]} for s in slots]
    return rl_step, records


VAL_EVERY, VAL_EPISODES, VAL_SEED = 25, 8, 1000


def validate(variant, agent):
    """Greedy mean TCT on fixed validation episodes (random, changing conditions;
    seeds differ from training and from eval_sim.py). DQN with the upstream
    learning rate oscillates, so the best checkpoint is kept, not the last one."""
    eps, hist = agent.epsilon, list(agent.lstm_history)
    agent.epsilon = 1.0
    tct = []
    for k in range(VAL_EPISODES):
        env = TestbedMEC(variant=variant, seed=VAL_SEED + k)
        agent.lstm_history.extend([np.zeros(agent.n_lstm_state)] * agent.n_lstm_step)
        _, rec = run_episode(env, agent, 0, False, 0)
        tct += [r["tct_ms"] for r in rec]
    agent.epsilon = eps
    agent.lstm_history.extend(hist)
    return float(np.mean(tct))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["orig", "net"], required=True)
    ap.add_argument("--episodes", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reward", choices=["qoe", "delay"], default="qoe")
    ap.add_argument("--gamma", type=float, default=None)
    args = ap.parse_args()
    global REWARD, GAMMA
    REWARD, GAMMA = args.reward, args.gamma
    os.makedirs(args.out, exist_ok=True)
    np.random.seed(args.seed)

    env = TestbedMEC(variant=args.variant, seed=args.seed)
    agent = make_agent(env)
    meta = {"variant": args.variant, "episodes": args.episodes, "seed": args.seed, "reward": args.reward,
            "gamma": GAMMA if GAMMA is not None else Config.REWARD_DECAY,
            "n_features": env.n_features, "n_lstm_state": env.n_lstm_state, "n_actions": env.n_actions,
            "n_time": env.n_time, "slot_ms": env.slot_ms, "max_delay_ms": env.max_delay_ms}
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=1)

    log = open(os.path.join(args.out, "train_log.csv"), "w")
    log.write("episode,tasks,qoe_avg,tct_avg_ms,tct_p95_ms,drops,share_local,share_e1,share_e2,epsilon,sec\n")
    vlog = open(os.path.join(args.out, "val_log.csv"), "w")
    vlog.write("episode,val_tct_ms,best\n")
    best = float("inf")
    rl_step, t0 = 0, time.time()
    for ep in range(args.episodes):
        rl_step, rec = run_episode(env, agent, ep, True, rl_step)
        if not rec:
            continue
        tct = np.array([r["tct_ms"] for r in rec])
        acts = np.array([r["action"] for r in rec])
        log.write(f"{ep},{len(rec)},{np.mean([r['qoe'] for r in rec]):.3f},{tct.mean():.2f},"
                  f"{np.percentile(tct, 95):.2f},{sum(r['unfinished'] for r in rec)},"
                  f"{(acts == 0).mean():.3f},{(acts == 1).mean():.3f},{(acts == 2).mean():.3f},"
                  f"{agent.epsilon:.3f},{time.time() - t0:.0f}\n")
        log.flush()
        if ep % 50 == 0:
            print(f"ep {ep} tct_avg {tct.mean():.1f} eps {agent.epsilon:.2f} {time.time() - t0:.0f}s", flush=True)
        if ep >= 100 and (ep + 1) % VAL_EVERY == 0:
            v = validate(args.variant, agent)
            if v < best:
                best = v
                agent.saver.save(agent.sess, os.path.join(args.out, "model", "model.ckpt"))
                meta["best_episode"], meta["best_val_tct_ms"] = ep, round(v, 2)
                json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=1)
            vlog.write(f"{ep},{v:.2f},{int(v == best)}\n"); vlog.flush()

    print("best", meta.get("best_episode"), meta.get("best_val_tct_ms"), args.out)


if __name__ == "__main__":
    main()
