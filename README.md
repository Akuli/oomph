# oomph
This is yet another attempt at making a usable programming language.

Commands:

```
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
make
./test
./lint
```

Test script passes its argument to oomph, try e.g. `./test --valgrind`

Type `python3 -m oomph foo.oomph` to compile and run `foo.oomph`.


## The language

- Compiles to C, aims to be high-level but faster than Python
- See example files in `tests` to get started
- Refcounted types are named `LikeThis`, non-refcounted pass-by-value types `like_this`

Bugs:
- ref cycles are not prevented or garbage collected
- maybe still a few reference counting bugs left, not sure

Missing features needed to write the oomph compiler in oomph:
- `\n`, `\t` etc inside strings
- foreach
- io
- union types
- forward-declaring a class

Other missing features:
- negative slices?
- `Str.replace(mapping)` (I wish python had this)
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
