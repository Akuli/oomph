#include "lib.h"
#include <assert.h>
#include <string.h>
#include <stdarg.h>

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
