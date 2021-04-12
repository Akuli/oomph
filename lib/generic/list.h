// TODO: have this struct on stack when possible, same with strings
struct LIST_STRUCT {
	REFCOUNT_HEADER
	int64_t len;
	int64_t alloc;
	ITEM smalldata[8];
	ITEM *data;
};

LIST LIST_CTOR(void);
void LIST_DTOR(void *ptr);
