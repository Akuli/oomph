# oomph
This is yet another attempt at making a usable programming language.

```shell
git clone https://github.com/Akuli/oomph
cd oomph
python3 -m venv env
. env/bin/activate
pip install more_itertools black isort mypy pyflakes
./test
python3 -m pyoomph tests/hello.oomph   # compile and run hello world file
```

- If you delete or rename files in `lib/`, you may need to run `make clean`.
- Run `./lint` before commit.
- If first argument of test does not start with `-`, it should be a valid oomph compiler command.
  The default is so that `./test` and `./test 'python3 -m pyoomph'` do the same thing.
- Test script passes other arguments to oomph. Try e.g. `./test --valgrind`.


## The language

- Compiles to C, aims to be high-level but faster than Python
- See example files in `tests` to get started
- Some things are implemented in the language itself (see `builtins.oomph` and `stdlib`)

Docs:
- [Syntax](docs/syntax.md)

Known bugs:
- ref cycles are not prevented or garbage collected
- self-hosted compiler (very wip) doesn't add `\n` to end of code

Missing features:
- `==` for unions
- nicer unpacking: `let [lhs, op, rhs] = list.slice(i, i+3)`
- functions as first-class objects
- better error messaging
- `>>>` prompt
- something like python's `__file__` (compile time and runtime)
- attributes of classes that are not arguments
- init methods of classes (or something similar)
- path objects and maybe `p"/home/akuli"` syntax
- `from "lib.oomph" import foo` syntax
- trailing commas
- newlines ignored inside parentheses
- automatic dedenting in multiline strings
- `r` strings
- better ternary than in python: `if cond then a else b`
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
- lists:
    - js-style methods (needs lambdas) or list comprehensions
        - idea: `foo.map(.to_string())` would be same as `foo.map(item => item.to_string())`
    - `list + list`
    - `list.starts_with` and `ends_with`
    - `insert_item` and `insert_sublist` methods
        - do we need both?
    - `delete_slice`
- generics
    - defining generic classes or functions
    - tuples
    - mappings
        - `Str.replace(mapping)` (I wish python had this)
- automatic types
    - automaticly turn `x` into `new SomeUnion(x)` when needed
        - can be difficult: what if unions are nested in a cyclic way?
    - `null[Str]` --> `null[auto]`
    - `null[auto]` --> `null`
    - `new List[Str]()` --> `[]`
    - search for type annotations i have needed to put in the python code, to
      get examples of things where oomph can be better than python+mypy
- some nice way to check if an object is null (for at least `if` and `while`)
    - Idea: `x := y` returns false if `x` is null, and when isn't, sets `y` to true
        - Leads to `while x := y`, `if x := y` and `assert x := y`
    - Idea 2: Optional interpreted as boolean tells whether it's null, and
      when it isn't, variables magically change type to get rid of `Optional`
        - Leads to `while x`, `if x` and `assert x` (or `assert(x)`)
        - Or without optional as boolean interpreting: explicit `while x != null` etc
    - rename `Optional.get()` to `.get_not_null_value()` to make it stand out
      in code reviews as possible bug
- defining non-ref-counted pass-by-value classes
- `starts_with` + `slice` string method
- exceptions (easiest to implement similar to union?)
- compilation errors or warnings for bad/unconventional/complicated style
    - `string.length() == 0` is more complicated than `string == ""`
    - `not (a and not b)` is more complicated than `(not a) or b`
    - `for let i = 0; i < thing.length(); i = i+1: thing.get(i)` --> `foreach`
- warnings about unused things (unions, classes, functions, methods, variables)
- `case Foo(Str x, Int y):`
    - combined with unused variable warnings, it is impossible to accidentally forget
        to use some data, a feature that I wish Python had

Deprecated:
- maybe traditional `for` loops? they seem more confusing than useful
    - if they are removed, `range` would be useful to have
        - if we want an efficient `range`, we need to have streams (python 2 vs 3)
            - and streams won't be easy to implement
                - so maybe it isn't deprecated after all
                    - why is this list so deeply nested lol

Design questions to (re)think:
- rename `switch` to `match`? note that `match` is a beautiful variable name
- `in` operator: `a in b` vs `b.contains(a)`
- tempting to use `func` as variable name
- name of `self`? maybe `instance` or `this`? also considered `inst`, but that's too short
- some kind of `do,while` loops? I don't like how in Python, you need to use `break` if
    you want multiple lines of code before the condition of a loop.
- should string lengths and indexing be done in unicode code points instead of
  utf-8 bytes?
    - Advantage: easier to understand
    - Advantage: slicing or indexing never fails due to being in the middle of a
      character
    - Disadvantage: slightly slower in programs that input and output utf-8 strings
        - Maybe store strings as utf-8, but somehow hopefully-not-shittily make
          indexing work with unicode code points?
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
    - `List[Str].join` and various other functions
- caching `strlen` result
- for pointer types, use C `NULL` to represent `null`, instead of a funny union
- streams, as an alternative to lists
    - doesn't seem to turn `O(n^2)` algorithms into `O(n)` algorithms
