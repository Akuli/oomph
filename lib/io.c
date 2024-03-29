#define _POSIX_C_SOURCE 1
#include "oomph.h"
#include <errno.h>
#include <fcntl.h>
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

bool oomph_io_write_file(struct String path, struct String content, bool must_create)
{
	char *pathstr = string_to_cstr(path);

	int fd = open(pathstr, O_CREAT | O_WRONLY | O_TRUNC | (must_create?O_EXCL:0), 0777);
	if (fd == -1) {
		if (errno == EEXIST) {
			free(pathstr);
			return false;
		}
		panic_printf_errno("opening file \"%s\" failed", pathstr);
	}

	FILE *f = fdopen(fd, "w");
	if (!f)
		panic_printf_errno("opening file \"%s\" failed", pathstr);

	size_t n = fwrite(string_data(content), 1, content.nbytes, f);
	if (n != content.nbytes || fflush(f) != 0)
		panic_printf_errno("writing to file \"%s\" failed", pathstr);

	free(pathstr);
	fclose(f);
	return true;
}
