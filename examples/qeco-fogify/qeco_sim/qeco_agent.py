"""Load a trained QECO model (upstream D3QN) for greedy inference."""
import json
import os
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "upstream"))
from D3QN import DuelingDoubleDeepQNetwork  # noqa: E402


class QecoPolicy:
    def __init__(self, model_dir):
        self.meta = json.load(open(os.path.join(model_dir, "meta.json")))
        m = self.meta
        self.agent = DuelingDoubleDeepQNetwork(m["n_actions"], m["n_features"], m["n_lstm_state"], m["n_time"])
        self.agent.saver.restore(self.agent.sess, os.path.join(model_dir, "model", "model.ckpt"))
        self.agent.epsilon = 1.0          # always greedy
        self.reset()

    def reset(self):
        a = self.agent
        a.lstm_history = deque([np.zeros(a.n_lstm_state) for _ in range(a.n_lstm_step)], maxlen=a.n_lstm_step)

    def update_lstm(self, lstm):
        self.agent.update_lstm(np.asarray(lstm, dtype=float))

    def q_values(self, obs):
        a = self.agent
        lstm = np.array(a.lstm_history).reshape(1, a.n_lstm_step, a.n_lstm_state)
        return a.sess.run(a.q_eval, {a.s: np.asarray(obs, dtype=float)[np.newaxis, :], a.lstm_s: lstm})[0]

    def act(self, obs):
        return int(np.argmax(self.q_values(obs)))
