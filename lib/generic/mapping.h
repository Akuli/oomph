struct INTERNAL_NAME(entry) {
	uint32_t hash;   // 0 if entry is unused
	KEYTYPE key;
	VALUETYPE value;
};

struct TYPE_STRUCT {
	REFCOUNT_HEADER
	size_t len;
	size_t nentries;
	struct INTERNAL_NAME(entry) *entries;
};
