Bugs:
- ref cycles are not prevented or garbage collected
- maybe still a few reference counting bugs left, not sure

Missing features needed to write compiler in the language itself:
- multiline strings
- `\n`, `\t` etc inside strings
- foreach
- io
- union types
- forward-declaring a class

Other missing features:
- `if cond then a else b`
- named arguments
- default values of arguments
- do we want more implicit int to float conversion? `print_float(2)`
- string methods
    - reverse
    - find occurrence of substring
        - last occurrence
        - all occurrences
        - only occurrence, failing if multiple are found
    - upper and lower (need unicode lib?)
- should `self` be keyword?
- chained equalities `a == b == c`
- `x++`
- `+=`
- arrays:
    - `[a, b, c]` syntax
    - js-style methods (needs lambdas) or list comprehensions
- generics
    - defining generic classes or functions
    - tuples
    - mappings
- automatic types
    - `null[Str]` --> `null[auto]`
    - `null[auto]` --> `null`
    - `new List[Str]()` --> `[]`
- some nice way to check if an object is null (for at least `if` and `while`)
- non-ref-counted pass-by-value classes
- for pointer types, use C `NULL` to represent `null`?
- avoid using lots of `strlen`
- `starts_with` + `slice` string method
- `list + list`
- `list.starts_with` and `ends_with`
