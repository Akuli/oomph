Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be
- loop variables leak

Missing features:
- do we want more implicit int to float conversion? `print_float(2)`
- default values of arguments
- string methods
    - reverse
    - find first/last/only/all occurence of substring
    - count occurrences of substring
    - split and join
    - strip, left strip, right strip (ascii whitespace only)
    - upper and lower (need unicode lib?)
    - replace (borrow logic from asda)
- should `self` be keyword?
- chained equalities `a == b == c`
- `x++`
- `+=`
- `>`, `<=`, `>=` (but there is already `<`)
- generics
    - optionals
    - arrays
    - mappings
- io
- non-ref-counted pass-by-value classes
