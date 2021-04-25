#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Used to decref objects with possibly different types
struct DestroyCallback {
	void (*func)(void *arg);
	void *arg;
};

struct IntFunc {
	int (*func)(void *data, int, int);
	void *data;
	struct DestroyCallback *dclist;  // NULL terminated or just NULL
};

void call_intfunc(struct IntFunc f)
{
	int res = f.func(f.data, 1, 2);
	printf("1 + 2 = %d\n", res);
}

void free_intfunc(struct IntFunc f)
{
	if (f.dclist) {
		for (size_t i = 0; f.dclist[i].func; i++)
			f.dclist[i].func(f.dclist[i].arg);
	}
	free(f.dclist);
}

int add_direct(void *data, int a, int b) { return a+b; }
int add_with_data(void *data, int a, int b) {
	printf("partial: %s\n", (char*)data);
	return a + b;
}

int main(void)
{
	char *data = malloc(4);
	strcpy(data, "lol");

	struct IntFunc add = {
		.func = add_with_data,
		.data = data,
	};
	add.dclist = malloc(sizeof(add.dclist[0]) * 2);
	add.dclist[0] = (struct DestroyCallback){ free, data };
	add.dclist[1] = (struct DestroyCallback){ NULL, NULL };
	call_intfunc(add);
	free_intfunc(add);

	struct IntFunc simple = { add_direct, NULL, NULL };
	call_intfunc(simple);
	free_intfunc(simple);

	return 0;
}
