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

# tcc doesn't have <stdnoreturn.h>
# https://stackoverflow.com/a/37741652
ifeq ($(findstring tcc,$(CC)),tcc)
CFLAGS += -Dnoreturn=
endif

SRC := $(wildcard lib/*.c)
OBJ := $(SRC:lib/%.c=obj/%.o)
HEADERS := lib/oomph.h

all: $(OBJ) obj/compile_info.txt

obj/%.o: lib/%.c $(HEADERS) Makefile
	mkdir -p $(@D) && $(CC) -c -o $@ $< $(CFLAGS)

obj/compile_info.txt: Makefile
	mkdir -p $(@D) && printf "cc=%s\ncflags=%s\nldflags=%s\n" "$(CC)" "$(CFLAGS)" "$(LDFLAGS)" > $@

# self-hosted compiler
oomphc: $(OBJ) obj/compile_info.txt $(wildcard pyoomph/*.py self_hosted/*.oomph)
	python3 -m pyoomph --verbose self_hosted/main.oomph -o $@

clean:
	rm -rvf obj test_out oomphc
	find -name .oomph-cache -exec rm -rvf {} +
