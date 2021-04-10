#include <assert.h>

#define concat(a, b) a##b
typedef struct concat(TYPE_STRUCT, _entry) Entry;
#undef concat

TYPE CONSTRUCTOR(void)
{
	TYPE res = malloc(sizeof(*res));
	assert(res);
	res->refcount = 1;
	res->len = 0;
	res->nentries = 0;
	res->entries = NULL;
	return res;
}
