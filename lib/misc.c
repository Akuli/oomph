#include "oomph.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdnoreturn.h>

noreturn void panic_printf(const char *fmt, ...)
{
	int er = errno;

	va_list ap;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (er)
		fprintf(stderr, " (errno %d: %s)", er, strerror(er));
	fputc('\n', stderr);

	fflush(stderr);
	abort();
}

void oomph_assert(bool cond, int64_t lineno)
{
	if (!cond)
		panic_printf("assert() failed on line %d", (int)lineno);
}

void oomph_main(void);
int main(void) {
	oomph_main();
	return 0;
}
