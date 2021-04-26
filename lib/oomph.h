#ifndef LIB_H
#define LIB_H

#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdnoreturn.h>
#include <string.h>

#define REFCOUNT_HEADER int64_t refcount;

// Used to decref objects with possibly different types
struct DestroyCallback {
	void (*func)(void *arg);
	void *arg;
};

// Can be shared by multiple string for efficient substrings
struct StringBuf {
	REFCOUNT_HEADER
	char *data;
	bool malloced;  // can you e.g. do free(buf->data)
	size_t len;     // strings don't use StringBuf beyond this, but more space may be malloced
	char flex[];    // allows allocating StringBuf and data at once, not used otherwise
};

struct String {
	// don't try to change the buf of a string after creating string, is difficult
	struct StringBuf *buf;
	size_t nbytes;
	size_t offset;
};

const char *string_data(struct String s);
void string_buf_destructor(void *ptr);
#define incref_Str(s) incref((s).buf)
#define decref_Str(s) decref((s).buf, string_buf_destructor)

bool string_validate_utf8(const char *data, size_t len);
struct String data_to_string(const char *data, size_t len);

struct String cstr_to_string(const char *s);
char *string_to_cstr(struct String s);

void oomph_string_concat_inplace(struct String *res, struct String suf);
void oomph_string_concat_inplace_cstr(struct String *res, const char *suf);

// panic_printf_errno includes value of errno when nonzero
noreturn void panic_printf_errno(const char *fmt, ...);
#define panic_printf(...) (errno = 0, panic_printf_errno(__VA_ARGS__))

// Currently it's not easy to return a list of strings from C function
int64_t oomph_argv_count(void);
struct String oomph_argv_get(int64_t i);

bool meth_Str_ends_with(struct String s, struct String suf);
bool meth_Str_starts_with(struct String s, struct String pre);
int64_t oomph_get_utf8_byte(struct String s, int64_t i);
int64_t oomph_run_subprocess(void *args);
int64_t oomph_utf8_len(struct String s);
noreturn void oomph_exit(int64_t status);
struct String meth_Str_remove_prefix(struct String s, struct String pre);
struct String meth_Str_remove_suffix(struct String s, struct String suf);
struct String oomph_get_first_char(struct String s);
struct String oomph_hash(struct String data, struct String algname);
struct String oomph_io_read_file(struct String path);
struct String oomph_slice_until_substring(struct String s, struct String sep);
void oomph_assert(bool cond, struct String path, int64_t lineno);
void oomph_io_delete_at_exit(struct String path);
void oomph_io_mkdir(struct String path);
void oomph_io_write_file(struct String path, struct String content);
void oomph_print(struct String str);

#define meth_Bool_equals(a, b) ((a)==(b))
#define meth_Bool_hash(a) (a)   // 0 or 1
#define meth_Float_equals(a, b) ((a)==(b))
#define meth_Int_equals(a, b) ((a)==(b))
#define meth_Int_hash(a) (a)
#define meth_null_equals(a, b) true
#define meth_null_hash(n) 69
#define meth_null_to_string(n) cstr_to_string("null")
bool meth_Str_equals(struct String a, struct String b);
double meth_Str_to_float(struct String s);
int64_t meth_Float_ceil(double d);
int64_t meth_Float_floor(double d);
int64_t meth_Float_round(double d);
int64_t meth_Float_truncate(double d);
int64_t meth_Str_hash(struct String s);
int64_t meth_Str_length(struct String s);
int64_t meth_Str_to_int(struct String s);
struct String meth_Float_to_string(double d);
struct String meth_Int_to_string(int64_t n);
struct String meth_Str_to_string(struct String s);

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
struct String oomph_string_concat(struct String str1, struct String str2);

#define oomph_false false
#define oomph_null 0
#define oomph_true true

#define pointer_hash(p) (((int64_t)(intptr_t)(p)) >> 5)

#endif   // LIB_H
