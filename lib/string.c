#include "lib.h"
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

static struct class_Str *alloc_string(size_t len)
{
	struct class_Str *res = malloc(sizeof(struct class_Str) + len + 1);
	assert(res);
	res->refcount = 1;
	return res;
}

struct class_Str *cstr_to_string(const char *s)
{
	struct class_Str *res = alloc_string(strlen(s));
	strcpy(res->str, s);
	return res;
}

struct class_Str *meth_Str_to_string(struct class_Str *s)
{
	incref(s);
	return s;
}

/*
struct class_Str *string_concat(const struct class_Str *strs[])
{
	size_t len=0;
	size_t n;
	for (n=0; strs[n]; n++)
		len += strlen(strs[n]->str);

	struct class_Str *res = malloc(sizeof(struct class_Str) + len + 1);
	assert(res);

	char *ptr = res->str;
	for (size_t i=0; i<n; i++){
		strcpy(ptr, strs[i]->str);
		ptr += strlen(strs[i]->str);
	}
	return res;
}
*/

void string_concat_inplace(struct class_Str **res, const char *suf)
{
	// TODO: do we always need to make a new string?
	struct class_Str *old = *res;
	*res = alloc_string(strlen(old->str) + strlen(suf));
	strcpy((*res)->str, old->str);
	strcat((*res)->str, suf);
	decref(old, dtor_Str);
}

struct class_Str *string_concat(const struct class_Str *str1, const struct class_Str *str2)
{
	struct class_Str *res = alloc_string(strlen(str1->str) + strlen(str2->str));
	strcpy(res->str, str1->str);
	strcat(res->str, str2->str);
	return res;
}

int64_t meth_Str_length(const struct class_Str *s)
{
	// TODO: optimize
	return strlen(s->str);
}

// example: ONES(6) is 111111 in binary
#define ONES(n) ((1<<(n))-1)

// https://en.wikipedia.org/wiki/UTF-8#Encoding
static bool is_utf8_continuation_byte(unsigned char c)
{
	return (c >> 6 == 1 << 1);  // 10xxxxxx
}
static int parse_utf8_start_byte(unsigned char c)
{
	if (c >> 7 == 0)  // 0xxxxxxx
		return 1;
	if (c >> 5 == ONES(2) << 1)  // 110xxxxx
		return 2;
	if (c >> 4 == ONES(3) << 1)  // 1110xxxx
		return 3;
	if (c >> 3 == ONES(4) << 1)  // 11110xxx
		return 4;
	assert(0);
}

int64_t meth_Str_unicode_length(const struct class_Str *s)
{
	const char *str = s->str;
	int64_t res = 0;
	while (str[0]) {
		str += parse_utf8_start_byte(str[0]);
		res++;
	}
	return res;
}

// TODO: for most uses, it is inefficient to allocate a new object
struct class_Str *meth_Str_slice(const struct class_Str *s, int64_t start, int64_t end)
{
	int64_t len = strlen(s->str);
	if (start < 0)
		start = 0;
	if (start > len)
		start = len;
	if (end < 0)
		end = 0;
	if (end > len)
		end = len;
	if (start >= end)
		return cstr_to_string("");

	assert(!is_utf8_continuation_byte(s->str[start]));  // TODO: would unicode strings be better?
	if (end == len)
		return cstr_to_string(&s->str[start]);

	assert(!is_utf8_continuation_byte(s->str[end]));
	struct class_Str *res = alloc_string(end - start);
	memcpy(res->str, &s->str[start], end - start);
	res->str[end - start] = '\0';
	return res;
}

int64_t meth_Str_find_first(const struct class_Str *s, const struct class_Str *sub)
{
	const char *ptr = strstr(s->str, sub->str);
	if (!ptr)
		return -1;   // TODO: optional type instead
	return ptr - s->str;
}
