#include "oomph.h"
#include <stdlib.h>

struct RefHeader { REFCOUNT_HEADER };

void incref(void *ptr)
{
	if (ptr) {
		struct RefHeader *hdr = ptr;
		if (hdr->refcount >= 0)
			hdr->refcount++;
	}
}

void decref(void *ptr, void (*destructor)(void *ptr))
{
	if (ptr) {
		struct RefHeader *hdr = ptr;
		if (hdr->refcount > 0 && --hdr->refcount == 0)
			destructor(ptr);
	}
}

void run_destroy_callbacks(struct DestroyCallback *cblist)
{
	if (cblist) {
		for (size_t i = 0; cblist[i].func; i++)
			cblist[i].func(cblist[i].arg);
	}
	free(cblist);
}
