Bugs:
- ref cycles are not prevented or garbage collected
- new refs are not created in every case where they should be

Missing features:
- operators `+ - * /`
- floats
- boolean not
- if, for, while
- strings and other arrays
- non-ref-counted pass-by-value classes

Messiness:
- `int` should be called `Int` since it's a type
