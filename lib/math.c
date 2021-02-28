#include "lib.h"

int64_t int_mod(int64_t a, int64_t b)
{
	int64_t res = a % b;
	// Make sure result has same sign as b
	if ((b > 0 && res < 0) || (b < 0 && res > 0))
		res += b;
	return res;
}
