#include <assert.h>

typedef struct INTERNAL_NAME(entry) Entry;

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
			DECREF_KEY(map->entries[i].key);
			DECREF_VALUE(map->entries[i].value);
		}
	}
	free(map->entries);
	free(map);
}

static uint32_t hash(KEYTYPE key)
{
	uint32_t h = (uint32_t)KEYTYPE_METHOD(hash)(key);
	if (h == 0)   // 0 has special meaning in mapping
		h = 69;
	return h;
}


static void add_entry(TYPE map, Entry e, bool check, bool incr)
{
	assert(e.hash != 0);
	assert(map->nentries != 0);

	uint32_t i = e.hash % map->nentries;
	while (map->entries[i].hash != 0) {
		if (check && map->entries[i].hash == e.hash && KEYTYPE_METHOD(equals)(map->entries[i].key, e.key)) {
			DECREF_VALUE(map->entries[i].value);
			map->entries[i].value = e.value;
			INCREF_VALUE(map->entries[i].value);
			return;
		}
		// Jump over this entry
		i = (i+1) % map->nentries;
	}

	map->entries[i] = e;
	INCREF_KEY(e.key);
	INCREF_VALUE(e.value);
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

void METHOD(set)(TYPE map, KEYTYPE key, VALUETYPE value)
{
	float magic = 0.7;   // TODO: do experiments to find best possible value
	if (map->len+1 > magic*map->nentries)
		grow(map);
	add_entry(map, (Entry){ hash(key), key, value }, true, true);
}

// TODO: this sucked in python 2 and it sucks here too
bool METHOD(has_key)(TYPE map, KEYTYPE key)
{
	// avoid % 0
	if (map->len != 0) {
		uint32_t h = hash(key);
		for (size_t i = h % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
		{
			Entry e = map->entries[i];
			if (e.hash == h && KEYTYPE_METHOD(equals)(e.key, key))
				return true;
		}
	}
	return false;
}

#define ERROR(msg, key) panic_printf("%s: %s", (msg), string_to_cstr(KEYTYPE_METHOD(to_string)((key))))

VALUETYPE METHOD(get)(TYPE map, KEYTYPE key)
{
	// avoid % 0
	if (map->len != 0) {
		uint32_t h = hash(key);
		for (size_t i = h % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
		{
			Entry e = map->entries[i];
			if (e.hash == h && KEYTYPE_METHOD(equals)(e.key, key)) {
				INCREF_VALUE(e.value);
				return e.value;
			}
		}
	}

	ERROR("Mapping.get(): key not found", key);
}

void METHOD(delete)(TYPE map, KEYTYPE key)
{
	// avoid % 0
	if (map->len == 0)
		goto error404;

	uint32_t h = hash(key);
	size_t i = h % map->nentries;
	for (; map->entries[i].hash != h || !KEYTYPE_METHOD(equals)(map->entries[i].key, key); i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == 0)
			goto error404;
	}

	DECREF_KEY(map->entries[i].key);
	DECREF_VALUE(map->entries[i].value);
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
	ERROR("Mapping.delete(): key not found", key);
}

int64_t METHOD(length)(TYPE map)
{
	return (int64_t)map->len;
}
