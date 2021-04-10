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

void DESTRUCTOR(void *ptr)
{
	TYPE self = ptr;
	for (int64_t i = 0; i < self->nentries; i++) {
		if (self->entries[i].hash != 0) {
			string_decref(self->entries[i].key);
			DECREF_ITEM(self->entries[i].value);
		}
	}
	// TODO: free entries
	free(self);
}
