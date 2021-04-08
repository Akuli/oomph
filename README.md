# oomph
This is yet another attempt at making a usable programming language.
Oomph is a high-level language, but it compiles to C and aims to be faster than Python.

    sudo apt install libssl-dev
    git clone https://github.com/Akuli/oomph
    cd oomph
    python3 -m venv env
    . env/bin/activate
    pip install -r requirements.txt
    make oomph
    ./oomph tests/hello.oomph   # compile and run hello world file

- If you delete or rename files in `lib/`, you may need to run `make clean`.
- Run `./lint` and `./test` to check stuff e.g. before commit.
- If `./test` fails because test output changes as expected, run `./test --fix`
- If you changed only the self-hosted compiler, you can use `./test --self-hosted`
    to test only that. There's also `--pyoomph`.
- To valgrind-check everything, run `./test --valgrind` (very slow)


## Why Oomph?

Oomph aims to be a small and simple language, with little boilerplate and few "gotchas".
I will compare Oomph to Python, because it's a programming language with somewhat similar goals.

Oomph code is short. For example, `class Foo(Int number, Str message)`
is valid line of Oomph code that corresponds to 4 lines of Python code:

```python
class Foo:
    def __init__(self, number, message):
        self.number = number
        self.message = message
```

With [dataclasses](https://docs.python.org/3/library/dataclasses.html),
the Python code is still 4 lines:

```python
@dataclass
class Foo:
    number: int
    message: str
```

I have helped lots of Python beginners, and seen lots of Python gotchas they struggle with.
Linters and type checkers can help with some of them, but not all.
These Python gotchas **don't exist in Oomph**:
- `a or b and c` is valid Python syntax. It confuses Python beginners who expect it to be
    `(a or b) and c` when it is actually `a or (b and c)`.
- `thing == "foo" or "bar"` is same as `thing == "foo"` in Python, because you can put `or`
    between strings: `"foo" or "bar"` evaluates to `"foo"`.
- `a == b == c` means `a == b and b == c` in Python, so Python programmers tend to assume
    it also works in other programming languages. Many other languages interpret it as
    `(a == b) == c`; that is, `some_boolean == c`.
- While Oomph's import system is super simple, Python's import system is complicated and
    full of surprising gotchas:
    - If you make a file called `queue.py`, then any code that does `import queue`
        will import your file instead of the standard-library `queue` module.
    - If `foo/a.py` wants to import `foo/b.py`, it should `import b` or `from foo import b`
        depending on whether you intend to run `python3 a.py` inside `foo/` or
        `python3 -m foo.a` outside `foo/`. In Oomph, you `import "b.oomph" as b`
        and it always works.
    - If you run your code with `python3 -m foo` or `python3 -m foo.thing`,
        you should to create an empty `foo/__init__.py`. Otherwise, you create an
        [implicit namespace package](https://www.python.org/dev/peps/pep-0420/). There's
        no warning, but it's bad practice, and Python will just do something weird when
        it imports your code.
    - If any file does `import foo.bar`, then **all** files that import `foo` will also
        get `foo.bar`. Then those other files might rely on `foo.bar` without actually
        importing it, and they break in surprising ways when someone removes
        `import foo.bar` from a seemingly unrelated file.
- Many beginners think that `10^2 == 100`. In Python, `10^2 = 8` and `10**2 = 100`.
- I have seen a beginner writing `x**2 + y*+2`, where `*+` should be `**`.
    It's valid Python code, and Python interprets `+2` as `2`.
- In Python, `--x` and `++x` don't work like you expect, but they are not syntax errors either. Both of those evaluate to `x`,
    without incrementing or decrementing anything.
- Python's error messages are terrible. For example:
    - `TypeError: NoneType object is not iterable` means that you are trying to `for` loop
        over something that is `None` when it shouldn't be. The error message mentions
        `None` and looping, but not in a way that someone new to Python would understand.
    - `SyntaxError: invalid syntax` pointing at a valid line of code usually means that
        the previous line is missing a `)`. This error message points at the wrong line
        and says nothing about parentheses.
- There's a `list` builtin in Python, but you can still make a variable named `list`.
    It works fine at first, but causes confusing errors when you try to convert something
    to a list with `list(thing)`.
- Python's `for item in thing: ...` creates an `item` variable set to
    the last element of `thing`. You won't get an error if you use it after the loop.
- If you `import string`, then you can't make a variable named `string`. Actually you can,
    and it will work, until you try to actually use something from the imported module.
    (Oomph clearly separates imported modules and variables, so a variable named
    `path` works fine even if you `import "<stdlib>/path.oomph" as path`)

Python gotchas that also exist in Oomph (but fixing is planned):
- Modifying a list while looping over it doesn't behave like you would expect.
    Try `for item in the_list: the_list.remove(item)` in Python, for example.


## Learning Oomph

Example code:
- There are short example programs in `tests`.
- Some things are implemented in Oomph. See `builtins.oomph` and `stdlib`.
- The `self_hosted/` directory is an Oomph compiler written in Oomph.

Docs:
- [Unions](docs/implicit-conversions.md)
- [Syntax](docs/syntax.md)
- [Automatic Types](docs/auto.md)
- [Implicit conversions](docs/implicit-conversions.md)


## Two compilers

Currently there's two compilers:
- `pyoomph` is an Oomph compiler written in Python.
- The self-hosted Oomph compiler is written in Oomph.

The self-hosted compiler can compile itself:

    ./oomph -o oomph self_hosted/main.oomph

Currently `make oomph` uses pyoomph to compile the self-hosted compiler.


## Editor support

### Visual Studio Code

Copy the `oomph-vscode` directory into `~/.vscode/extensions` (might be `.vscode-server` if using WSL)

### Porcupine

[Porcupine](https://github.com/Akuli/porcupine) is an editor I made.
With small modifications, these instructions should also work with any other editor that
uses [Pygments](https://pygments.org/) for syntax highlighting
(although I haven't seen many such editors).

1. Go to "Settings" in Porcupine's menubar then "Config Files", then `filetypes.toml`.
2. Add this to the file:
    ```toml
    [Oomph]
    filename_patterns = ["*.oomph"]
    pygments_lexer = 'oomph_pygments_lexer.CustomLexer'
    comment_prefix = '#'
    autoindent_regexes = {dedent = 'return( .+)?|break|pass|continue', indent = '.*:'}
    ```
3. Restart Porcupine so that it can import `oomph_pygments_lexer`. It comes with Oomph.
    Python imports from the current working directory when using the `-m` switch,
    so you can do this:
    ```
    cd path/to/oomph
    python3 -m porcupine
    ```
    Note that you should not have the Oomph virtual env activated when doing this,
    unless you installed Porcupine into it.


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


## Stuff I wrote before I used Github issues with this project

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
