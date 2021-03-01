Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be
- loop variables leak

Missing features:
- do we want more implicit int to float conversion? `print_float(2)`
- default values of arguments
- string methods
    - reverse
    - find occurrence of substring
        - last occurrence
        - all occurrences
        - only occurrence, failing if multiple are found
    - split and join
    - upper and lower (need unicode lib?)
- should `self` be keyword?
- chained equalities `a == b == c`
- `x++`
- `+=`
- generics
    - defining generic classes or functions
    - tuples
    - arrays
    - mappings
- io
- non-ref-counted pass-by-value classes
