#!/bin/bash

# profiling stuff
#
#   $ sudo apt install valgrind
#   $ python3 -m pip install gprof2dot
#   $ path/to/this/file ./program arg1 arg2

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT

valgrind --tool=callgrind --callgrind-out-file=$dir/callgrind.out "$@"
gprof2dot $dir/callgrind.out --format=callgrind --output=$dir/graph.gvz
dot -Tpng $dir/graph.gvz -o $dir/perf.png
mv -v $dir/perf.png perf.png