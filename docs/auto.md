# Automatic types

The keyword `auto` creates a new automatic type, or auto type for short.
The first "use" of the type will determine what that type actually is.
Also, the type of the empty list `[]` is `List[auto]`.

In this context, the first "use" is actually the first
[implicit conversion](implicit-conversions.md).
To understand why, consider this code:

    foreach thing of []:
        thing.blah()

Here `thing` has the type of a list item, which is `auto`.
Even though it's used to do `thing.blah()`,
there is not enough information to determine the type of the list,
and this code in fact doesn't compile.
In general, writing `thing.blah` does not count as "using" `thing` in this context,
as it that does not implicitly convert `thing` to a different type.


## How are auto types resolved

First, the code is compiled without paying much attention to auto types,
treating them like any other type.
However, implicit conversions treat auto types specially:
- An implicit conversion between an auto type and a non-auto type
    (either from auto to non-auto, or from non-auto to auto)
    determines what the auto type is.
    The value of the auto type is not immediately substituted everywhere;
    instead, it is remembered for later.
- An implicit conversion between two different auto types is an error,
    unless the value of one (or both) auto types has been determined already;
    in that case, the determined value is used.
    This simplifies the implementation and doesn't seem to have much practical impact.
- A similar thing happens when implicitly converting from `List[T]` to `List[U]`,
    where `T` and `U` are different types,
    or similarly for any other generic instead of `List`.
    (TODO: implement the rest of this)
    Currently this does not recurse,
    so `List[List[auto]]` does not convert `List[List[Str]]` for example,
    but this will hopefully be changed in a future version of Oomph.

Also, when `thing` has automatic type, `thing.blah(foo)`
is not used to implicitly convert `foo` to the correct argument type,
because the type of `thing` might not be known yet.

Once all that is done, the compiled code contains `auto` types,
and we also have a mapping of values of the `auto` types.
The next step is to plug in the types of
the `thing`s of `thing.blah` attribute and method lookups,
and then do the implicit conversions for method arguments.

Finally, all automatic types are replaced with the corresponding actual types.
It is an error if the actual type is not available;
in that case, the automatic type has never been used.
