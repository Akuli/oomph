#include <assert.h>

#define concat(a, b) a##b
typedef struct concat(TYPE_STRUCT, _entry) Entry;
#undef concat

TYPE CONSTRUCTOR(void)
{
	TYPE map = malloc(sizeof(*map));
	assert(map);
	map->refcount = 1;
	map->len = 0;
	map->nentries = 0;
	map->entries = NULL;
	return map;
}

void DESTRUCTOR(void *ptr)
{
	TYPE map = ptr;
	for (size_t i = 0; i < map->nentries; i++) {
		if (map->entries[i].hash != 0) {
			string_decref(map->entries[i].key);
			DECREF_ITEM(map->entries[i].value);
		}
	}
	free(map->entries);
	free(map);
}

uint32_t hash(struct class_Str s)
{
	// FIXME
	assert(s.nbytes != 0);
	return s.nbytes;
}


static void add_entry(TYPE map, Entry e, bool check, bool incr)
{
	assert(e.hash != 0);
	assert(map->nentries != 0);

	uint32_t i = e.hash % map->nentries;
	while (map->entries[i].hash != 0) {
		if (check && map->entries[i].hash == e.hash && meth_Str_equals(map->entries[i].key, e.key)) {
			DECREF_ITEM(map->entries[i].value);
			map->entries[i].value = e.value;
			INCREF_ITEM(map->entries[i].value);
			return;
		}
		// Jump over this entry
		i = (i+1) % map->nentries;
	}

	map->entries[i] = e;
	string_incref(e.key);
	INCREF_ITEM(e.value);
	if (incr)
		map->len++;
}

static void grow(TYPE map)
{
	size_t oldn = map->nentries;
#define max(a, b) ((a)>(b) ? (a) : (b))
	map->nentries = max(oldn, 1)*2;
#undef max

	// TODO: can use realloc?
	Entry *oldlist = map->entries;
	map->entries = calloc(sizeof map->entries[0], map->nentries);
	assert(map->entries);

	for (size_t i = 0; i < oldn; i++) {
		if (oldlist[i].hash != 0)
			add_entry(map, oldlist[i], false, false);
	}
	free(oldlist);
}

void METHOD(set)(TYPE map, struct class_Str key, ITEMTYPE value)
{
	float magic = 0.7;   // TODO: do experiments to find best possible value
	if (map->len+1 > magic*map->nentries)
		grow(map);
	add_entry(map, (Entry){ hash(key), key, value }, true, true);
}

// TODO: this sucked in python 2 and it sucks here too
bool METHOD(has_key)(TYPE map, struct class_Str key)
{
	// avoid % 0
	if (map->len != 0) {
		uint32_t h = hash(key);
		for (size_t i = h % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
		{
			Entry e = map->entries[i];
			if (e.hash == h && meth_Str_equals(e.key, key))
				return true;
		}
	}
	return false;
}

ITEMTYPE METHOD(get)(TYPE map, struct class_Str key)
{
	// avoid % 0
	if (map->len != 0) {
		uint32_t h = hash(key);
		for (size_t i = h % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
		{
			Entry e = map->entries[i];
			if (e.hash == h && meth_Str_equals(e.key, key)) {
				INCREF_ITEM(e.value);
				return e.value;
			}
		}
	}

	panic_printf("key not found from mapping: %s", string_to_cstr(key));
}

void METHOD(delete)(TYPE map, struct class_Str key)
{
	// avoid % 0
	if (map->len == 0)
		goto error404;

	uint32_t h = hash(key);
	size_t i = h % map->nentries;
	for (; map->entries[i].hash != h || !ITEMTYPE_METHOD(equals)(map->entries[i].key, key); i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == 0)
			goto error404;
	}

	string_decref(map->entries[i].key);
	DECREF_ITEM(map->entries[i].value);
	map->entries[i].hash = 0;
	map->len--;

	// Delete and add back everything that might rely on jumping over the item at i
	for (size_t k = (i+1) % map->nentries; map->entries[k].hash != 0; k = (k+1) % map->nentries)
	{
		Entry e = map->entries[k];
		map->entries[k].hash = 0;
		add_entry(map, e, false, false);
	}
	return;

error404:
	panic_printf("key not found from mapping: %s", string_to_cstr(key));
}

int64_t METHOD(length)(TYPE map)
{
	return (int64_t)map->len;
}
