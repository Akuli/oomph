#include "lib.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>

void var_print_int(int64_t x)
{
	printf("%lld\n", (long long)x);
}

void var_print_bool(bool b)
{
	puts(b ? "true" : "false");
}
