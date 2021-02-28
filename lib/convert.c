#include "lib.h"
#include <stdint.h>
#include <stdio.h>
#include <math.h>

int64_t meth_float_floor(double f) { return (int64_t)floor(f); }
int64_t meth_float_ceil(double f) { return (int64_t)ceil(f); }
int64_t meth_float_truncate(double f) { return (int64_t)f; }
int64_t meth_float_round(double f) { return (int64_t)round(f); }

struct String *meth_int_to_string(int64_t n)
{
	char s[100];
	snprintf(s, sizeof s, "%lld", (long long)n);
	return cstr_to_string(s);
}
