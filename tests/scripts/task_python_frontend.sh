#!/usr/bin/env bash
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

set -euxo pipefail

source tests/scripts/setup-pytest-env.sh
# to avoid openblas threading error
export TVM_BIND_THREADS=0
export OMP_NUM_THREADS=1

export TVM_TEST_TARGETS="llvm;cuda"

find . -type f -path "*.pyc" | xargs rm -f

# Rebuild cython
make cython3

# These tests are sharded into two sections in order to increase parallelism in CI.
# The split is purely based on balancing the runtime of each shard so they should
# be about the same. This may need rebalancing in the future if this is no longer
# the case.
function shard1 {
    echo "Running relay MXNet frontend test..."
    run_pytest cython python-frontend-mxnet tests/python/frontend/mxnet

    echo "Running relay ONNX frontend test..."
    run_pytest cython python-frontend-onnx tests/python/frontend/onnx

    echo "Running relay PyTorch frontend test..."
    run_pytest cython python-frontend-pytorch tests/python/frontend/pytorch
}

function shard2 {
    echo "Running relay Tensorflow frontend test..."
    # Note: Tensorflow tests often have memory issues, so invoke each one separately
    TENSORFLOW_TESTS=$(./tests/scripts/pytest_ids.py --folder tests/python/frontend/tensorflow)
    i=0
    for node_id in $TENSORFLOW_TESTS; do
        echo "$node_id"
        run_pytest cython "python-frontend-tensorflow-$i" "$node_id"
        i=$((i+1))
    done

    echo "Running relay DarkNet frontend test..."
    run_pytest cython python-frontend-darknet tests/python/frontend/darknet

    echo "Running relay PaddlePaddle frontend test..."
    run_pytest cython python-frontend-paddlepaddle tests/python/frontend/paddlepaddle

    echo "Running relay CoreML frontend test..."
    run_pytest cython python-frontend-coreml tests/python/frontend/coreml
}


if [ -z ${1+x} ]; then
    # TODO: This case can be removed once https://github.com/apache/tvm/pull/10413
    # is merged.
    # No sharding set, run everything
    shard1
    shard2
else
    if [ "$1" == "1" ]; then
        shard1
    else
        shard2
    fi
fi
