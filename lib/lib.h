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
#define float_mul(a, b) ((a)*(b))
#define float_neg(a) (-(a))
#define float_sub(a, b) ((a)-(b))
#define int2float(x) ((double)(x))
#define int_add(a, b) ((a)+(b))
#define int_eq(a, b) ((a)==(b))
#define int_mul(a, b) ((a)*(b))
#define int_neg(a) (-(a))
#define int_sub(a, b) ((a)-(b))
struct String *string_concat(const struct String *str1, const struct String *str2);

#endif
