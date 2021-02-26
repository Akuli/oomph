#include "lib.h"
#include <stdlib.h>

struct RefHeader { REFCOUNT_HEADER };

void incref(void *ptr)
{
	struct RefHeader *hdr = ptr;
	hdr->refcount++;
}

void decref(void *ptr)
{
	struct RefHeader *hdr = ptr;
	if (--hdr->refcount == 0)
		free(ptr);
}
