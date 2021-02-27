Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be

Missing features:
- implicit int to float conversion: `print_float(2)`
- chained equalities `a == b == c`
- if, for, while
- strings
- generics
    - arrays
    - optionals
- non-ref-counted pass-by-value classes

Messiness:
- `int` should be called `Int` since it's a type
