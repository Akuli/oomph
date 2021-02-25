import sys

from compiler import c_output, parser, tokenizer, typecheck


def main() -> None:
    print('#include "../lib/lib.h"')

    parsed = parser.parse_file(tokenizer.tokenize(sys.stdin.read()))
    typecheck.check_program(parsed)
    for toplevel_statement in parsed:
        c_output.emit_toplevel_statement(toplevel_statement)


main()
