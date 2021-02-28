#include "lib.h"
#include <assert.h>
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

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

struct String *meth_float_to_string(double d)
{
	// 0.1+0.2 --> "0.30000000000000004"
	char res[100];
	snprintf(res, sizeof res, "%.*f", DBL_DIG + 2, d);

	// 0.25 --> "0.25"
	size_t n = strlen(res);
	while (n > 3 && res[n-1] == '0' && res[n-2] != '.')
		res[--n] = '\0';

	return cstr_to_string(res);
}

int64_t meth_string_to_int(const struct String *s)
{
	char *endptr;
	errno = 0;
	long long res = strtoll(s->str, &endptr, 10);

	// TODO: exceptions or optionals
	assert(!((res == LLONG_MIN || res == LLONG_MAX) && errno == ERANGE));
	assert(endptr == s->str + strlen(s->str));
	return res;
}
