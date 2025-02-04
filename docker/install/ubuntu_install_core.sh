#!/bin/bash
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

set -e
set -u
set -o pipefail

# install libraries for building c++ core on ubuntu
apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    cmake \
    curl \
    g++ \
    gdb \
    git \
    google-mock \
    graphviz \
    libcurl4-openssl-dev \
    libgtest-dev \
    libopenblas-dev \
    libssl-dev \
    libtinfo-dev \
    libz-dev \
    lsb-core \
    make \
    ninja-build \
    parallel \
    pkg-config \
    sudo \
    unzip \
    wget \


# Get Ubuntu version
release=$(lsb_release -r)
version_number=$(cut -f2 <<< "$release")

if [ "$version_number" == "20.04" ]; then
  # Single package source (Ubuntu 20.04)
  # googletest is installed via libgtest-dev
  cd /usr/src/googletest && cmake CMakeLists.txt && make && cp -v lib/*.a /usr/lib
elif [ "$version_number" == "18.04" ]; then
  # Single package source (Ubuntu 18.04)
  # googletest is installed via libgtest-dev
  cd /usr/src/googletest && cmake CMakeLists.txt && make && cp -v {googlemock,googlemock/gtest}/*.a /usr/lib
else
  # Split source package (Ubuntu 16.04)
  # libgtest-dev and google-mock
  cd /usr/src/gtest && cmake CMakeLists.txt && make && cp -v *.a /usr/lib
  cd /usr/src/gmock && cmake CMakeLists.txt && make && cp -v *.a /usr/lib
fi
