#if ITEMTYPE_IS_STRING
struct class_Str METHOD(join)(TYPE self, struct class_Str sep)
{
	return meth_List_Str_join(self, sep);   // Implemented in oomph
}
#endif

TYPE CONSTRUCTOR(void)
{
	TYPE res = malloc(sizeof(*res));
	assert(res);
	res->refcount = 1;
	res->len = 0;
	res->data = res->smalldata;
	res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
	return res;
}

void DESTRUCTOR(void *ptr)
{
	TYPE self = ptr;
	for (int64_t i = 0; i < self->len; i++)
		DECREF_ITEM(self->data[i]);
	if (self->data != self->smalldata)
		free(self->data);
	free(self);
}

bool METHOD(equals)(TYPE self, TYPE other)
{
	if (self->len != other->len)
		return false;
	for (int64_t i = 0; i < self->len; i++) {
		if (!ITEMTYPE_METHOD(equals)(self->data[i], other->data[i]))
			return false;
	}
	return true;
}

static void set_length(TYPE self, int64_t n)
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

void METHOD(push)(TYPE self, ITEMTYPE val)
{
	set_length(self, self->len + 1);
	self->data[self->len - 1] = val;
	INCREF_ITEM(val);
}

void METHOD(push_all)(TYPE self, TYPE src)
{
	int64_t oldlen = self->len;
	set_length(self, self->len + src->len);
	memcpy(self->data + oldlen, src->data, sizeof(src->data[0]) * src->len);
	for (int64_t i = 0; i < src->len; i++)
		INCREF_ITEM(src->data[i]);
}

void METHOD(insert)(TYPE self, int64_t index, ITEMTYPE val)
{
	if (index < 0)
		index = 0;
	if (index > self->len)
		index = self->len;

	set_length(self, self->len + 1);
	memmove(self->data + index + 1, self->data + index, (self->len - index - 1)*sizeof(self->data[0]));
	self->data[index] = val;
	INCREF_ITEM(val);
}

ITEMTYPE METHOD(pop)(TYPE self)
{
	if (self->len == 0)
		panic_printf("pop from empty list");
	return self->data[--self->len];
}

static void validate_index(TYPE self, int64_t i)
{
	if (i < 0)
		panic_printf("negative list index %%d", (long)i);
	if (i >= self->len)
		panic_printf("list index %%ld beyond end of list of length %%ld", (long)i, (long)self->len);
}

ITEMTYPE METHOD(get)(TYPE self, int64_t i)
{
	validate_index(self, i);
	INCREF_ITEM(self->data[i]);
	return self->data[i];
}

ITEMTYPE METHOD(delete_at_index)(TYPE self, int64_t i)
{
	validate_index(self, i);
	ITEMTYPE item = self->data[i];
	self->len--;
	memmove(self->data+i, self->data+i+1, (self->len - i)*sizeof(self->data[0]));
	return item;
}

static TYPE slice(TYPE self, int64_t start, int64_t end, bool del)
{
	if (start < 0)
		start = 0;
	if (end > self->len)
		end = self->len;

	TYPE res = CONSTRUCTOR();
	if (start < end) {
		set_length(res, end-start);
		memcpy(res->data, &self->data[start], res->len*sizeof(self->data[0]));
		if (del) {
			memmove(&self->data[start], &self->data[end], (self->len - end)*sizeof(self->data[0]));
			self->len -= res->len;
		} else {
			for (int64_t i = 0; i < res->len; i++)
				INCREF_ITEM(res->data[i]);
		}
	}
	return res;
}

TYPE METHOD(slice)(TYPE self, int64_t start, int64_t end)
{
	return slice(self, start, end, false);
}

TYPE METHOD(delete_slice)(TYPE self, int64_t start, int64_t end)
{
	return slice(self, start, end, true);
}

ITEMTYPE METHOD(first)(TYPE self)
{
	if (self->len == 0)
		panic_printf("can't get first item of empty list");
	INCREF_ITEM(self->data[0]);
	return self->data[0];
}

ITEMTYPE METHOD(last)(TYPE self)
{
	if (self->len == 0)
		panic_printf("can't get last item of empty list");
	INCREF_ITEM(self->data[self->len - 1]);
	return self->data[self->len - 1];
}

bool METHOD(__contains)(TYPE self, ITEMTYPE item)
{
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEMTYPE_METHOD(equals)(self->data[i], item))
			return true;
	}
	return false;
}

int64_t METHOD(find_first)(TYPE self, ITEMTYPE item)
{
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEMTYPE_METHOD(equals)(self->data[i], item))
			return i;
	}
	panic_printf("find_first: item not found");
}

int64_t METHOD(find_last)(TYPE self, ITEMTYPE item)
{
	for (int64_t i = self->len - 1; i >= 0; i--) {
		if (ITEMTYPE_METHOD(equals)(self->data[i], item))
			return i;
	}
	panic_printf("find_last: item not found");
}

int64_t METHOD(find_only)(TYPE self, ITEMTYPE item)
{
	int64_t found = -1;
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEMTYPE_METHOD(equals)(self->data[i], item)) {
			if (found != -1)
				panic_printf("find_only: item found multiple times");
			found = i;
		}
	}
	if (found == -1)
		panic_printf("find_only: item not found");
	return found;
}

void METHOD(delete_first)(TYPE self, ITEMTYPE item)
{
	ITEMTYPE deleted = METHOD(delete_at_index)(self, METHOD(find_first)(self, item));
	DECREF_ITEM(deleted);
}

void METHOD(delete_last)(TYPE self, ITEMTYPE item)
{
	ITEMTYPE deleted = METHOD(delete_at_index)(self, METHOD(find_last)(self, item));
	DECREF_ITEM(deleted);
}

void METHOD(delete_only)(TYPE self, ITEMTYPE item)
{
	ITEMTYPE deleted = METHOD(delete_at_index)(self, METHOD(find_only)(self, item));
	DECREF_ITEM(deleted);
}

bool METHOD(starts_with)(TYPE self, TYPE prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t i = 0; i < prefix->len; i++)
		if (!ITEMTYPE_METHOD(equals)(self->data[i], prefix->data[i]))
			return false;
	return true;
}

bool METHOD(ends_with)(TYPE self, TYPE prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t s=self->len-1, p=prefix->len-1; p >= 0; s--,p--)
		if (!ITEMTYPE_METHOD(equals)(self->data[s], prefix->data[p]))
			return false;
	return true;
}

int64_t METHOD(length)(TYPE self)
{
	return self->len;
}

// TODO: rewrite better in the language itself?
struct class_Str METHOD(to_string)(TYPE self)
{
	struct class_Str res = cstr_to_string("[");

	for (int64_t i = 0; i < self->len; i++) {
		if (i != 0) {
			oomph_string_concat_inplace(&res, ", ");
		}

		struct class_Str s = ITEMTYPE_METHOD(to_string)(self->data[i]);
		struct class_Str res2 = oomph_string_concat(res, s);
		string_decref(s);
		string_decref(res);
		res = res2;
	}

	oomph_string_concat_inplace(&res, "]");
	return res;
}

TYPE METHOD(reversed)(TYPE self)
{
	TYPE res = CONSTRUCTOR();
	set_length(res, self->len);
	for (int64_t i = 0; i < self->len; i++) {
		res->data[i] = self->data[self->len - 1 - i];
		INCREF_ITEM(res->data[i]);
	}
	return res;
}
