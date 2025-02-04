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
# pylint: disable=unused-argument
"""cuBLAS Relay integration."""
from typing import Callable, List, Tuple, Dict, Optional

import tvm
import tvm.ir
from tvm import relay
from tvm import te
from tvm.relay import transform
from tvm.contrib import cublas

from ...dataflow_pattern import is_op, wildcard
from .register import register_pattern_table


def partition_for_cublas(
    mod: tvm.IRModule, params: Optional[Dict[str, tvm.runtime.NDArray]] = None
) -> tvm.IRModule:
    """Partition the graph to offload for cuBLAS.

    Parameters
    ----------
    mod : tvm.IRModule
        The module to partition.
    params : Optional[Dict[str, tvm.runtime.NDArray]]
        Constant input parameters.

    Returns
    -------
    tvm.IRModule
        The partitioned module.
    """

    seq = tvm.transform.Sequential(
        [
            transform.InferType(),
            transform.MergeComposite(pattern_table()),
            transform.AnnotateTarget("cublas"),
            transform.PartitionGraph(),
            transform.InferType(),
        ]
    )
    return seq(mod)


@register_pattern_table("cublas")
def pattern_table() -> List[Tuple[str, relay.Pattern, Callable[[relay.Call], bool]]]:
    """Get the cuBLAS pattern table."""

    def matmul_pattern() -> relay.Pattern:
        """Create pattern for matmul."""
        return is_op("nn.matmul")(wildcard(), wildcard())

    def batch_matmul_pattern() -> relay.Pattern:
        """Create pattern for batch_matmul."""
        return is_op("nn.batch_matmul")(wildcard(), wildcard())

    def dense_pattern() -> relay.Pattern:
        """Create pattern for dense."""
        return is_op("nn.dense")(wildcard(), wildcard())

    def check_matmul_like(matched: relay.Call) -> bool:
        """Check if matmul is supported by cuBLAS."""
        # Input data types can't be mixed
        if matched.args[0].checked_type.dtype != matched.args[1].checked_type.dtype:
            return False

        in_dtype = matched.args[0].checked_type.dtype
        out_dtype = matched.checked_type.dtype
        # Only the following data type combinations are supported
        if (in_dtype, out_dtype) not in [
            ("float32", "float32"),
            ("float16", "float16"),
            ("float16", "float32"),
            ("int8", "int32"),
            ("float64", "float64"),
            ("int8", "float32"),
        ]:
            return False

        # If inputs are int8, input column strides must be a multiple of 4
        if in_dtype == "int8":
            if (
                matched.args[0].checked_type.shape[-1] % 4 != 0
                or matched.args[1].checked_type.shape[-1] % 4 != 0
            ):
                return False

        return True

    return [
        ("cublas.matmul", matmul_pattern(), check_matmul_like),
        ("cublas.batch_matmul", batch_matmul_pattern(), check_matmul_like),
        ("cublas.dense", dense_pattern(), check_matmul_like),
    ]


_LowerFunc = Callable[[relay.Call, List[te.Tensor]], te.Tensor]
_LOWER_MAP: Dict[str, _LowerFunc] = {}


def _lower_composite(comp_name: str) -> Callable[[_LowerFunc], _LowerFunc]:
    """Register a lowering function for a given composite function name."""

    def _register(f: _LowerFunc) -> _LowerFunc:
        _LOWER_MAP[comp_name] = f
        return f

    return _register


@tvm._ffi.register_func("relay.ext.cublas")
def relay_to_runtime(partition: relay.Function) -> tvm.runtime.Module:
    """Compile cuBLAS Relay functions to a runtime module."""
    assert isinstance(partition, relay.Function)
    assert isinstance(partition.body, relay.Call)
    assert isinstance(partition.body.op, relay.Function)

    global_name = str(partition.attrs.global_symbol)
    target = tvm.target.cuda()
    comp_func = partition.body.op
    comp_name = comp_func.attrs["Composite"]
    assert comp_name in _LOWER_MAP
    assert isinstance(comp_func.body, relay.Call)

    op = comp_func.body
    inputs = []
    for i, param in enumerate(comp_func.params):
        inputs.append(
            te.placeholder(
                param.checked_type.shape,
                name=f"input_{i}",
                dtype=param.checked_type.dtype,
            )
        )

    output = _LOWER_MAP[comp_name](op, inputs)
    prim_func = te.create_prim_func(inputs + [output])
    return tvm.build(prim_func, target=target, name=global_name)


@_lower_composite("cublas.matmul")
def _lower_matmul(op: relay.Call, inputs: List[te.Tensor]) -> te.Tensor:
    """Lower a matmul using cuBLAS."""
    return cublas.matmul(
        inputs[0],
        inputs[1],
        transa=op.attrs["transpose_a"],
        transb=op.attrs["transpose_b"],
        dtype=op.checked_type.dtype,
    )


@_lower_composite("cublas.batch_matmul")
def _lower_batch_matmul(op: relay.Call, inputs: List[te.Tensor]) -> te.Tensor:
    """Lower a batch_matmul using cuBLAS."""
    return cublas.batch_matmul(
        inputs[0],
        inputs[1],
        transa=op.attrs["transpose_a"],
        transb=op.attrs["transpose_b"],
        dtype=op.checked_type.dtype,
    )


@_lower_composite("cublas.dense")
def _lower_dense(op: relay.Call, inputs: List[te.Tensor]) -> te.Tensor:
    """Lower a dense using cuBLAS."""
    return cublas.matmul(
        inputs[0], inputs[1], transa=False, transb=True, dtype=op.checked_type.dtype
    )
