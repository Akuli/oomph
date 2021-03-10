#include "oomph.h"
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>

// TODO: this is copy/pasted from generated c code, not ideal
struct class_List_Str {
	REFCOUNT_HEADER
	int64_t len;
	int64_t alloc;
	struct class_Str * smalldata[8];
	struct class_Str * *data;
};

int64_t subprocess_run(void *args)
{
	struct class_List_Str *arglst = args;

	char **argarr = malloc(sizeof(argarr[0]) * (arglst->len + 1));
	assert(argarr);
	for (int i = 0; i < arglst->len; i++)
		argarr[i] = arglst->data[i]->str;
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

	free(argarr);
	int wstatus;
	if (waitpid(pid, &wstatus, 0) <= 0)
		panic_printf("waitpid() failed");
	// TODO: represent signals etc nicely
	return WIFEXITED(wstatus) ? WEXITSTATUS(wstatus) : -1;
}
