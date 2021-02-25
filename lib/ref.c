#include <stdlib.h>

struct RefHeader {
	size_t refcount;
};

void decref(void *ptr)
{
	struct RefHeader *hdr = ptr;
	if (--hdr->refcount == 0)
		free(ptr);
}
