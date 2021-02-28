#ifndef LIB_H
#define LIB_H

#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

#define REFCOUNT_HEADER int64_t refcount;

struct String {
	REFCOUNT_HEADER
	char str[];   // flexible array member, ends with \0, valid utf-8
};

void var_print(const struct String *s);
void var_print_int(int64_t x);
void var_print_bool(bool b);
void var_print_float(double d);

int64_t meth_float_floor(double d);
int64_t meth_float_ceil(double d);
int64_t meth_float_truncate(double d);
int64_t meth_float_round(double d);

struct String *string_concat(const struct String *str1, const struct String *str2);

void incref(void *ptr);
void decref(void *ptr);

#endif
