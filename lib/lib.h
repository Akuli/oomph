#ifndef LIB_H
#define LIB_H

#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

#define REFCOUNT_HEADER size_t refcount;

void var_print_int(int64_t x);
void var_print_bool(bool b);
void var_print_float(double d);

int64_t meth_float_floor(double d);
int64_t meth_float_ceil(double d);
int64_t meth_float_truncate(double d);
int64_t meth_float_round(double d);

void incref(void *ptr);
void decref(void *ptr);

#endif
