#include <assert.h>
#include <string.h>

typedef struct INTERNAL_NAME(entry) Entry;

TYPE CONSTRUCTOR(void)
{
	size_t n = 8;
	TYPE map = malloc(sizeof(*map) + n*sizeof(map->flex[0]));
	assert(map);
	map->refcount = 1;
	map->len = 0;
	map->nentries = n;
	map->entries = map->flex;
	memset(map->entries, 0, sizeof(map->entries[0]) * n);
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
	if (map->entries != map->flex)
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


// Returns whether the entry was actually added
static bool add_entry(TYPE map, Entry e, bool check)
{
	assert(e.hash != 0);

	uint32_t i = e.hash % map->nentries;
	while (map->entries[i].hash != 0) {
		if (check && map->entries[i].hash == e.hash && KEYTYPE_METHOD(equals)(map->entries[i].key, e.key)) {
			DECREF_VALUE(map->entries[i].value);
			map->entries[i].value = e.value;
			INCREF_VALUE(map->entries[i].value);
			return false;
		}
		// Jump over this entry
		i = (i+1) % map->nentries;
	}

	map->entries[i] = e;
	return true;
}

static void grow(TYPE map)
{
	size_t oldn = map->nentries;
	map->nentries *= 2;

	// TODO: can use realloc?
	Entry *oldlist = map->entries;
	map->entries = calloc(sizeof map->entries[0], map->nentries);
	assert(map->entries);

	for (size_t i = 0; i < oldn; i++) {
		if (oldlist[i].hash != 0)
			add_entry(map, oldlist[i], false);
	}

	if (oldlist != map->flex)
		free(oldlist);
}

void METHOD(set)(TYPE map, KEYTYPE key, VALUETYPE value)
{
	float magic = 0.7;   // TODO: do experiments to find best possible value
	if (map->len+1 > magic*map->nentries)
		grow(map);

	if (add_entry(map, (Entry){ hash(key), key, value }, true)) {
		INCREF_KEY(key);
		INCREF_VALUE(value);
		map->len++;
	}
}

static Entry *find(TYPE map, KEYTYPE key, uint32_t keyhash)
{
	for (size_t i = keyhash % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == keyhash && KEYTYPE_METHOD(equals)(map->entries[i].key, key))
			return &map->entries[i];
	}
	return NULL;
}

// TODO: this sucked in python 2 and it sucks here too
bool METHOD(has_key)(TYPE map, KEYTYPE key)
{
	return find(map, key, hash(key)) != NULL;
}

#define ERROR(msg, key) panic_printf("%s: %s", (msg), string_to_cstr(KEYTYPE_METHOD(to_string)((key))))

VALUETYPE METHOD(get)(TYPE map, KEYTYPE key)
{
	Entry *e = find(map, key, hash(key));
	if (!e)
		ERROR("Mapping.get(): key not found", key);

	INCREF_VALUE(e->value);
	return e->value;
}

void METHOD(delete)(TYPE map, KEYTYPE key)
{
	uint32_t h = hash(key);
	size_t i = h % map->nentries;
	for (; map->entries[i].hash != h || !KEYTYPE_METHOD(equals)(map->entries[i].key, key); i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == 0)
			ERROR("Mapping.delete(): key not found", key);
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
		add_entry(map, e, false);
	}
}

int64_t METHOD(length)(TYPE map)
{
	return (int64_t)map->len;
}

struct class_Str METHOD(to_string)(TYPE map)
{
	struct class_Str res = cstr_to_string("Mapping{");
	bool first = true;
	for (size_t i = 0; i < map->nentries; i++) {
		Entry e = map->entries[i];
		if (e.hash != 0) {
			if (!first)
				oomph_string_concat_inplace_cstr(&res, ", ");
			first = false;

			struct class_Str keystr = KEYTYPE_METHOD(to_string)(e.key);
			struct class_Str valstr = VALUETYPE_METHOD(to_string)(e.value);
			oomph_string_concat_inplace(&res, keystr);
			oomph_string_concat_inplace_cstr(&res, ": ");
			oomph_string_concat_inplace(&res, valstr);
			string_decref(keystr);
			string_decref(valstr);
		}
	}

	oomph_string_concat_inplace_cstr(&res, "}");
	return res;
}

bool METHOD(equals)(TYPE a, TYPE b)
{
	if (a->len != b->len)
		return false;

	// Check that every key of a is also in b, and values match.
	// No need to check in opposite direction, because lengths match.
	for (size_t i = 0; i < a->nentries; i++) {
		Entry aent = a->entries[i];
		if (aent.hash != 0) {
			Entry *bent = find(b, aent.key, aent.hash);
			if (bent == NULL || !VALUETYPE_METHOD(equals)(aent.value, bent->value))
				return false;
		}
	}

	return true;
}
