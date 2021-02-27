Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be
- loop variables leak

Missing features:
- implicit int to float conversion: `print_float(2)`
- chained equalities `a == b == c`
- `x++`
- while
- strings
- generics
    - arrays
    - optionals
- non-ref-counted pass-by-value classes
