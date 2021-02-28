Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be
- loop variables leak

Missing features:
- do we want more implicit int to float conversion? `print_float(2)`
- chained equalities `a == b == c`
- `x++`
- print automatic to_string
- float mod
- generics
    - optionals
    - arrays
    - mappings
- io
- non-ref-counted pass-by-value classes
