struct MAPPING_STRUCT {
	REFCOUNT_HEADER
	size_t len;
	size_t nentries;   // never zero
	ITEM *entries;
	ITEM flex[];   // just for mallocing struct and entries with one allocation
};

MAPPING MAPPING_CTOR(void);
void MAPPING_DTOR(void *ptr);
