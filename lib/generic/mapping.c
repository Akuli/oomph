// TODO: Python-style order-preserving mapping https://www.youtube.com/watch?v=p33CVV29OG8

#include <assert.h>
#include <string.h>

MAPPING MAPPING_CTOR(void)
{
	size_t n = 8;   // TODO: experiment with different values
	MAPPING map = calloc(1, sizeof(*map) + n*sizeof(map->flex[0]));
	assert(map);
	map->refcount = 1;
	map->nentries = n;
	map->entries = map->flex;
	return map;
}

void MAPPING_DTOR(void *ptr)
{
	MAPPING map = ptr;
	for (size_t i = 0; i < map->nentries; i++) {
		if (map->entries[i].hash != 0) {
			KEY_DECREF(map->entries[i].memb_key);
			VALUE_DECREF(map->entries[i].memb_value);
		}
	}
	if (map->entries != map->flex)
		free(map->entries);
	free(map);
}

static uint32_t hash(KEY key)
{
	uint32_t h = (uint32_t)KEY_METHOD(hash)(key);
	// 0 has special meaning in mapping
	return h==0 ? 69 : h;
}


// Returns whether the entry was actually added
static bool add_entry(MAPPING map, ENTRY e, bool check)
{
	assert(e.hash != 0);

	uint32_t i = e.hash % map->nentries;
	while (map->entries[i].hash != 0) {
		if (check && map->entries[i].hash == e.hash && KEY_METHOD(equals)(map->entries[i].memb_key, e.memb_key)) {
			VALUE_DECREF(map->entries[i].memb_value);
			map->entries[i].memb_value = e.memb_value;
			VALUE_INCREF(map->entries[i].memb_value);
			return false;
		}
		// Jump over this entry
		i = (i+1) % map->nentries;
	}

	map->entries[i] = e;
	return true;
}

static void grow(MAPPING map)
{
	size_t oldn = map->nentries;
	map->nentries *= 2;

	// TODO: can use realloc?
	ENTRY *oldlist = map->entries;
	map->entries = calloc(map->nentries, sizeof map->entries[0]);
	assert(map->entries);

	for (size_t i = 0; i < oldn; i++) {
		if (oldlist[i].hash != 0)
			add_entry(map, oldlist[i], false);
	}

	if (oldlist != map->flex)
		free(oldlist);
}

void MAPPING_METHOD(set)(MAPPING map, KEY key, VALUE value)
{
	float magic = 0.7;   // TODO: do experiments to find best possible value
	if (map->len+1 > magic*map->nentries)
		grow(map);

	if (add_entry(map, (ENTRY){ hash(key), key, value }, true)) {
		KEY_INCREF(key);
		VALUE_INCREF(value);
		map->len++;
	}
}

static ENTRY *find(MAPPING map, KEY key, uint32_t keyhash)
{
	for (size_t i = keyhash % map->nentries; map->entries[i].hash != 0; i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == keyhash && KEY_METHOD(equals)(map->entries[i].memb_key, key))
			return &map->entries[i];
	}
	return NULL;
}

// TODO: this sucked in python 2 and it sucks here too
bool MAPPING_METHOD(has_key)(MAPPING map, KEY key)
{
	return find(map, key, hash(key)) != NULL;
}

#define ERROR(msg, key) panic_printf("%s: %s", (msg), string_to_cstr(KEY_METHOD(to_string)((key))))

VALUE MAPPING_METHOD(get)(MAPPING map, KEY key)
{
	ENTRY *e = find(map, key, hash(key));
	if (!e)
		ERROR("Mapping.get(): key not found", key);

	VALUE_INCREF(e->memb_value);
	return e->memb_value;
}

void MAPPING_METHOD(delete)(MAPPING map, KEY key)
{
	uint32_t h = hash(key);
	size_t i = h % map->nentries;
	for (; map->entries[i].hash != h || !KEY_METHOD(equals)(map->entries[i].memb_key, key); i = (i+1) % map->nentries)
	{
		if (map->entries[i].hash == 0)
			ERROR("Mapping.delete(): key not found", key);
	}

	KEY_DECREF(map->entries[i].memb_key);
	VALUE_DECREF(map->entries[i].memb_value);
	map->entries[i].hash = 0;
	map->len--;

	// Delete and add back everything that might rely on jumping over the item at i
	for (size_t k = (i+1) % map->nentries; map->entries[k].hash != 0; k = (k+1) % map->nentries)
	{
		ENTRY e = map->entries[k];
		map->entries[k].hash = 0;
		add_entry(map, e, false);
	}
}

int64_t MAPPING_METHOD(length)(MAPPING map)
{
	return (int64_t)map->len;
}

struct class_Str MAPPING_METHOD(to_string)(MAPPING map)
{
	struct class_Str res = cstr_to_string("Mapping{");
	bool first = true;
	for (size_t i = 0; i < map->nentries; i++) {
		ENTRY e = map->entries[i];
		if (e.hash != 0) {
			if (!first)
				oomph_string_concat_inplace_cstr(&res, ", ");
			first = false;

			struct class_Str keystr = KEY_METHOD(to_string)(e.memb_key);
			struct class_Str valstr = VALUE_METHOD(to_string)(e.memb_value);
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

bool MAPPING_METHOD(equals)(MAPPING a, MAPPING b)
{
	if (a->len != b->len)
		return false;

	// Check that every key of a is also in b, and values match.
	// No need to check in opposite direction, because lengths match.
	for (size_t i = 0; i < a->nentries; i++) {
		ENTRY aent = a->entries[i];
		if (aent.hash != 0) {
			ENTRY *bent = find(b, aent.memb_key, aent.hash);
			if (bent == NULL || !VALUE_METHOD(equals)(aent.memb_value, bent->memb_value))
				return false;
		}
	}

	return true;
}

// TODO: optimize?
MAPPING MAPPING_METHOD(copy)(MAPPING map)
{
	MAPPING res = MAPPING_CTOR();
	for (size_t i = 0; i < map->nentries; i++) {
		ENTRY e = map->entries[i];
		if (e.hash != 0)
			MAPPING_METHOD(set)(res, e.memb_key, e.memb_value);
	}
	return res;
}

ENTRY_LIST MAPPING_METHOD(items)(MAPPING map)
{
	ENTRY_LIST res = ENTRY_LIST_CTOR();
	for (size_t i = 0; i < map->nentries; i++) {
		ENTRY e = map->entries[i];
		if (e.hash != 0)
			ENTRY_LIST_METHOD(push)(res, e);
	}
	return res;
}
