struct TYPE_STRUCT {
	REFCOUNT_HEADER
	size_t len;
	size_t nentries;

	// TODO: this is a bit hacky
#define concat(a, b) a##b
	struct concat(TYPE_STRUCT, _entry) {
#undef concat
		uint32_t hash;   // 0 if entry is unused
		struct class_Str key;
		ITEMTYPE value;
	} *entries;
};

