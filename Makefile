#CFLAGS += -fsanitize=undefined -fsanitize=address
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
CFLAGS += -Werror=incompatible-pointer-types
CFLAGS += -Werror=implicit-function-declaration
CFLAGS += -Werror=discarded-qualifiers
CFLAGS += -Werror=stack-usage=50000
CFLAGS += -Wno-unused-parameter
CFLAGS += -Wno-unused-variable
CFLAGS += -Wno-unused-but-set-variable
CFLAGS += -Wno-unused-label
CFLAGS += -g
LDFLAGS += -lm

SRC := $(wildcard lib/*.c)
OBJ := $(SRC:lib/%.c=obj/%.o)
HEADERS := lib/oomph.h

all: $(OBJ) obj/compile_info.txt

obj/%.o: lib/%.c $(HEADERS) Makefile
	mkdir -p $(@D) && $(CC) -c -o $@ $< $(CFLAGS)

obj/compile_info.txt: Makefile
	# The compiler emits unused functions. It's fine.
	mkdir -p $(@D) && printf "cc=%s\ncflags=%s\nldflags=%s\n" "$(CC)" "$(CFLAGS) -Wno-unused-function" "$(LDFLAGS)" > $@

clean:
	rm -rvf obj test_out
	find -name .oomph-cache -exec rm -rvf {} +
