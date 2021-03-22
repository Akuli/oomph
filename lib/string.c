#include "oomph.h"
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

struct class_Str *string_concat(const struct class_Str *str1, const struct class_Str *str2)
{
	struct class_Str *res = alloc_string(strlen(str1->str) + strlen(str2->str));
	strcpy(res->str, str1->str);
	strcat(res->str, str2->str);
	return res;
}

void string_concat_inplace(struct class_Str **res, const char *suf)
{
	// TODO: do we always need to make a new string?
	struct class_Str *old = *res;
	*res = alloc_string(strlen(old->str) + strlen(suf));
	strcpy((*res)->str, old->str);
	strcat((*res)->str, suf);
	decref(old, dtor_Str);
}

struct class_Str *meth_Str_to_string(struct class_Str *s)
{
	// Returns a programmer-readable string, print does not use this
	// TODO: escape quotes?
	int64_t len = strlen(s->str);
	struct class_Str *res = alloc_string(len+2);
	strcpy(res->str, "\"");
	strcat(res->str, s->str);
	strcat(res->str, "\"");
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

bool string_validate_utf8(const char *s)
{
	while(*s) {
		int n = parse_utf8_start_byte(s[0]);
		switch(n){
			case 1:
				break;
			case 2:
				if (!is_utf8_continuation_byte(s[1])) return false;
				break;
			case 3:
				if (!is_utf8_continuation_byte(s[1])) return false;
				if (!is_utf8_continuation_byte(s[2])) return false;
				break;
			case 4:
				if (!is_utf8_continuation_byte(s[1])) return false;
				if (!is_utf8_continuation_byte(s[2])) return false;
				if (!is_utf8_continuation_byte(s[3])) return false;
				break;
			default:
				assert(0);
		}
		s+=n;
	}
	return true;
}

bool meth_Str_has_continuation_byte_at(const struct class_Str *s, int64_t i)
{
	return (0 <= i && i < (int64_t)strlen(s->str) && is_utf8_continuation_byte(s->str[i]));
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
	if (is_utf8_continuation_byte(s->str[start]))
		panic_printf("can't slice string in the middle of continuation byte");

	if (end == len)
		return cstr_to_string(&s->str[start]);
	if (is_utf8_continuation_byte(s->str[end]))
		panic_printf("can't slice string in the middle of continuation byte");

	struct class_Str *res = alloc_string(end - start);
	memcpy(res->str, &s->str[start], end - start);
	res->str[end - start] = '\0';
	return res;
}

static struct class_Str *slice_from_start(struct class_Str *s, size_t len)
{
	assert(strlen(s->str) >= len);
	// TODO: avoid temporary allocation
	char *tmp = malloc(len + 1);
	assert(tmp);
	memcpy(tmp, s->str, len);
	tmp[len] = '\0';
	struct class_Str *res = cstr_to_string(tmp);
	free(tmp);
	return res;
}

struct class_Str *string_remove_prefix(struct class_Str *s, struct class_Str *pre)
{
	size_t n = strlen(pre->str);
	if (strlen(s->str) >= n && memcmp(s->str, pre->str, n) == 0)
		return cstr_to_string(s->str + strlen(pre->str));
	incref(s);
	return s;
}

struct class_Str *string_remove_suffix(struct class_Str *s, struct class_Str *suf)
{
	size_t slen=strlen(s->str), suflen=strlen(suf->str);
	if (slen >= suflen && memcmp(s->str + slen - suflen, suf->str, suflen) == 0)
		return slice_from_start(s, slen - suflen);
	incref(s);
	return s;
}

// python's string.split(sep)[0]
struct class_Str *string_from_start_to(struct class_Str *s, struct class_Str *sep)
{
	char *ptr = strstr(s->str, sep->str);
	if (!ptr) {
		incref(s);
		return s;
	}
	return slice_from_start(s, ptr - s->str);
}

int64_t string_find_internal(const struct class_Str *s, const struct class_Str *sub)
{
	const char *ptr = strstr(s->str, sub->str);
	if (!ptr)
		return -1;
	return ptr - s->str;
}
