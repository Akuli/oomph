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

static int global_argc = -1;
static const char *const *global_argv = NULL;

int64_t argv_count(void)
{
	assert(global_argc != -1);
	return global_argc;
}

struct class_Str *argv_get(int64_t i)
{
	assert(global_argv != NULL);
	assert(0 <= i && i < global_argc);
	return cstr_to_string(global_argv[i]);
}


void oomph_main(void);
int main(int argc, char **argv) {
	global_argc = argc;
	global_argv = (const char*const*)argv;
	oomph_main();
	return 0;
}
