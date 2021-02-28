#include "lib.h"
#include <assert.h>
#include <string.h>

/*
struct String *string_concat(const struct String *strs[])
{
	size_t len=0;
	size_t n;
	for (n=0; strs[n]; n++)
		len += strlen(strs[n]->str);

	struct String *res = malloc(sizeof(struct String) + len + 1);
	assert(res);

	char *ptr = res->str;
	for (size_t i=0; i<n; i++){
		strcpy(ptr, strs[i]->str);
		ptr += strlen(strs[i]->str);
	}
	return res;
}
*/

struct String *string_concat(const struct String *str1, const struct String *str2)
{
	size_t len = strlen(str1->str) + strlen(str2->str);
	struct String *res = malloc(sizeof(struct String) + len + 1);
	assert(res);
	res->refcount = 1;
	strcpy(res->str, str1->str);
	strcat(res->str, str2->str);
	return res;
}
