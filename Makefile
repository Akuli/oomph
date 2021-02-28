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
HEADERS := lib/lib.h

all: $(OBJ) obj/compile_info.txt

obj/%.o: lib/%.c $(HEADERS)
	mkdir -p $(@D) && $(CC) -c -o $@ $< $(CFLAGS)

obj/compile_info.txt:
	mkdir -p $(@D) && printf "cc=%s\ncflags=%s\nldflags=%s\n" "$(CC)" "$(CFLAGS)" "$(LDFLAGS)" > $@

clean:
	rm -rvf obj test.out
	find -name .compiler-cache -exec rm -rvf {} +
