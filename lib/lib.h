#ifndef LIB_H
#define LIB_H

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#define REFCOUNT_HEADER size_t refcount;

void var_print_int(int64_t x);
int64_t var_add(int64_t x, int64_t y);
void incref(void *ptr);
void decref(void *ptr);

#endif
