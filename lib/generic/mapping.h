struct MAPPING_STRUCT {
	REFCOUNT_HEADER
	ITEM_LIST items;

	// itable contains indexes into items, see https://www.youtube.com/watch?v=p33CVV29OG8
	// TODO: often int8_t or int16_t or int32_t is big enough, use those
	size_t *itable;
	size_t itablesz;

	// to allocate itable and rest of mapping at once
	size_t flex[];
};

MAPPING MAPPING_CTOR(void);
void MAPPING_DTOR(void *ptr);
