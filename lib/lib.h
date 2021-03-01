#ifndef LIB_H
#define LIB_H

#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define REFCOUNT_HEADER int64_t refcount;

struct class_Str {
	REFCOUNT_HEADER
	char str[];   // flexible array member, ends with \0, valid utf-8
};
struct class_Str *cstr_to_string(const char *s);

void var_print(const struct class_Str *s);
int64_t meth_float_floor(double d);
int64_t meth_float_ceil(double d);
int64_t meth_float_truncate(double d);
int64_t meth_float_round(double d);
struct class_Str *meth_float_to_string(double d);
struct class_Str *meth_int_to_string(int64_t n);
int64_t meth_Str_to_int(const struct class_Str *s);
double meth_Str_to_float(const struct class_Str *s);
int64_t meth_Str_length(const struct class_Str *s);
int64_t meth_Str_unicode_length(const struct class_Str *s);

// Class implemented in C, method implemented in the language itself
#define meth_bool_to_string var___bool_to_string

void incref(void *ptr);
void decref(void *ptr);

// Special functions. Keep up to date with typer.py.
#define bool_and(a, b) ((a) && (b))
#define bool_eq(a, b) ((a)==(b))
#define bool_false() false
#define bool_not(a) (!(a))
#define bool_or(a, b) ((a) || (b))
#define bool_true() true
#define float_add(a, b) ((a)+(b))
#define float_div(a, b) ((a)/(b))
#define float_eq(a, b) ((a)==(b))
double float_mod(double a, double b);
#define float_mul(a, b) ((a)*(b))
#define float_neg(a) (-(a))
#define float_sub(a, b) ((a)-(b))
#define int2float(x) ((double)(x))
#define int_add(a, b) ((a)+(b))
#define int_eq(a, b) ((a)==(b))
int64_t int_mod(int64_t a, int64_t b);
#define int_mul(a, b) ((a)*(b))
#define int_neg(a) (-(a))
#define int_sub(a, b) ((a)-(b))
struct class_Str *string_concat(const struct class_Str *str1, const struct class_Str *str2);
#define string_eq(a, b) (strcmp((a)->str, (b)->str) == 0)

#endif
