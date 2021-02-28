Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be
- loop variables leak

Missing features:
- do we want more implicit int to float conversion? `print_float(2)`
- chained equalities `a == b == c`
- `x++`
- `to_string()` methods
    - automatically call `to_string()` in string formatting
- string to int
- string to float
- rethink how to name classes (`Str` and `int` feels weird)
- generics
    - arrays
    - optionals
- non-ref-counted pass-by-value classes
