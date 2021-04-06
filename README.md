# oomph
This is yet another attempt at making a usable programming language.

    sudo apt install libssl-dev
    git clone https://github.com/Akuli/oomph
    cd oomph
    python3 -m venv env
    . env/bin/activate
    pip install -r requirements.txt
    ./test
    python3 -m pyoomph tests/hello.oomph   # compile and run hello world file

- If you delete or rename files in `lib/`, you may need to run `make clean`.
- Run `./lint` and `./test` to check stuff e.g. before commit.
- If `./test` fails because test output changes as expected, run `./test --fix`
- If you changed only the self-hosted compiler, you can use `./test --self-hosted`
    to test only that. There's also `--pyoomph`.
- To valgrind-check everything, run `./test --valgrind`


## The language

- Compiles to C, aims to be high-level but faster than Python
- See example files in `tests` to get started
- Some things are implemented in the language itself (see `builtins.oomph` and `stdlib`)

Docs:
- [Unions](docs/implicit-conversions.md)
- [Syntax](docs/syntax.md)
- [Automatic Types](docs/auto.md)
- [Implicit conversions](docs/implicit-conversions.md)

Known bugs:
- ref cycles are not prevented or garbage collected
- The `export` keyword does nothing, and all symbols are visible

Missing features:
- safe and unsafe (user-input) strings: would prevent a lot of security problems
- nicer unpacking: `let [lhs, op, rhs] = list.slice(i, i+3)`
- functions as first-class objects
- better error messaging
- `>>>` prompt
- something like python's `__file__` (compile time and runtime)
- attributes of classes that are not arguments
- init methods of classes (or something similar)
- path objects and maybe `p"/home/akuli"` syntax
- automatic dedenting in multiline strings
- `r` strings
- better ternary than in python: `if cond then a else b`
- named arguments
- default values of arguments
- find all occurences from list
- custom callback to list find methods
- string methods
    - upper and lower (need unicode lib?)
    - grep self-hosted compiler for more string method ideas
- should `self` be a keyword?
- chained equalities `a == b == c`
- `x++`
- `+=`
- lists:
    - `if` in list comprehensions
    - js-style methods (needs lambdas)
        - idea: `foo.map(.to_string())` would be same as `foo.map(item => item.to_string())`
        - list comprehensions still needed?
    - `list + list` or `[first_foo, ...other_foos]` syntax? or both?
- generics
    - defining generic classes or functions
    - tuples
    - mappings
        - `Str.replace(mapping)` (I wish python had this)
- search for type annotations i have needed to put in the python code, to
  get examples of things where oomph can be better than python+mypy
- defining non-ref-counted pass-by-value classes
    - would be useful for views into data that don't require allocations
- exceptions (easiest to implement similar to union?)
- compilation errors or warnings for bad/unconventional/complicated style
    - `string.length() == 0` is more complicated than `string == ""`, same for lists
    - `not (a and not b)` is more complicated than `(not a) or b`
    - `for let i = 0; i < thing.length(); i = i+1: thing.get(i)` --> `foreach`
    - `not a in b` --> `a not in b`
    - using `foo` inside `switch foo:`
    - `if a != b: ... else: ...` is more complicated than `a == b` with `...` swapped
- disallow `not a and b`? i always write it as `(not a) and b`
    - ...except in things like this:
        ```
        return (
            not foo
            and not bar
            and not baz
        )
        ```
- warnings about unused things (unions, classes, functions, methods, variables, arguments)
- `case Foo(Str x, Int y):`
    - combined with unused variable warnings, it is impossible to accidentally forget
        to use some data, a feature that I wish Python had
- good error message for using non-function as function

Deprecated:
- maybe traditional `for` loops? they seem more confusing than useful
    - if they are removed, `range` would be useful to have
        - if we want an efficient `range`, we need to have streams (python 2 vs 3)
            - and streams won't be easy to implement
                - so maybe it isn't deprecated after all
                    - why is this list so deeply nested lol

Design questions to (re)think:
- `from "lib.oomph" import foo` syntax?
    - Advantage: no need to write `lib::` in front of everything, can improve readability
    - Disadvantage: makes things more complicated in several ways
        - An import can span multiple lines, with lots of stuff imported
            - Breaks line-by-line sorting
        - More work to implement
    - If each import is one line, imports can still be sorted line-by-line alphabetically,
        and `from` imports will go first
- rename `switch` to `match`? note that `match` is a beautiful variable name
- tempting to use `func` as variable name
- union types likely shouldn't show up when printed, `print(new (int | null)(null))` just print `null`
- name of `self`? maybe `instance` or `this`? also considered `inst`, but that's too short
- some kind of `do,while` loops? I don't like how in Python, you need to use `break` if
    you want multiple lines of code before the condition of a loop.
- More agressively prevent variables from leaking: if variable defined inside
  `if`, not visible outside by default? Or at least can be overwritten with
  another `let`?
- Negative list indexes? The downside is that `thing[-n:]` (in Python syntax) doesn't do
  what you would expect when `n=0`.
- Mutable objects as arguments: yes or no? Mutable aliasing can be confusing, but efficient

Optimization ideas:
- avoiding allocations when an object isn't passed around and no reference
  counting is actually needed
    - In particular, `thing == []` does not have to allocate
- concatenating `n` strings in `O(n)` time instead of the current `O(n^2)`
    - `List[Str].join` and various other functions
- for pointer types, use C `NULL` to represent `null`, instead of a funny union
- streams, as an alternative to lists
    - doesn't seem to turn `O(n^2)` algorithms into `O(n)` algorithms, unless you e.g.
        use only the first element of the stream
- `(a / b).floor()` with integers `a` and `b` doesn't have to involve floats at runtime
- `foo.split(bar).first()` creates unnecessary list, e.g. with empty `bar` this is
    linear time but could be optimized to constant time


## Self-hosted compiler

Very wip. The `./test` script runs working tests.
There's a list of tests that don't work at `tests/self_hosted_skip.txt`.


## Editor support

There is `oomph_pygments_lexer.py` for syntax highlighting.
To use it in an editor:
1. Make sure that you are using an editor that supports [Pygments](https://pygments.org/),
    such as [Porcupine](https://github.com/Akuli/porcupine) (I made it).
    If you want syntax highlighting in an editor that doesn't use Pygments,
    you can make a pull request that makes Oomph support
    the syntax highlighting library that the editor uses.
2. Configure the editor. At the time of writing this, I use the following config in Porcupine's `filetypes.toml`:
    ```toml
    [Oomph]
    filename_patterns = ["*.oomph"]
    pygments_lexer = 'oomph_pygments_lexer.CustomLexer'
    comment_prefix = '#'
    autoindent_regexes = {dedent = 'return( .+)?|break|pass|continue', indent = '.*:'}
    ```
3. Start the editor so that it can import `oomph_pygments_lexer`.
    Python imports from the current working directory when using the `-m` switch,
    so with Porcupine, you can do:
    ```
    cd path/to/oomph
    python3 -m porcupine
    ```
    Note that you should not have the virtual env activated when doing this,
    unless you have installed Porcupine into it.


## TCC

I like to use tcc when developing oomph.
It compiles much faster than gcc, even though it doesn't optimize as well.

```
./download-tcc
make clean
```

Now `make`, `./test` etc will use the downloaded tinycc.
Currently you need `make clean` because the Makefile isn't clever enough to realize that
the C compiler changed and everything has to be recompiled.
