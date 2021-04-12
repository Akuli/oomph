// TODO: Python-style order-preserving mapping https://www.youtube.com/watch?v=p33CVV29OG8

#include <assert.h>

#define EMPTY ((size_t)(-1))

MAPPING MAPPING_CTOR(void)
{
	size_t n = 8;   // TODO: experiment with different values
	MAPPING map = malloc(sizeof(*map) + n*sizeof(map->flex[0]));
	assert(map);

	map->refcount = 1;
	map->items = ITEM_LIST_CTOR();
	map->itable = map->flex;
	for (size_t i = 0; i < n; i++)
		map->itable[i] = EMPTY;
	map->itablesz = n;
	return map;
}

void MAPPING_DTOR(void *ptr)
{
	MAPPING map = ptr;
	ITEM_LIST_DECREF(map->items);
	if (map->itable != map->flex)
		free(map->itable);
	free(map);
}

static uint32_t hash(KEY key)
{
	uint32_t h = (uint32_t)KEY_METHOD(hash)(key);
	// 0 has special meaning in MappingItem
	return h==0 ? 69 : h;
}


static size_t find_empty(MAPPING map, uint32_t keyhash)
{
	size_t i;
	for (i = keyhash % map->itablesz; map->itable[i] != EMPTY; i = (i+1) % map->itablesz) { }
	return i;
}

static ITEM *find_item_or_empty(MAPPING map, KEY key, uint32_t keyhash, size_t *idx)
{
	size_t i;
	for (i = keyhash % map->itablesz; map->itable[i] != EMPTY; i = (i+1) % map->itablesz)
	{
		ITEM *inmap = &map->items->data[map->itable[i]];
		if (inmap->hash == keyhash && KEY_METHOD(equals)(inmap->memb_key, key)) {
			*idx = i;
			return inmap;
		}
	}
	*idx = i;   // Same as what find_empty(map, keyhash) would return
	return NULL;
}

static ITEM *find_item(MAPPING map, KEY key, uint32_t keyhash)
{
	size_t dummy;
	return find_item_or_empty(map, key, keyhash, &dummy);
}

static void grow_itable(MAPPING map)
{
	size_t oldsz = map->itablesz;
	map->itablesz *= 2;

	// TODO: use realloc
	size_t *old = map->itable;
	map->itable = malloc(map->itablesz * sizeof map->itable[0]);
	assert(map->itable);

	// Reindex everything lol
	for (size_t i = 0; i < map->itablesz; i++)
		map->itable[i] = EMPTY;
	for (int64_t i = 0; i < map->items->len; i++)
		map->itable[find_empty(map, map->items->data[i].hash)] = i;

	if (old != map->flex)
		free(old);
}

void MAPPING_METHOD(set)(MAPPING map, KEY key, VALUE value)
{
	float magic = 0.7;   // TODO: do experiments to find best possible value
	if (map->items->len+1 > magic*map->itablesz)
		grow_itable(map);

	uint32_t h = hash(key);
	size_t i;
	ITEM *inmap = find_item_or_empty(map, key, h, &i);
	if (inmap == NULL) {
		map->itable[i] = (size_t)map->items->len;
		ITEM_LIST_METHOD(push)(map->items, (ITEM){ h, key, value });
	} else {
		VALUE_DECREF(inmap->memb_value);
		inmap->memb_value = value;
		VALUE_INCREF(inmap->memb_value);
	}
}

// TODO: this sucked in python 2 and it sucks here too
bool MAPPING_METHOD(has_key)(MAPPING map, KEY key)
{
	return find_item(map, key, hash(key)) != NULL;
}

#define ERROR(msg, key) panic_printf("%s: %s", (msg), string_to_cstr(KEY_METHOD(to_string)((key))))

VALUE MAPPING_METHOD(get)(MAPPING map, KEY key)
{
	ITEM *it = find_item(map, key, hash(key));
	if (!it)
		ERROR("Mapping.get(): key not found", key);

	VALUE_INCREF(it->memb_value);
	return it->memb_value;
}

void MAPPING_METHOD(delete)(MAPPING map, KEY key)
{
	size_t i;
	if (find_item_or_empty(map, key, hash(key), &i) == NULL)
		ERROR("Mapping.delete(): key not found", key);

	// TODO: delete_at_index is slow
	size_t delidx = map->itable[i];
	ITEM deleted = ITEM_LIST_METHOD(delete_at_index)(map->items, delidx);
	KEY_DECREF(deleted.memb_key);
	VALUE_DECREF(deleted.memb_value);
	map->itable[i] = EMPTY;

	// Adjust the mess left behind by delete_at_index
	for (size_t k = 0; k < map->itablesz; k++) {
		if (map->itable[k] != EMPTY && map->itable[k] > delidx)
			map->itable[k]--;
	}

	// Delete and add back everything that might rely on jumping over the item at i
	for (size_t k = (i+1) % map->itablesz; map->itable[k] != EMPTY; k = (k+1) % map->itablesz)
	{
		size_t idx = map->itable[k];
		map->itable[k] = EMPTY;
		map->itable[find_empty(map, map->items->data[idx].hash)] = idx;
	}
}

int64_t MAPPING_METHOD(length)(MAPPING map)
{
	return map->items->len;
}

struct class_Str MAPPING_METHOD(to_string)(MAPPING map)
{
	// TODO: Mapping[...] is a bit weird
	struct class_Str res = cstr_to_string("Mapping");
	struct class_Str itemstr = ITEM_LIST_METHOD(to_string)(map->items);
	oomph_string_concat_inplace(&res, itemstr);
	decref_Str(itemstr);
	return res;
}

bool MAPPING_METHOD(equals)(MAPPING a, MAPPING b)
{
	if (a->items->len != b->items->len)
		return false;

	// Check that every key of a is also in b, and values match.
	// No need to check in opposite direction, because lengths match.
	for (int64_t i = 0; i < a->items->len; i++) {
		ITEM aent = a->items->data[i];
		if (aent.hash != 0) {
			ITEM *bent = find_item(b, aent.memb_key, aent.hash);
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
	for (int64_t i = 0; i < map->items->len; i++) {
		ITEM it = map->items->data[i];
		MAPPING_METHOD(set)(res, it.memb_key, it.memb_value);
	}
	return res;
}

KEY_LIST MAPPING_METHOD(keys)(MAPPING map)
{
	KEY_LIST res = KEY_LIST_CTOR();
	for (int64_t i = 0; i < map->items->len; i++) {
		assert(MAPPING_METHOD(has_key)(map, map->items->data[i].memb_key));
		KEY_LIST_METHOD(push)(res, map->items->data[i].memb_key);
	}
	return res;
}

VALUE_LIST MAPPING_METHOD(values)(MAPPING map)
{
	VALUE_LIST res = VALUE_LIST_CTOR();
	for (int64_t i = 0; i < map->items->len; i++)
		VALUE_LIST_METHOD(push)(res, map->items->data[i].memb_value);
	return res;
}

ITEM_LIST MAPPING_METHOD(items)(MAPPING map)
{
	return ITEM_LIST_METHOD(copy)(map->items);
}
