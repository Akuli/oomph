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

Known bugs:
- ref cycles are not prevented or garbage collected

Missing features needed to write the oomph compiler in oomph:
- multiple files
- io

Other missing features:
- automaticly turn `x` into `new SomeUnion(x)` when needed
- automatic dedenting in multiline strings
- `case Foo, Bar:`
- `r` strings
- `if cond then a else b`
- named arguments
- default values of arguments
- do we want more implicit int to float conversion? `sleep(2)` where `sleep` takes a float
- string methods
    - reverse
    - find occurrence of substring
        - last occurrence
        - all occurrences
        - only occurrence, failing if multiple are found
    - upper and lower (need unicode lib?)
- should `self` be a keyword?
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
        - `Str.replace(mapping)` (I wish python had this)
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
- defining non-ref-counted pass-by-value classes
- `starts_with` + `slice` string method
- `list + list`
- `list.starts_with` and `ends_with`
- exceptions (easiest to implement similar to union?)

Design questions to (re)think:
- should string lengths and indexing be done in unicode code points instead of
  utf-8 bytes?
    - Advantage: easier to understand
    - Advantage: slicing or indexing never fails due to being in the middle of a
      character
    - Disadvantage: slightly slower in programs that input and output utf-8 strings
        - Maybe store strings as utf-8, but somehow hopefully-not-shittily make
          indexing work with unicode code points?
- Should classes be named more consistently? Having `int` and `Str` feels weird
  (and too much like Java), even though there is a reason for doing it.
- More agressively prevent variables from leaking: if variable defined inside
  `if`, not visible outside by default? Or at least can be overwritten with
  another `let`?
- Negative indexes? The downside is that `thing[-n:]` (in Python syntax) doesn't do
  what you would expect when `n=0`.
- Mutable objects as arguments: yes or no? Mutable aliasing can be confusing, but efficient

Optimization ideas:
- avoiding allocations when an object isn't passed around and no reference
  counting is actually needed
- concatenating `n` strings in `O(n)` time instead of the current `O(n^2)`
    - `List[str].join` and various other functions
- caching `strlen` result
- for pointer types, use C `NULL` to represent `null`, instead of a funny union
