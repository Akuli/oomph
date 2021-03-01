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

static int utf8_chars_in_beginning(unsigned char c)
{
	// https://en.wikipedia.org/wiki/UTF-8
	if (c >> 7 == 0)
		return 1;
	if (c >> 5 == ONES(2) << 1)
		return 2;
	if (c >> 4 == ONES(3) << 1)
		return 3;
	if (c >> 3 == ONES(4) << 1)
		return 4;
	assert(0);  // invalid utf8
}

int64_t meth_Str_unicode_length(const struct class_Str *s)
{
	const char *str = s->str;
	int64_t res = 0;
	while (*str) {
		str += utf8_chars_in_beginning(str[0]);
		res++;
	}
	return res;
}
