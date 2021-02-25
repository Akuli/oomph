from typing import Dict

from compiler import c_output, parser, tokenizer, typecheck
from compiler.parser import INT, FunctionType, Type


def main() -> None:
    print('#include <stdint.h>')
    print('#include <stdio.h>')
    print(r'void var_print_int(int64_t x){ printf("%lld\n", (long long)x); }')
    print(r'int64_t var_add(int64_t x, int64_t y){ return x+y; }')

    code = '''
func foo(int x) -> void {
    print_int(x)
}

func main() -> void {
    foo(12345)
    let x = add(1, 2)
    print_int(x)
    print_int(add(1, 2))
}
'''
    var_types: Dict[str, Type] = {
        'add': FunctionType([INT, INT], INT),
        'print_int': FunctionType([INT], None),
    }
    parsed = parser.parse_file(tokenizer.tokenize(code))
    for funcdef in parsed:
        typecheck.check_funcdef(var_types, funcdef)
    for funcdef in parsed:
        c_output.emit_funcdef(funcdef)
    print('int main(void) { var_main(); return 0; }')


main()
