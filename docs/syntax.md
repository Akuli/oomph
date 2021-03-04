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
- An identifier consists of one or more of the following characters:
  uppercase and lowercase ASCII letters A-Z and a-z, the underscore, and digits 0-9.
  The fist character can't be a digit.
- If an identifier token is a keyword, such as `let` or `func`,
  it is converted to be a keyword token rather than an identifier token.
  This means that keywords can't be used as variable names, for example,
  because that requires an identifier token, not a keyword token.
  See [tokenizer.py](../oomph/tokenizer.py) for a full list of keywords.
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
    - Actual newline characters are not allowed.
    - Code between braces must not contain `"` characters.
- Operators, such as `==` or `(`. You can find a full list similarly to keywords.
- Newline tokens, matching a single  newline character.
- An indentation token consists of one or more ` ` characters, following a newline character.
  Note that indentation cannot be in the beginning of the file,
  as there is no newline character before the beginning.
  There must not be `#` or a newline character immediately following the indentation;
  that does not produce an indentation token, but is ignored (see below).
- Spaces are ignored anywhere except in the beginning of the file (and in indentation, described above).
- `#` and everything after to it until the next newline character is ignored.
- Anything else is an error.

Once tokenized according to the above rules, the stream of tokens must be modified before parsing:
1. Newlines are cleaned up.
2. If there is `:` operator followed by a newline and an indentation,
   all those tokens are replaced with one token signifying the beginning of a block.
   It is an error if the new indentation level is not 4 spaces more than the previous indentation level.
3. If there is a newline token, then the indentation level changes according to that;
   if there is not, then the indentation level changes to zero.
   The new indentation level must be a multiple of 4 spaces,
   and less than or equal to the previous indentation level.
   For each decrease of 4 spaces in the level, a token indicating the end of a block is produced.
   The indentation token used (if any) is deleted;
   it must not be passed on to the next steps of compilation.
   The newline token is not deleted, however, and is yielded before the block ending tokens.
4. Newlines are cleaned up again.

Here cleaning up the newlines means that newline tokens are removed when
- a newline token is in the beginning of the file,
- a newline token follows another newline token
- a newline token follows a token signifying the beginning of a block, or
- a newline token follows a token signifying the end of a block.

When implementing the tokenizer, steps 2 and 3 can be combined into one function,
and the indentation level can be represented with a local integer variable.


## Parsing

In this documentation, we use the following phrases:
- A "block of X" consists of a token signifying the beginning of a block,
  then zero or more instances of X parsed from the tokens, then a token signifying the end of a block.
  Note that the block includes the `:` used to begin the block, as explained above.
- "Parenthesized" means enclosed between `(` and `)` operators.
- "`[]`-parenthesized" means the same thing with `[` and `]` operators.
- "Comma-separated" means separated by `,` operators, with trailing comma not allowed.

The tokenized file consists of zero or more toplevel declarations.
A toplevel declaration can be:
- A union definition: the keyword `union` followed by an identifier, and then a block of union members.
  Each union member is a type followed by a newline token.
- A class definition: the keyword `class` followed by an identifier,
  then parenthesized and comma-separated argument definitions,
  and then optionally a block of method definitions.
  A method definition is just like a function definition, but starting with `func` instead of `meth`.
- A function definition, starting with the keyword `func`, then an identifier,
  then parenthesized and comma-separated argument definitions, then a block of statements.

A type is an identifier, possibly followed by another `[]`-parenthesized type to indicate a generic.
An argument definition of a function, method or class is a type followed by an identifier.

A statement can be:
- If statement: the keyword `if` followed by an expression, then a block of statements,
  then zero or more occurences of `elif` followed by an expression and a block of statements,
  then an optional `else` followed by a block of statements.
- While loop: the keyword `while` followed by an expression and then a block of statements.
- For loop: the keyword `for` followed by a one-line-ish statement, then `;` operator,
  then an expression, then `;` operator, then another one-line-ish statement, then a block of statements.
- Foreach loop: the keyword `foreach` followed by an identifier, then `of`, then an expression, then a block of statements.
- Switch statement: the keyword `switch`, followed by an expression with a union type, and then block of cases.
  A case consists of the keyword `case` followed by a type and then a block of statements.
- Any one-line-ish statement followed by a newline.

A one-line-ish statement can be:
- Let statement: the `let` keyword followed by an identifier, `=` operator, and an expression.
- Return statement: the `return` keyword optionally followed by an expression.
- Pass statement: the `pass` keyword.
- Continue statement: the `continue` keyword.
- Break statement: the `break` keyword.
- An assignment statement: just like a let statement, but without the keyword `let`.
- A function call expression.

An expression is a sequence of simple expressions or operators and keywords from the below precedence list:
1. `*`, `/`
2. `+`, `-` (can be `-x` or `x - y`)
3. `mod`
4. `==` and `!=` (it is an error to chain these like `a == b == c` or `a == b != c`)
5. `<`, `>`, `<=`, `>=` (it is an error to chain these)
6. `not`
7. `and`, `or` (it is an error to chain these)
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
- The keyword `null`, followed by a `[]`-parenthesized type.
- A parenthesized expression.
Any simple expression can include zero or more of the following at the end:
- Call: comma-separated parenthesized list of expressions.
- Attribute lookup: `.` operator token followed by an identifier token.
