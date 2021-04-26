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

void oomph_io_delete(struct String path)
{
	char *s = string_to_cstr(path);
	if (remove(s) != 0)
		panic_printf_errno("deleting \"%s\" failed", s);
	free(s);
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

	size_t bufsz = BUFSIZ, len = 0;
	char *buf = malloc(bufsz);
	assert(buf);

	size_t n;
	while (( n = fread(buf+len, 1, bufsz-len, f) )) {
		// TODO: this looks like it can be simplified
		len += n;
		assert(len <= bufsz);
		bufsz *= 2;
		buf = realloc(buf, bufsz);
		assert(buf);
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
