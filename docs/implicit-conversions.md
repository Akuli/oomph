# Implicit Type Conversions

Arguments of functions, methods, class constructors and unions are implicitly
converted to the correct types. Currently, this is the only implicit conversion
done in Oomph, but other implicit conversions are planned.

Implicitly converting an object to a type follows these rules:
- If the object already has the desired type, then nothing happens; the
    original object is the result of the conversion.
- If the type to convert to is a union type, with the type of the object as a
    member, then the result of the conversion is a new instance of the union
    type. Nested unions are allowed when they are not ambiguous. If the desired
    type itself is a union type, then its members are ignored.
- Otherwise, the conversion is not possible, and a compilation error occurs.

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

As a special case, the argument of the built-in `print` function is converted
to string like this:
- If the argument is already a string, then it's used as is.
- Otherwise, `print(thing)` does `print(thing.to_string())`; that is,
    the `.to_string()` method is called without arguments. It is an error if
    the method doesn't exist or it does not return a string.
