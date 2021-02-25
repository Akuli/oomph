import sys

from compiler import c_output, parser, tokenizer, typer


def main() -> None:
    print('#include "../lib/lib.h"')

    parsed = typer.convert_program(parser.parse_file(tokenizer.tokenize(sys.stdin.read())))
    for toplevel_statement in parsed:
        c_output.emit_toplevel_statement(toplevel_statement)


main()
