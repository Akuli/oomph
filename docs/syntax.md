# Oomph Syntax

This file describes oomph's syntax. You may find it useful if you want to work on the
compiler or you want to know in detail how something works.


## Source file encoding

Source files must be encoded in UTF-8,
with both CRLF and LF line endings accepted, and treated in exactly the same way.
The files must not start with a BOM.


## Tokenizing

Tokenizing is the first step in compiling an oomph program.
The input is the code as a string, and the output is a sequence of tokens,
each having a type (such as "oneline string") and a value (such as `"hello"`).
Before tokenizing, a newline character is added to the end of the code if not present;
this makes describing the tokenizing rules slightly easier.

Here are the different kinds of tokens.
If more than one of these rules match, then the first matching rule should be used.
- A simple identifier consists of one or more of the following characters:
  uppercase and lowercase ASCII letters A-Z and a-z, the underscore, and digits 0-9.
  The fist character can't be a digit.
- An import identifier consists of two simple identifiers with `::` in between.
  In this documentation, "an identifier" can be a simple identifier or an import identifier.
- If a simple identifier token is a keyword, such as `let` or `func`,
  it is converted to be a keyword token rather than an identifier token.
  This means that keywords can't be used as variable names, for example,
  because that requires an identifier token, not a keyword token.
  See [tokenizer.py](../pyoomph/tokenizer.py) for a full list of keywords.
- Float tokens start with one or more digits 0-9,
  so that the first digit can't be zero unless it's the only digit,
  and then a dot, and finally one or more digits 0-9.
- Integer tokens are just like the part of float tokens on left side of dot:
  one or more digits 0-9, with first digit required to be nonzero unless it's the only digit.
- Multiline strings start and end with `"""`. Between those, you can put zero or more of the following:
    - Any character except `\`, `{` or `}`. The resulting string will contain this character as is.
    - Backslash `\` followed by `{`, `}`, `t` or another `\`.
      The resulting string will contain the character after the initial backslash.
      Note that `\n` is disallowed, as you can write the newline without escaping.
    - First `{`, then any characters except newline or `{` or `}` or backslash, then `}`.
      The text between `{` and `}` is interpreted as the code of an expression and evaluated.
      Its `to_string()` method will be called, unless the expression is already a string.
      The resulting string will be placed into the multiline string
      instead of the braces and the code between them.
- Oneline strings start and end with `"`. The text between the `"` characters is interpreted
  just like for a multiline string, but with these differences:
    - Writing `\n`, a backslash followed by `n`, is allowed.
    - Writing `\"` is allowed.
    - Code between braces must not contain `"` characters.
    - Actual newline characters are not allowed.
- Operators, such as `==` or `(`. You can find a full list similarly to keywords.
- Newline tokens, matching a single newline character.
- An indentation token consists of one or more space characters in the beginning of a line.
  There must not be `#` or a newline character immediately following the indentation;
  that does not produce an indentation token, but is ignored (see below).
- Spaces are ignored anywhere except in the beginning of the file (and in indentation, described above).
- `#` and everything after to it until the next newline character is ignored.
- Anything else is an error.

Once tokenized according to the above rules, the stream of tokens must be modified before parsing:
1. Newline tokens and indentation tokens (that is, newlines and spaces not inside strings)
    inside `(` `)` or `[` `]` are ignored.
2. When the keywords `not` and `in` appear consecutively, as two separate tokens,
    they are replaced with one `not in` token.
3. Newlines are cleaned up.
4. If there is `:` operator followed by a newline and an indentation,
   all those tokens are replaced with one token signifying the beginning of a block.
   It is an error if the new indentation level is not 4 spaces more than the previous indentation level.
5. If a newline token is followed by an indentation token,
   then the indentation level changes according to that; if not, then the indentation level changes to zero.
   The new indentation level must be a multiple of 4 spaces,
   and less than or equal to the previous indentation level.
   For each decrease of 4 spaces in the level, a token indicating the end of a block is produced.
   The indentation token used (if any) is deleted;
   it must not be passed on to the next steps of compilation.
   The newline token is not deleted, however, and is yielded before the block ending tokens.
6. Newlines are cleaned up again.

Here cleaning up the newlines means that newline tokens are removed when
- a newline token is in the beginning of the file,
- a newline token follows another newline token
- a newline token follows a token signifying the beginning of a block, or
- a newline token follows a token signifying the end of a block.

When implementing the tokenizer, steps 4 and 5 can be combined into one function,
and the indentation level can be represented with a local integer variable.


## Parsing

In this documentation, we use the following phrases:
- A "block of X" consists of a token signifying the beginning of a block,
  then zero or more instances of X parsed from the tokens, then a token signifying the end of a block.
  Note that the block includes the `:` used to begin the block, as explained above.
- "Parenthesized" means enclosed between `(` and `)` operators.
- "`[]`-parenthesized" means the same thing with `[` and `]` operators.
- "Comma-separated" means separated by `,` operators, with trailing comma allowed.
- "`|`-separated" means a similar thing, but without leading or trailing `|` allowed.

