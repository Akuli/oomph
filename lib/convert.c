#include <stdint.h>
#include <math.h>

int64_t meth_float_floor(double f) { return (int64_t)floor(f); }
int64_t meth_float_ceil(double f) { return (int64_t)ceil(f); }
int64_t meth_float_truncate(double f) { return (int64_t)f; }
int64_t meth_float_round(double f) { return (int64_t)round(f); }
