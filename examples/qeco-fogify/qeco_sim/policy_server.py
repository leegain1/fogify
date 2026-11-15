"""HTTP policy server for the trained QECO models (TensorFlow lives here, not in
the Fogify ui container).

    docker run -d --name qeco-policy --network fogemulator_default -u 1000:1000 \
        -v $PWD:/w -w /w/qeco_sim qeco-tf:0.1 python policy_server.py

    QECO_MODELS="QECO-net+=P35_netplus_s0,QECO-net=P35_net_s1" (run dirs in results/) selects
    the models; default: Phase 3 models as "orig" and "net".

    POST /reset {"model": "QECO-net+"}                     -> clear LSTM history
    POST /act   {"model": "QECO-net+", "obs": [...], "lstm": [[...], ...]}
    ("variant" is accepted instead of "model" for the Phase 4 calls)
         lstm = LSTM inputs observed since the last call (one per 10 ms slot, oldest first)
         -> {"action": 0|1|2, "q": [...]}
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from qeco_agent import QecoPolicy

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
SPEC = os.environ.get("QECO_MODELS", "orig=P3_orig,net=P3_net")
POLICIES = {name: QecoPolicy(os.path.join(RES, d)) for name, d in (kv.split("=", 1) for kv in SPEC.split(","))}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        pol = POLICIES[req.get("model", req.get("variant"))]
        if self.path == "/reset":
            pol.reset()
            out = {"ok": True}
        else:
            for l in req.get("lstm", []):
                pol.update_lstm(l)
            q = pol.q_values(req["obs"])
            out = {"action": int(q.argmax()), "q": [round(float(x), 4) for x in q]}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("policy server on :8090, models", {v: p.meta.get("best_episode") for v, p in POLICIES.items()}, flush=True)
    HTTPServer(("", 8090), Handler).serve_forever()
