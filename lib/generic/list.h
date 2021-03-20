// TODO: have this struct on stack when possible, same with strings
struct TYPE_STRUCT {
	REFCOUNT_HEADER
	int64_t len;
	int64_t alloc;
	ITEMTYPE smalldata[8];
	ITEMTYPE *data;
};
