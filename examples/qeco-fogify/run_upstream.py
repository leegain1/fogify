"""Phase 2: run upstream QECO main.py unchanged, in a separate run directory.

Only Config.N_EPISODE can be overridden (QECO_EPISODES env). The run directory
gets an empty models/ because upstream saves checkpoints there but its mkdir is
commented out.

    docker run --rm -v $PWD:/w -w /w -e QECO_EPISODES=1000 \
        qeco-tf:0.1 python run_upstream.py results/P2_upstream
"""
import os
import runpy
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__))
run_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "results/P2_upstream")
os.makedirs(os.path.join(run_dir, "models"), exist_ok=True)

sys.path.insert(0, os.path.join(here, "upstream"))
from Config import Config  # noqa: E402

if os.environ.get("QECO_EPISODES"):
    Config.N_EPISODE = int(os.environ["QECO_EPISODES"])
print("N_EPISODE =", Config.N_EPISODE, "-> run dir", run_dir, flush=True)

os.chdir(run_dir)
runpy.run_path(os.path.join(here, "upstream", "main.py"), run_name="__main__")
