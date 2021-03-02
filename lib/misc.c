#include "lib.h"
#include <stdio.h>

void var_assert(bool cond, int64_t lineno)
{
	if (!cond) {
		fprintf(stderr, "assert() failed on line %d\n", (int)lineno);
		fflush(stderr);
		abort();
	}
}

void var_print(const struct class_Str *s)
{
	puts(s->str);
}

void var_main(void);
int main(void) {
	var_main();
	return 0;
}
