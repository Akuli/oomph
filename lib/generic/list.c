#if %(itemtype_is_string)s
struct class_Str *meth_%(type_cname)s_join(struct class_%(type_cname)s *self, struct class_Str *sep)
{
	return meth_List_Str_join(self, sep);   // Implemented in oomph
}
#endif

struct class_%(type_cname)s *ctor_%(type_cname)s(void)
{
	struct class_%(type_cname)s *res = malloc(sizeof(*res));
	assert(res);
	res->refcount = 1;
	res->len = 0;
	res->data = res->smalldata;
	res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
	return res;
}

void dtor_%(type_cname)s (void *ptr)
{
	struct class_%(type_cname)s *self = ptr;
	for (int64_t i = 0; i < self->len; i++)
		DECREF_ITEM(self->data[i]);
	if (self->data != self->smalldata)
		free(self->data);
	free(self);
}

bool meth_%(type_cname)s_equals(struct class_%(type_cname)s *self, struct class_%(type_cname)s *other)
{
	if (self->len != other->len)
		return false;
	for (int64_t i = 0; i < self->len; i++) {
		if (!ITEM_EQUALS(self->data[i], other->data[i]))
			return false;
	}
	return true;
}

void class_%(type_cname)s_ensure_alloc(struct class_%(type_cname)s *self, int64_t n)
{
	assert(n >= 0);
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

void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val)
{
	class_%(type_cname)s_ensure_alloc(self, self->len + 1);
	self->data[self->len++] = val;
	INCREF_ITEM(val);
}

void meth_%(type_cname)s_push_all(struct class_%(type_cname)s *self, struct class_%(type_cname)s *src)
{
	class_%(type_cname)s_ensure_alloc(self, self->len + src->len);
	memcpy(self->data + self->len, src->data, sizeof(src->data[0]) * src->len);
	for (int64_t i = 0; i < src->len; i++)
		INCREF_ITEM(src->data[i]);
	self->len += src->len;
}

void meth_%(type_cname)s_insert(struct class_%(type_cname)s *self, int64_t index, %(itemtype)s val)
{
	if (index < 0)
		index = 0;
	if (index > self->len)
		index = self->len;

	class_%(type_cname)s_ensure_alloc(self, self->len + 1);
	memmove(self->data + index + 1, self->data + index, (self->len - index)*sizeof(self->data[0]));
	self->data[index] = val;
	self->len++;
	INCREF_ITEM(val);
}

%(itemtype)s meth_%(type_cname)s_pop(struct class_%(type_cname)s *self)
{
	if (self->len == 0)
		panic_printf("pop from empty list");
	return self->data[--self->len];
}

static void validate_index(struct class_%(type_cname)s *self, int64_t i)
{
	if (i < 0)
		panic_printf("negative list index %%d", (long)i);
	if (i >= self->len)
		panic_printf("list index %%ld beyond end of list of length %%ld", (long)i, (long)self->len);
}

%(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i)
{
	validate_index(self, i);
	INCREF_ITEM(self->data[i]);
	return self->data[i];
}

void meth_%(type_cname)s_delete_by_index(struct class_%(type_cname)s *self, int64_t i)
{
	validate_index(self, i);
	DECREF_ITEM(self->data[i]);
	self->len--;
	memmove(self->data+i, self->data+i+1, (self->len - i)*sizeof(self->data[0]));
}

static struct class_%(type_cname)s *slice(struct class_%(type_cname)s *self, int64_t start, int64_t end, bool del)
{
	if (start < 0)
		start = 0;
	if (end > self->len)
		end = self->len;

	struct class_%(type_cname)s *res = ctor_%(type_cname)s();
	if (start < end) {
		class_%(type_cname)s_ensure_alloc(res, end-start);
		res->len = end-start;
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

struct class_%(type_cname)s *meth_%(type_cname)s_slice(struct class_%(type_cname)s *self, int64_t start, int64_t end)
{
	return slice(self, start, end, false);
}

struct class_%(type_cname)s *meth_%(type_cname)s_delete_slice(struct class_%(type_cname)s *self, int64_t start, int64_t end)
{
	return slice(self, start, end, true);
}

%(itemtype)s meth_%(type_cname)s_first(struct class_%(type_cname)s *self)
{
	if (self->len == 0)
		panic_printf("can't get first item of empty list");
	INCREF_ITEM(self->data[0]);
	return self->data[0];
}

%(itemtype)s meth_%(type_cname)s_last(struct class_%(type_cname)s *self)
{
	if (self->len == 0)
		panic_printf("can't get last item of empty list");
	INCREF_ITEM(self->data[self->len - 1]);
	return self->data[self->len - 1];
}

bool meth_%(type_cname)s___contains(struct class_%(type_cname)s *self, %(itemtype)s item)
{
	for (int64_t i = 0; i < self->len; i++) {
		if (ITEM_EQUALS(self->data[i], item))
			return true;
	}
	return false;
}

bool meth_%(type_cname)s_starts_with(struct class_%(type_cname)s *self, struct class_%(type_cname)s *prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t i = 0; i < prefix->len; i++)
		if (!ITEM_EQUALS(self->data[i], prefix->data[i]))
			return false;
	return true;
}

bool meth_%(type_cname)s_ends_with(struct class_%(type_cname)s *self, struct class_%(type_cname)s *prefix)
{
	if (self->len < prefix->len)
		return false;
	for (int64_t s=self->len-1, p=prefix->len-1; p >= 0; s--,p--)
		if (!ITEM_EQUALS(self->data[s], prefix->data[p]))
			return false;
	return true;
}

int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self)
{
	return self->len;
}

// TODO: rewrite better in the language itself
struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self)
{
	struct class_Str *res = cstr_to_string("[");

	for (int64_t i = 0; i < self->len; i++) {
		if (i != 0) {
			string_concat_inplace(&res, ", ");
		}
		struct class_Str *s = meth_%(itemtype_cname)s_to_string(self->data[i]);
		string_concat_inplace(&res, s->str);
		decref(s, dtor_Str);
	}

	string_concat_inplace(&res, "]");
	return res;
}

struct class_%(type_cname)s *meth_%(type_cname)s_reversed(struct class_%(type_cname)s *self)
{
	struct class_%(type_cname)s *res = ctor_%(type_cname)s();
	class_%(type_cname)s_ensure_alloc(res, self->len);
	for (int64_t i = 0; i < self->len; i++) {
		res->data[i] = self->data[self->len - 1 - i];
		INCREF_ITEM(res->data[i]);
	}
	res->len = self->len;
	return res;
}
