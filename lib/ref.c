#include "lib.h"
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

void decref(void *ptr)
{
	if (ptr) {
		struct RefHeader *hdr = ptr;
		if (hdr->refcount > 0 && --hdr->refcount == 0)
			free(ptr);
	}
}
