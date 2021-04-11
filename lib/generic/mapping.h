struct INTERNAL_NAME(entry) {
	uint32_t hash;   // 0 if entry is unused
	KEY key;
	VALUE value;
};

struct TYPE_STRUCT {
	REFCOUNT_HEADER
	size_t len;
	size_t nentries;   // never zero
	struct INTERNAL_NAME(entry) *entries;
	struct INTERNAL_NAME(entry) flex[];   // just for mallocing struct and entries with one allocation
};
