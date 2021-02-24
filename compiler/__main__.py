from compiler import tokenizer, parser, c_output


def main():
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
    var_types = {'add': ('func', ['int', 'int'], 'int'), 'print_int': ('func', ['int'], None)}
    parsed = parser.parse_file(tokenizer.tokenize(code))
    for toplevel in parsed:
        c_output.emit_toplevel(var_types, toplevel)
    print('int main(void) { var_main(); return 0; }')


main()