The tokenized file consists of zero or more toplevel declarations.
A toplevel declaration can be:
- An import: the keyword `import`, then a oneline string with no backslashes or braces,
  then the keyword `as`, then a simple identifier.
  Imports must be before other toplevel declarations.
  The string of an import in `foo/bar/baz.oomph` is interpreted as a path relative to `foo/bar`,
  unless the string starts with `<stdlib>/`;
  in that case, it's interpreted relative to Oomph's standard library directory.
- A typedef: the keyword `typedef` followed by a simple identifier, then the `=` operator,
    then a type and a newline token. It is an error if the type exists already.
- A class definition: the keyword `class` followed by a simple identifier,
  then parenthesized and comma-separated argument definitions,
  and then optionally a block of method definitions.
  A method definition is just like a function definition, but starting with `func` instead of `meth`.
- A function definition, starting with the keyword `func`, then a simple identifier,
  then parenthesized and comma-separated argument definitions, then a block of statements.

There may be an `export` keyword in front of any toplevel declaration.
This makes the defined function or type visible in other files when the file is imported.

An argument definition of a function, method or class is a type followed by a simple identifier.

A type is a non-union type or multiple `|`-separated non-union types. A non-union type can be:
- [Automatic type](auto.md): the keyword `auto`.
- Generic type: an identifier followed by a `[]`-parenthesized type.
- Named type: an identifier.
- Any parenthesized type.

A statement can be:
- If statement: the keyword `if` followed by an expression, then a block of statements,
  then zero or more occurences of `elif` followed by an expression and a block of statements,
  then an optional `else` followed by a block of statements.
- While loop: the keyword `while` followed by an expression and then a block of statements.
- For loop: the keyword `for` followed by a one-line-ish statement, then `;` operator,
  then an expression, then `;` operator, then another one-line-ish statement, then a block of statements.
- Foreach loop: the keyword `foreach` followed by a simple identifier, then `of`, then an expression, then a block of statements.
- Switch statement: the keyword `switch`, followed by an expression with a union type, and then block of cases.
  A case consists of the keyword `case` followed by
  a type, then a simple identifier interpreted as a local variable name,
  and then a block of statements.
  The last `case` keyword may be instead followed by the `*` operator and a block,
  in which case the block runs when no other cases match.
- Any one-line-ish statement followed by a newline.

A one-line-ish statement can be:
- Let statement: the `let` keyword followed by a simple identifier, `=` operator, and an expression.
- Return statement: the `return` keyword optionally followed by an expression.
- Pass statement: the `pass` keyword.
- Continue statement: the `continue` keyword.
- Break statement: the `break` keyword.
- An assignment statement: an expression, then the `=` operator, then another expression.
    The first expression must end with an attribute lookup or be an identifier token,
    interpreted as a local variable.
- A function call expression.

An expression is a sequence of simple expressions or operators and keywords from the below precedence list:
1. `*`, `/`
2. `+`, `-` (can be `-x` or `x - y`, but not `x + -y`; `-` must be first unless it's `x - y`)
3. `mod`
4. `==` and `!=` (it is an error to chain these like `a == b == c` or `a == b != c`)
5. `<`, `>`, `<=`, `>=` (it is an error to chain these)
6. `as` (the right side is a type, not an expression)
7. `in`, `not in` (it is an error to chain these)
8. `not`
9. `and`, `or` (it is an error to chain these)

Items high in the list take precedence, and when chaining is allowed, it happens from left to right.
For example `a+b*c/d*e` means `(a + (((b * c) / d) * e))`.
As a special case, it is an error to write `--x`,
even though according to these rules, it would parse as `-(-x)`.

A simple expression can be:
- One of the following tokens:
    - oneline string
    - multiline string
    - identifier token (interpreted as a variable name)
    - integer token
    - float token
- The keyword `new`, followed by a type.
  This evaluates to a function that constructs an instance of the type,
  or an error if the type does not have a constructor.
- A parenthesized expression.
- A `[]`-parenthesized comma-separated list of expressions, to create a list.

Any simple expression can include zero or more of the following at the end:
- Call: comma-separated parenthesized list of expressions.
- Attribute lookup: `.` operator token followed by a simple identifier token.


## Order of toplevel declarations

Imports must be first, but otherwise,
the order of toplevel declarations in an Oomph program usually doesn't matter.
To make this work, the compiler processes the parsed code in the following steps:
1. Make names of classes, typedefs and imported files available for subsequent
    steps. No more types are defined after this step, although details about the types
    are not made available yet; we don't know what methods are available in each class,
    for example.
2. Process typedef contents. This is done in a separate step because
    it involves referencing other types, possibly defined later in the file.
3. Process arguments and return types of functions, methods and classes. These may use
    typedefs, which is fine, because the actual type corresponding with each typedef
    is now known.
4. Process bodies of functions and methods. This needs information about what other
    functions and methods there are, what arguments do they take, and what they return,
    provided by the previous step.
