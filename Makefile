CFLAGS += -fsanitize=undefined -fsanitize=address
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
CFLAGS += -Werror=incompatible-pointer-types
CFLAGS += -Werror=implicit-function-declaration
CFLAGS += -Werror=discarded-qualifiers
CFLAGS += -Werror=stack-usage=50000
CFLAGS += -Wno-unused-parameter
CFLAGS += -Wno-unused-variable
CFLAGS += -g

SRC := $(wildcard lib/*.c)
OBJ := $(SRC:lib/%.c=obj/%.o)
HEADERS := lib/lib.h

temp/%.c: %.code $(wildcard compiler/*.py)
	mkdir -p $(@D) && python3 -m compiler $< $@

obj/%.o: lib/%.c $(HEADERS)
	mkdir -p $(@D) && $(CC) -c -o $@ $< $(CFLAGS)

build/%: temp/%.c $(OBJ) $(HEADERS)
	mkdir -p $(@D) && $(CC) $(CFLAGS) $< $(OBJ) -o $@ $(LDFLAGS)

clean:
	rm -rvf temp obj build

.PRECIOUS: obj/%.o
