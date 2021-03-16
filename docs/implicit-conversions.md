# Implicit Type Conversions

Implicit conversion rules are applied in these situations (and more is planned):
- Arguments of all calls, including functions, methods, `new`, and so on.
- Variable assignments (but not `let` statements;
    they use the type of the value as the type of the variable, with no conversions).
- The value of a `return` statement.
- The operators `==`, `!=`, `<`, `>`, `<=`, `>=`, `+`, `-`, `*` and `/`
    attempt converting their left side to have the type of the right side,
    and the right side to have the type of the left side.
    - If the left and right side have the same type without having to do any
        conversions, then no conversions are done.
    - Otherwise, if both conversions succeed, a compilation error occurs. This is done
        to prevent ambiguity in choosing the "right" conversion to do.
    - If one conversion succeeds and the other fails, the successful conversion is used.
    - If neither conversion succeeds, a compilation error occurs.
- The operators `and`, `or`, `not` implicitly convert all values to type `Bool`.

Implicitly converting an object to a type follows these rules:
- If the object already has the desired type, then nothing happens; the
    original object is the result of the conversion.
- If the type to convert to is `Float` and the object has type `Int`,
    the integer will be converted to a float at runtime.
- If the type to convert to is a union type, with the type of the object as a
    member, then the result of the conversion is a new instance of the union
    type. Nested unions are allowed when they are not ambiguous. If the desired
    type itself is a union type, then its members are ignored.
- Otherwise, the implicit conversion fails.

There are also a few additional rules that apply only when automatic types are involved.
See [the documentation on automatic types](auto.md).

These rules are intentionally weak. For example, unlike in many other programming
languages, `1 == "2"` is an error: even though the `==` operator does implicit
conversions, nothing can implicitly convert between `Int` and `Str`.

To understand what "when they are not ambiguous" means, consider the following example:

```python
class Foo()
class Bar()

union Inner:
    Foo
    Bar

union Outer:
    Foo
    Inner
```

Now an instance of `Foo` cannot be implicitly converted to type `Outer`,
as it could mean `Outer(foo)` or `Outer(Inner(foo))`.
However, an instance of `Bar` can be implicitly converted to type `Outer`,
and that means `Outer(Inner(bar))`.

There are some special cases:
- If the argument of the built-in `print` function is not a string, its `.to_string()`
    method is called with no arguments to get the string to be printed.
- `Int / Int` division converts both integers to floats before dividing them.
    The result is a float.
