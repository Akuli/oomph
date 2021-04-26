#include "oomph.h"
#include <assert.h>
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef DBL_DECIMAL_DIG
#define DBL_DECIMAL_DIG 17  // TODO: what should be used instead? this is for tcc
#endif

int64_t meth_Float_floor(double f) { return (int64_t)floor(f); }
int64_t meth_Float_ceil(double f) { return (int64_t)ceil(f); }
int64_t meth_Float_truncate(double f) { return (int64_t)f; }
int64_t meth_Float_round(double f) { return (int64_t)round(f); }

struct String meth_Int_to_string(int64_t n)
{
	char s[100];
	snprintf(s, sizeof s, "%lld", (long long)n);
	return cstr_to_string(s);
}

struct String meth_Float_to_string(double d)
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

int64_t meth_Str_to_int(struct String s)
{
	char *cstr = string_to_cstr(s);
	char *endptr;
	errno = 0;
	long long res = strtoll(cstr, &endptr, 10);
	if (errno != 0 || endptr != cstr + s.nbytes)
		panic_printf_errno("not a valid integer: %s", cstr);

	free(cstr);
	return res;
}

double meth_Str_to_float(struct String s)
{
	char *cstr = string_to_cstr(s);
	char *endptr;
	errno = 0;
	double res = strtod(cstr, &endptr);
	if (errno != 0 || endptr != cstr + s.nbytes)
		panic_printf_errno("not a valid integer: %s", cstr);

	free(cstr);
	return res;
}

int64_t oomph_int_mod(int64_t a, int64_t b)
{
	int64_t res = a % b;
	// Make sure result has same sign as b
	if ((b > 0 && res < 0) || (b < 0 && res > 0))
		res += b;
	return res;
}

double oomph_float_mod(double a, double b)
{
	double res = fmod(a, b);
	if ((b > 0 && res < 0) || (b < 0 && res > 0))
		res += b;
	return res;
}
