#include "oomph.h"
#include <errno.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/types.h>

void io_print(const struct class_Str *s)
{
	puts(s->str);
}

void io_mkdir(const struct class_Str *path)
{
	if (mkdir(path->str, 0777) == -1)
		assert(errno == EEXIST);
}

struct class_Str *io_read_file(const struct class_Str *path)
{
	FILE *f = fopen(path->str, "r");
	assert(f);

	size_t bufsz = BUFSIZ, len = 0;
	char *buf = malloc(bufsz);
	assert(buf);

	size_t n;
	while (( n = fread(buf+len, 1, bufsz-len-1, f) )) {
		assert(n < bufsz);
		len += n;
		bufsz *= 2;
		buf = realloc(buf, bufsz);
		assert(buf);
	}
	assert(feof(f) && !ferror(f));
	fclose(f);

	for (size_t i = 0; i < len; i++)
		assert(buf[i] != '\0');
	buf[len] = '\0';

	if (!string_validate_utf8(buf)) {
		fprintf(stderr, "invalid utf-8 in \"%s\"\n", path->str);
		fflush(stderr);
		abort();
	}

	struct class_Str *res = cstr_to_string(buf);
	free(buf);
	return res;
}

void io_write_file(const struct class_Str *path, const struct class_Str *content)
{
	FILE *f = fopen(path->str, "w");
	assert(f);
	size_t len = strlen(content->str);
	size_t n = fwrite(content->str, 1, len, f);
	assert(n == len);
	fclose(f);
}
