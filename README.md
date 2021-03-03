# oomph
This is yet another attempt at making a usable programming language.

```shell
git clone https://github.com/Akuli/oomph
cd oomph
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
./test
python3 -m oomph tests/hello.oomph   # compile and run hello world file
```

- If you delete or rename files in `lib/`, you may need to run `make clean`.
- Run `./lint` before commit.
- Test script passes its argument to oomph. Try e.g. `./test --valgrind`.


## The language

- Compiles to C, aims to be high-level but faster than Python
- See example files in `tests` to get started
- Some things are implemented in the language itself (see `stdlib.oomph`)
- Refcounted types are named `LikeThis`, non-refcounted pass-by-value types `like_this`

Bugs:
- ref cycles are not prevented or garbage collected
- maybe still a few reference counting bugs left, not sure

Missing features needed to write the oomph compiler in oomph:
- multiple files
- foreach
- io

Other missing features:
- forward-declaring a class
- automatic dedenting in multiline strings
- `case Foo, Bar:`
- get rid of `-> void`?
- more agressively prevent variables from leaking: if variable defined inside 'if', not visible outside by default?
- `r` strings
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
    - Idea: `x := y` returns false if `x` is null, and when isn't, sets `y` to true
        - Leads to `while x := y`, `if x := y` and `assert x := y`
    - Idea 2: optional interpreted as boolean tells whether it's null, and 
      when it isn't, variables magically change type to get rid of `optional`
        - Leads to `while x`, `if x` and `assert x` (or `assert(x)`)
- non-ref-counted pass-by-value classes
- for pointer types, use C `NULL` to represent `null`?
- avoid using lots of `strlen`
- `starts_with` + `slice` string method
- `list + list`
- `list.starts_with` and `ends_with`
