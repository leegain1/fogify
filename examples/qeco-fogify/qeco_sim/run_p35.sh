#!/bin/sh
# Phase 3.5: train QECO-orig / QECO-net / QECO-net+ on the closed-loop simulator, 3 seeds each,
# all in parallel (one container per run). Large tasks (64 / 256 KB) are 60% of the tasks,
# RTT log-uniform 5-250 ms. GAMMA=0 sh qeco_sim/run_p35.sh to set the discount factor.
#   sh qeco_sim/run_p35.sh        (from examples/qeco-fogify)
cd "$(dirname "$0")/.." || exit 1
for v in orig net netplus; do
  for s in 0 1 2; do
    out=results/P35_${v}_s${s}
    mkdir -p "$out"
    docker run -d --rm --name "p35_${v}_s${s}" -u 1000:1000 -e OMP_NUM_THREADS=1 -e TF_NUM_INTRAOP_THREADS=1 \
      -e TF_NUM_INTEROP_THREADS=1 -v "$PWD":/w -w /w/qeco_sim qeco-tf:0.1 \
      sh -c "python train.py --variant $v --seed $s --episodes 1000 --arrival closed --reward delay --gamma ${GAMMA:-0.9} --rtt-dist log \
             --payload-probs 0.2 0.2 0.3 0.3 --out ../$out > ../$out.log 2>&1"
  done
done
docker ps --filter name=p35_ --format '{{.Names}}'
