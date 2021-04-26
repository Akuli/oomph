#include "oomph.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>

void oomph_print(struct String str)
{
	fwrite(string_data(str), 1, str.nbytes, stdout);
	putchar('\n');
}

// I wish there was a way to pass arguments to atexit()
static struct String global_delete_list[100];
static size_t global_delete_list_len = 0;

static void atexit_callback(void)
{
	for (size_t i = 0; i < global_delete_list_len; i = i+1) {
		char *s = string_to_cstr(global_delete_list[i]);
		decref_Str(global_delete_list[i]);

		if (remove(s) != 0)
			panic_printf_errno("io::delete_at_exit failed to delete %s", s);
		free(s);
	}
}

void oomph_io_delete_at_exit(struct String path)
{
	if (global_delete_list_len == 0)
		atexit(atexit_callback);

	size_t max = sizeof(global_delete_list)/sizeof(global_delete_list[0]);
	if (global_delete_list_len >= max)
		panic_printf("io::delete_at_exit() called more than %zu times", max);

	global_delete_list[global_delete_list_len++] = path;
	incref_Str(path);
}

void oomph_io_mkdir(struct String path)
{
	char *s = string_to_cstr(path);
	if (mkdir(s, 0777) == -1 && errno != EEXIST)
		panic_printf_errno("creating directory \"%s\" failed", s);
	free(s);
}

struct String oomph_io_read_file(struct String path)
{
	char *pathstr = string_to_cstr(path);
	FILE *f = fopen(pathstr, "r");
	if (!f)
		panic_printf_errno("opening file \"%s\" failed", pathstr);

	char *buf = NULL;
	size_t len = 0;

	for (size_t alloced = BUFSIZ; !feof(f) && !ferror(f); alloced *= 2) {
		buf = realloc(buf, alloced);
		assert(buf);
		len += fread(buf+len, 1, alloced-len, f);
	}

	if (ferror(f))
		panic_printf_errno("reading file \"%s\" failed", pathstr);
	fclose(f);

	if (!string_validate_utf8(buf, len))
		panic_printf("invalid utf-8 in \"%s\"", pathstr);

	struct String res = data_to_string(buf, len);
	free(pathstr);
	free(buf);
	return res;
}

void oomph_io_write_file(struct String path, struct String content)
{
	char *pathstr = string_to_cstr(path);
	FILE *f = fopen(pathstr, "w");
	if (!f)
		panic_printf_errno("opening file \"%s\" failed", pathstr);

	size_t n = fwrite(string_data(content), 1, content.nbytes, f);
	if (n != content.nbytes || fflush(f) != 0)
		panic_printf_errno("writing to file \"%s\" failed", pathstr);

	free(pathstr);
	fclose(f);
}
