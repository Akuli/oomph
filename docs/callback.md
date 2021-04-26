# Callback functions

Oomph functions can be given as arguments to other functions.
Here's a small program that does it:

    func run_twice(func() callback):
        callback()
        callback()

    func print_hello():
        print("Hello")

    export func main():
        run_twice(print_hello)   # prints "Hello" twice

On the first line, `func() callback` means that `run_twice` takes an argument named `callback`,
and its type is a function, denoted by `func()`.
So, this is the usual `func do_something(Str argument)`,
but with `func()` as the type of the argument instead of `Str`.
Specifically, `func()` means a function that takes no arguments and doesn't return anything.

To specify that the function should take arguments or return a value,
use the same syntax as you would otherwise use with `func`,
but omit the function and argument names.
For example, `func(Int) -> Str` is a function that takes an integer as an argument and returns a string:

    func do_stuff(func(Int) -> Str callback, Int arg):
        print("Callback returned: " + callback(arg))

    func create_lol(Int number) -> Str:
        return "lol {number}"

    export func main():
        do_stuff(create_lol, 123)   # prints "Callback returned: lol 123"

Multiple arguments should be separated with commas, as in `func(Int, Bool) -> Str`.


## Union syntax gotcha

Oomph aims to have as few gotchas as possible. This is one of them.

If you want to say "a string or a function that returns `Int`" (see [union types](union.md)),
this does **not** work:

    func() -> Int | Str

Instead, this means a function with union return type `Int | Str`.
Add parentheses to make this work:

    (func() -> Int) | Str
