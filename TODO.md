Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be

Missing features:
- subtraction
- prefix minus (`-2` is currently invalid syntax)
- float to int conversion
- if, for, while
- strings and other arrays
- non-ref-counted pass-by-value classes

Messiness:
- `int` should be called `Int` since it's a type
