Bugs:
- ref cycles are not prevented or garbage collected
- maybe still a few reference counting bugs left, not sure

Missing features needed to write compiler in the language itself:
- multiline strings
- `\n`, `\t` etc inside strings
- string split and join
- foreach
- io

Other missing features:
- `if cond then a else b`
- named arguments
- do we want more implicit int to float conversion? `print_float(2)`
- default values of arguments
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
- some nice way to check if an object is null
- non-ref-counted pass-by-value classes
