#include "oomph.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

// TODO: this is copy/pasted from generated c code, not ideal
struct class_List_Str {
	REFCOUNT_HEADER
	int64_t len;
	int64_t alloc;
	struct class_Str smalldata[8];
	struct class_Str *data;
};

int64_t oomph_run_subprocess(void *args)
{
	struct class_List_Str *arglst = args;

	char **argarr = malloc(sizeof(argarr[0]) * (arglst->len + 1));
	assert(argarr);
	for (int i = 0; i < arglst->len; i++)
		argarr[i] = string_to_cstr(arglst->data[i]);
	argarr[arglst->len] = NULL;

	pid_t pid = fork();
	switch(pid) {
		case -1:
			panic_printf_errno("fork() failed");
		case 0:  // child
			execvp(argarr[0], argarr);
			// It shouldn't return, if it returns anyway then it failed
			panic_printf_errno("execvp() failed");
		default:  // parent
			break;
	}

	for (int i = 0; i < arglst->len; i++)
		free(argarr[i]);
	free(argarr);
	int wstatus;
	if (waitpid(pid, &wstatus, 0) <= 0)
		panic_printf("waitpid() failed");
	// TODO: represent signals etc nicely
	return WIFEXITED(wstatus) ? WEXITSTATUS(wstatus) : -1;
}

noreturn void oomph_exit(int64_t status)
{
	exit((int)status);
}

noreturn void panic_printf_errno(const char *fmt, ...)
{
	int er = errno;

	// Make sure that what is printed here goes after everything else
	fflush(stdout);
	fflush(stderr);

	va_list ap;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (er)
		fprintf(stderr, " (errno %d: %s)", er, strerror(er));
	fputc('\n', stderr);

	exit(1);
}

void oomph_assert(bool cond, struct class_Str path, int64_t lineno)
{
	if (!cond)
		panic_printf("assert() failed in \"%s\", line %d", string_to_cstr(path), (int)lineno);
}

static int global_argc = -1;
static const char *const *global_argv = NULL;

int64_t oomph_argv_count(void)
{
	assert(global_argc != -1);
	return global_argc;
}

struct class_Str oomph_argv_get(int64_t i)
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
