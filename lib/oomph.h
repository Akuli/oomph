#ifndef LIB_H
#define LIB_H

#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifndef noreturn
#include <stdnoreturn.h>
#endif

#define REFCOUNT_HEADER int64_t refcount;

struct class_Str {
	REFCOUNT_HEADER
	char str[];   // flexible array member, ends with \0, valid utf-8
};
struct class_Str *cstr_to_string(const char *s);
void oomph_string_concat_inplace(struct class_Str **res, const char *suf);
bool string_validate_utf8(const char *s);
#define dtor_Str free
struct class_List_Str;

// panic_printf_errno includes value of errno when nonzero
noreturn void panic_printf_errno(const char *fmt, ...);
#define panic_printf(...) (errno = 0, panic_printf_errno(__VA_ARGS__))

// Currently it's not easy to return a list of strings from C function
int64_t oomph_argv_count(void);
struct class_Str *oomph_argv_get(int64_t i);

int64_t oomph_get_utf8_byte(struct class_Str *s, int64_t i);
int64_t oomph_run_subprocess(void *args);
struct class_Str *meth_Str_remove_prefix(struct class_Str *s, struct class_Str *pre);
struct class_Str *meth_Str_remove_suffix(struct class_Str *s, struct class_Str *suf);
struct class_Str *oomph_get_first_char(struct class_Str *s);
struct class_Str *oomph_hash(const struct class_Str *data, const struct class_Str *algname);
struct class_Str *oomph_io_read_file(const struct class_Str *path);
struct class_Str *oomph_slice_until_substring(struct class_Str *s, struct class_Str *sep);
void oomph_assert(bool cond, const struct class_Str *path, int64_t lineno);
void oomph_io_mkdir(const struct class_Str *path);
void oomph_io_write_file(const struct class_Str *path, const struct class_Str *content);
void oomph_print(const struct class_Str *s);

#define meth_Bool_equals(a, b) ((a)==(b))
#define meth_Float_equals(a, b) ((a)==(b))
#define meth_Int_equals(a, b) ((a)==(b))
#define meth_Str_equals(a, b) (strcmp((a)->str, (b)->str) == 0)
#define meth_null_equals(a, b) true
#define meth_null_to_string(n) cstr_to_string("null")
double meth_Str_to_float(const struct class_Str *s);
int64_t meth_Float_ceil(double d);
int64_t meth_Float_floor(double d);
int64_t meth_Float_round(double d);
int64_t meth_Float_truncate(double d);
int64_t meth_Str_length(const struct class_Str *s);
int64_t meth_Str_to_int(const struct class_Str *s);
struct class_Str *meth_Float_to_string(double d);
struct class_Str *meth_Int_to_string(int64_t n);
struct class_Str *meth_Str_to_string(struct class_Str *s);

/*
Can't be macros because of assumptions that compiler makes:
- Can be used in comma expressions, as in (decref(ptr), (ptr = new_value))
- Only evaluates argument once
*/
void incref(void *ptr);
void decref(void *ptr, void (*destructor)(void *ptr));

// Special functions. Keep up to date with typer.py.
#define oomph_bool_not(a) (!(a))
#define oomph_float_add(a, b) ((a)+(b))
#define oomph_float_div(a, b) ((a)/(b))
#define oomph_float_gt(a, b) ((a)>(b))
#define oomph_float_mul(a, b) ((a)*(b))
#define oomph_float_neg(a) (-(a))
#define oomph_float_sub(a, b) ((a)-(b))
#define oomph_int2float(x) ((double)(x))
#define oomph_int_add(a, b) ((a)+(b))
#define oomph_int_gt(a, b) ((a)>(b))
#define oomph_int_mul(a, b) ((a)*(b))
#define oomph_int_neg(a) (-(a))
#define oomph_int_sub(a, b) ((a)-(b))
double oomph_float_mod(double a, double b);
int64_t oomph_int_mod(int64_t a, int64_t b);
struct class_Str *oomph_string_concat(const struct class_Str *str1, const struct class_Str *str2);

#define oomph_false false
#define oomph_null 0
#define oomph_true true

// null is first member
#define IS_NULL(unionvar) ((unionvar).membernum == 0)

// self-hosted can't use builtins.oomph yet
#ifdef SELF_HOSTED
	#define meth_Bool_to_string(b) cstr_to_string((b) ? "true" : "false")
#endif

#endif   // LIB_H
