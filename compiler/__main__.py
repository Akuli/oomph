import sys
from typing import Dict

from compiler import c_output, parser, tokenizer, typecheck
from compiler.types import INT, FunctionType, Type


def main() -> None:
    print('#include "../lib/lib.h"')

    var_types: Dict[str, Type] = {
        'add': FunctionType([INT, INT], INT),
        'print_int': FunctionType([INT], None),
    }
    parsed = parser.parse_file(tokenizer.tokenize(sys.stdin.read()))
    for funcdef in parsed:
        typecheck.check_funcdef(var_types, funcdef)
    for funcdef in parsed:
        c_output.emit_funcdef(funcdef)


main()
