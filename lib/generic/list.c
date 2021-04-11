#if ITEM_IS_STRING
struct class_Str LIST_METHOD(join)(LIST self, struct class_Str sep)
{
	return meth_List_Str_join(self, sep);   // Implemented in oomph
}
#endif

LIST LIST_CTOR(void)
{
	LIST res = malloc(sizeof(*res));
	assert(res);
	res->refcount = 1;
	res->len = 0;
	res->data = res->smalldata;
	res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
	return res;
}

void LIST_DTOR(void *ptr)
{
	LIST self = ptr;
	for (int64_t i = 0; i < self->len; i++)
		ITEM_DECREF(self->data[i]);
	if (self->data != self->smalldata)
		free(self->data);
	free(self);
}

bool LIST_METHOD(equals)(LIST self, LIST other)
{
	if (self->len != other->len)
		return false;
	for (int64_t i = 0; i < self->len; i++) {
		if (!ITEM_METHOD(equals)(self->data[i], other->data[i]))
			return false;
	}
	return true;
}

static void set_length(LIST self, int64_t n)
{
	assert(n >= 0);
	self->len = n;

	if (self->alloc >= n)
		return;
	while (self->alloc < n)
		self->alloc *= 2;

	if (self->data == self->smalldata) {
		self->data = malloc(self->alloc * sizeof(self->data[0]));
		assert(self->data);
		memcpy(self->data, self->smalldata, sizeof self->smalldata);
	} else {
		self->data = realloc(self->data, self->alloc * sizeof(self->data[0]));
		assert(self->data);
	}
}

void LIST_METHOD(push)(LIST self, ITEM val)
{
	set_length(self, self->len + 1);
	self->data[self->len - 1] = val;
	ITEM_INCREF(val);
}

void LIST_METHOD(push_all)(LIST self, LIST src)
{
	int64_t oldlen = self->len;
	set_length(self, self->len + src->len);
	memcpy(self->data + oldlen, src->data, sizeof(src->data[0]) * src->len);
	for (int64_t i = 0; i < src->len; i++)
		ITEM_INCREF(src->data[i]);
}

void LIST_METHOD(insert)(LIST self, int64_t index, ITEM val)
{
	if (index < 0)
		index = 0;
	if (index > self->len)
		index = self->len;

	set_length(self, self->len + 1);
	memmove(self->data + index + 1, self->data + index, (self->len - index - 1)*sizeof(self->data[0]));
	self->data[index] = val;
	ITEM_INCREF(val);
}

ITEM LIST_METHOD(pop)(LIST self)
{
	if (self->len == 0)
		panic_printf("pop from empty list");
	return self->data[--self->len];
}

static void validate_index(LIST self, int64_t i)
{
	if (i < 0)
		panic_printf("negative list index %%d", (long)i);
	if (i >= self->len)
		panic_printf("list index %%ld beyond end of list of length %%ld", (long)i, (long)self->len);
}

ITEM LIST_METHOD(set)(LIST self, int64_t i, ITEM value)
{
	validate_index(self, i);
	ITEM old = self->data[i];
	self->data[i] = value;
	ITEM_INCREF(value);
	return old;
}

ITEM LIST_METHOD(get)(LIST self, int64_t i)
{
	validate_index(self, i);
	ITEM_INCREF(self->data[i]);
	return self->data[i];
}

ITEM LIST_METHOD(delete_at_index)(LIST self, int64_t i)
{
	validate_index(self, i);
	ITEM item = self->data[i];
	self->len--;
	memmove(self->data+i, self->data+i+1, (self->len - i)*sizeof(self->data[0]));
	return item;
}

static LIST slice(LIST self, int64_t start, int64_t end, bool del)
{
	if (start < 0)
		start = 0;
	if (end > self->len)
		end = self->len;

	LIST res = LIST_CTOR();
	if (start < end) {
		set_length(res, end-start);
		memcpy(res->data, &self->data[start], res->len*sizeof(self->data[0]));
		if (del) {
			memmove(&self->data[start], &self->data[end], (self->len - end)*sizeof(self->data[0]));
			self->len -= res->len;
		} else {
			for (int64_t i = 0; i < res->len; i++)
				ITEM_INCREF(res->data[i]);
		}
	}
	return res;
}

