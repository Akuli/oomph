struct TYPE_STRUCT {
	REFCOUNT_HEADER
	int64_t len;
	int64_t nentries;

	// TODO: this is a bit hacky
#define concat(a, b) a##b
	struct concat(TYPE_STRUCT, _entry) {
#undef concat
		unsigned int hash;   // -1 if entry is unused
		struct class_Str key;
		ITEMTYPE value;
	} *entries;
};

