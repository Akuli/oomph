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

struct class_Str *meth_int_to_string(int64_t n)
{
	char s[100];
	snprintf(s, sizeof s, "%lld", (long long)n);
	return cstr_to_string(s);
}

struct class_Str *meth_float_to_string(double d)
{
	char res[100];
	snprintf(res, sizeof res, "%g", d);
	if (!strchr(res, '.')) {
		// e.g. 69.0 instead of 69
		snprintf(res, sizeof res, "%.1f", d);
	} else if (atof(res) != d) {
		// Tricky float, e.g. 0.1 + 0.2, display the truth to user
		snprintf(res, sizeof res, "%.*f", DBL_DECIMAL_DIG, d);
	}
	return cstr_to_string(res);
}

int64_t meth_Str_to_int(const struct class_Str *s)
{
	char *endptr;
	errno = 0;
	long long res = strtoll(s->str, &endptr, 10);
	assert(errno == 0 && endptr == s->str + strlen(s->str));  // TODO: exceptions or optionals
	return res;
}

double meth_Str_to_float(const struct class_Str *s)
{
	char *endptr;
	errno = 0;
	double res = strtod(s->str, &endptr);
	assert(errno == 0 && endptr == s->str + strlen(s->str));  // TODO: exceptions or optionals
	return res;
}

int64_t int_mod(int64_t a, int64_t b)
{
	int64_t res = a % b;
	// Make sure result has same sign as b
	if ((b > 0 && res < 0) || (b < 0 && res > 0))
		res += b;
	return res;
}

double float_mod(double a, double b)
{
	double res = fmod(a, b);
	if ((b > 0 && res < 0) || (b < 0 && res > 0))
		res += b;
	return res;
}