LIST LIST_METHOD(slice)(LIST self, int64_t start, int64_t end)
{
	return slice(self, start, end, false);
}

LIST LIST_METHOD(delete_slice)(LIST self, int64_t start, int64_t end)
{
	return slice(self, start, end, true);
}

ITEM LIST_METHOD(first)(LIST self)
{
	if (self->len == 0)
		panic_printf("can't get first item of empty list");
	ITEM_INCREF(self->data[0]);
	return self->data[0];
}

ITEM LIST_METHOD(last)(LIST self)
{
	if (self->len == 0)
		panic_printf("can't get last item of empty list");
	ITEM_INCREF(self->data[self->len - 1]);
	return self->data[self->len - 1];
}

bool LIST_METHOD(__contains)(LIST self, ITEM item)
{
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEM_METHOD(equals)(self->data[i], item))
			return true;
	}
	return false;
}

int64_t LIST_METHOD(find_first)(LIST self, ITEM item)
{
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEM_METHOD(equals)(self->data[i], item))
			return i;
	}
	panic_printf("find_first: item not found");
}

int64_t LIST_METHOD(find_last)(LIST self, ITEM item)
{
	for (int64_t i = self->len - 1; i >= 0; i--) {
		if (ITEM_METHOD(equals)(self->data[i], item))
			return i;
	}
	panic_printf("find_last: item not found");
}

int64_t LIST_METHOD(find_only)(LIST self, ITEM item)
{
	int64_t found = -1;
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEM_METHOD(equals)(self->data[i], item)) {
			if (found != -1)
				panic_printf("find_only: item found multiple times");
			found = i;
		}
	}
	if (found == -1)
		panic_printf("find_only: item not found");
	return found;
}

void LIST_METHOD(delete_first)(LIST self, ITEM item)
{
	ITEM deleted = LIST_METHOD(delete_at_index)(self, LIST_METHOD(find_first)(self, item));
	ITEM_DECREF(deleted);
}

void LIST_METHOD(delete_last)(LIST self, ITEM item)
{
	ITEM deleted = LIST_METHOD(delete_at_index)(self, LIST_METHOD(find_last)(self, item));
	ITEM_DECREF(deleted);
}

void LIST_METHOD(delete_only)(LIST self, ITEM item)
{
	ITEM deleted = LIST_METHOD(delete_at_index)(self, LIST_METHOD(find_only)(self, item));
	ITEM_DECREF(deleted);
}

bool LIST_METHOD(starts_with)(LIST self, LIST prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t i = 0; i < prefix->len; i++)
		if (!ITEM_METHOD(equals)(self->data[i], prefix->data[i]))
			return false;
	return true;
}

bool LIST_METHOD(ends_with)(LIST self, LIST prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t s=self->len-1, p=prefix->len-1; p >= 0; s--,p--)
		if (!ITEM_METHOD(equals)(self->data[s], prefix->data[p]))
			return false;
	return true;
}

int64_t LIST_METHOD(length)(LIST self)
{
	return self->len;
}

// TODO: rewrite better in the language itself?
struct class_Str LIST_METHOD(to_string)(LIST self)
{
	struct class_Str res = cstr_to_string("[");

	for (int64_t i = 0; i < self->len; i++) {
		if (i != 0)
			oomph_string_concat_inplace_cstr(&res, ", ");

		struct class_Str s = ITEM_METHOD(to_string)(self->data[i]);
		oomph_string_concat_inplace(&res, s);
		string_decref(s);
	}

	oomph_string_concat_inplace_cstr(&res, "]");
	return res;
}

LIST LIST_METHOD(reversed)(LIST self)
{
	LIST res = LIST_CTOR();
	set_length(res, self->len);
	for (int64_t i = 0; i < self->len; i++) {
		res->data[i] = self->data[self->len - 1 - i];
		ITEM_INCREF(res->data[i]);
	}
	return res;
}

LIST LIST_METHOD(copy)(LIST self)
{
	LIST res = LIST_CTOR();
	set_length(res, self->len);
	memcpy(res->data, self->data, sizeof(self->data[0]) * self->len);
	for (int64_t i = 0; i < self->len; i++)
		ITEM_INCREF(res->data[i]);
	return res;
}
