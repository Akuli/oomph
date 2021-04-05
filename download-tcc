#!/bin/bash
set -ex

rm -rf tinycc
git clone https://github.com/TinyCC/tinycc/
cd tinycc
git checkout aa77279

# For some reason, it has to be 'make install'ed somewhere, doesn't matter where
./configure --prefix=$PWD/build
make -j2
make install
