#ifndef LIB_H
#define LIB_H

#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define REFCOUNT_HEADER int64_t refcount;

struct class_Str {
	REFCOUNT_HEADER
	char str[];   // flexible array member, ends with \0, valid utf-8
};
struct class_Str *cstr_to_string(const char *s);
void string_concat_inplace(struct class_Str **res, const char *suf);
bool string_validate_utf8(const char *s);
#define dtor_Str free

struct class_Str *io_read_file(const struct class_Str *path);
void io_mkdir(const struct class_Str *path);
void io_print(const struct class_Str *s);
void io_write_file(const struct class_Str *path, const struct class_Str *content);
void oomph_assert(bool cond, int64_t lineno);

double meth_Str_to_float(const struct class_Str *s);
int64_t meth_Str_find_first(const struct class_Str *s, const struct class_Str *sub);
int64_t meth_Str_length(const struct class_Str *s);
int64_t meth_Str_to_int(const struct class_Str *s);
int64_t meth_Str_unicode_length(const struct class_Str *s);
int64_t meth_float_ceil(double d);
int64_t meth_float_floor(double d);
int64_t meth_float_round(double d);
int64_t meth_float_truncate(double d);
struct class_Str *meth_Str_slice(const struct class_Str *s, int64_t start, int64_t end);
struct class_Str *meth_Str_to_string(struct class_Str *s);
struct class_Str *meth_float_to_string(double d);
struct class_Str *meth_int_to_string(int64_t n);

// Class implemented in C, method implemented in oomph
#define meth_List_Str_join func___string_join
#define meth_Str_center_pad func___string_center_pad
#define meth_Str_count func___string_count
#define meth_Str_ends_with func___string_ends_with
#define meth_Str_left_pad func___string_left_pad
#define meth_Str_left_trim func___string_left_trim
#define meth_Str_repeat func___string_repeat
#define meth_Str_replace func___string_replace
#define meth_Str_right_pad func___string_right_pad
#define meth_Str_right_trim func___string_right_trim
#define meth_Str_split func___string_split
#define meth_Str_starts_with func___string_starts_with
#define meth_Str_trim func___string_trim
#define meth_bool_to_string func___bool_to_string

/*
Can't be macros because of assumptions that compiler makes:
- Can be used in comma expressions, as in (decref(ptr), (ptr = new_value))
- Only evaluates argument once
*/
void incref(void *ptr);
void decref(void *ptr, void (*destructor)(void *ptr));

// Special functions. Keep up to date with typer.py.
#define bool_eq(a, b) ((a)==(b))
#define bool_not(a) (!(a))
#define float_add(a, b) ((a)+(b))
#define float_div(a, b) ((a)/(b))
#define float_eq(a, b) ((a)==(b))
#define float_gt(a, b) ((a)>(b))
#define float_mul(a, b) ((a)*(b))
#define float_neg(a) (-(a))
#define float_sub(a, b) ((a)-(b))
#define int2float(x) ((double)(x))
#define int_add(a, b) ((a)+(b))
#define int_eq(a, b) ((a)==(b))
#define int_gt(a, b) ((a)>(b))
#define int_mul(a, b) ((a)*(b))
#define int_neg(a) (-(a))
#define int_sub(a, b) ((a)-(b))
#define string_eq(a, b) (strcmp((a)->str, (b)->str) == 0)
double float_mod(double a, double b);
int64_t int_mod(int64_t a, int64_t b);
struct class_Str *string_concat(const struct class_Str *str1, const struct class_Str *str2);

#endif   // LIB_H
