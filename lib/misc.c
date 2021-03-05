#include "oomph.h"
#include <stdio.h>

void oomph_assert(bool cond, int64_t lineno)
{
	if (!cond) {
		fprintf(stderr, "assert() failed on line %d\n", (int)lineno);
		fflush(stderr);
		abort();
	}
}

void oomph_print(const struct class_Str *s)
{
	puts(s->str);
}

void oomph_main(void);
int main(void) {
	oomph_main();
	return 0;
}
