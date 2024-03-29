#include "oomph.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <spawn.h>
#include <sys/types.h>
#include <sys/wait.h>

// TODO: copy/pasted from generated c code, not ideal
// ------------ copy/pasta BEGIN
struct StringList {
	REFCOUNT_HEADER
	int64_t len;
	int64_t alloc;
	struct String smalldata[8];
	struct String *data;
};
struct AtExitFunction {
	REFCOUNT_HEADER
	void (*func)(void *);
	void *data;
	struct DestroyCallback cblist[];
};
static void at_exit_function_dtor(void *ptr)
{
	struct AtExitFunction *obj = ptr;
	for (const struct DestroyCallback *cb = obj->cblist; cb->func; cb++)
		cb->func(cb->arg);
	free(obj);
}
// ------------ copy/pasta END

extern char **environ;

int64_t oomph_run_subprocess(void *args)
{
	struct StringList *arglst = args;
	assert(arglst->len != 0);

	char **argarr = malloc(sizeof(argarr[0]) * (arglst->len + 1));
	assert(argarr);
	for (int i = 0; i < arglst->len; i++)
		argarr[i] = string_to_cstr(arglst->data[i]);
	argarr[arglst->len] = NULL;

	pid_t pid;
	int ret = posix_spawnp(&pid, argarr[0], NULL, NULL, argarr, environ);
	if (ret != 0) {
		errno = ret;
		panic_printf_errno("posix_spawnp() failed");
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

void oomph_assert(bool cond, struct String path, int64_t lineno)
{
	if (!cond)
		panic_printf("assert() failed in \"%s\", line %d", string_to_cstr(path), (int)lineno);
}

static int global_argc = -1;
static const char *const *global_argv = NULL;

noreturn void panic_printf_errno(const char *fmt, ...)
{
	int er = errno;

	// Make sure that what is printed here goes after everything else
	fflush(stdout);
	fflush(stderr);

	assert(global_argc != -1);
	fprintf(stderr, "%s: ", global_argv[0]);

	va_list ap;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (er)
		fprintf(stderr, " (errno %d: %s)", er, strerror(er));
	fputc('\n', stderr);

	exit(1);
}

int64_t oomph_argv_count(void)
{
	assert(global_argc != -1);
	return global_argc;
}

struct String oomph_argv_get(int64_t i)
{
	assert(global_argv != NULL);
	assert(0 <= i && i < global_argc);
	return cstr_to_string(global_argv[i]);
}

static struct AtExitFunction *atexit_callbacks[100] = {0};
static size_t atexit_callbacks_len = 0;

void oomph_run_at_exit(void *func)
{
	if (atexit_callbacks_len >= sizeof(atexit_callbacks)/sizeof(atexit_callbacks[0]))
		panic_printf("too many run_at_exit() calls");
	atexit_callbacks[atexit_callbacks_len++] = func;
	incref(func);
}

static void atexit_callback(void)
{
	for (size_t i = 0; i < atexit_callbacks_len; i++) {
		struct AtExitFunction *f = atexit_callbacks[i];
		f->func(f->data);
		at_exit_function_dtor(f);
	}
}

void oomph_main(void);
int main(int argc, char **argv) {
	global_argc = argc;
	global_argv = (const char*const*)argv;
	atexit(atexit_callback);
	oomph_main();
	return 0;
}
