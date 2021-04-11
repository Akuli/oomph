struct TYPE_STRUCT {
	REFCOUNT_HEADER
	size_t len;
	size_t nentries;   // never zero
	ENTRY *entries;
	ENTRY flex[];   // just for mallocing struct and entries with one allocation
};
