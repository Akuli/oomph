#include "lib.h"
#include <float.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

void var_print(const struct String *s) { puts(s->str); }

void var_print_float(double f)
{
	// 0.25 --> "0.25", 0.1+0.2 --> "0.30000000000000004"
	char res[100];
	snprintf(res, sizeof res, "%.*f", DBL_DIG + 2, f);

	size_t n = strlen(res);
	while (n > 3 && res[n-1] == '0' && res[n-2] != '.')
		res[--n] = '\0';
	printf("%s\n", res);
}
