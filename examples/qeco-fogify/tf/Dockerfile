# Runtime for QECO. Upstream code uses the TF1 API through tensorflow.compat.v1
# and calls tf.compat.v1.* on that module (D3QN.py:86), which only exists in TF 2.x.
# Upstream requirements.txt pins tensorflow 2.8.0, so use that.
FROM tensorflow/tensorflow:2.8.0
RUN pip install --no-cache-dir "matplotlib==3.5.3" "pandas==1.4.4"
ENV MPLBACKEND=Agg HOME=/tmp CUDA_VISIBLE_DEVICES="" TF_CPP_MIN_LOG_LEVEL=2
