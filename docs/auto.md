```
func foo(List[Float] list):
    pass

let asdf = new List[auto]()   # Let A denote the type created here
asdf.push(1)                  # Conversion(from=Int, to=A)
foo(asdf)                     # A = Float
```

## Defining the conversions

- Int can convert to float
- Union member type can convert to union itself, nested not allowed

NOT transitive. Allowing nested when unambiguous does not help:

```
class A()

union B:
    A
    Str

union B2:
    A
    Int

union C:
    B
    B2
```

Now A converts to B and B converts to C, but A does not convert to C (ambiguous).
- Conclusion: not gonna allow nested, that's not necessary

## The "convert-equals rule"

(couldn't think of better name)

Assume:

```
A1 converts to A2
A2 converts to A3
...
A(n-1) converts to An
An converts to A1
```

Then A1 = A2 = ... = An.

In other words, union membership graph has no cycles.

TODO: disallow this:

```
union A:
    Str
    B

union B:
    Int
    A
```

## Auto-type resolving algorithm

Assume only `Conversion`s left. They form a directed graph.

- Break cycles with convert-equals rule: `A >= B >= C ==> A=B=C`. Now we have DAG.
- Eliminate type variables from DAG like this:
    - Find any type variable
    - While possible, choose a narrower type variable instead. Let result be T
    - If a subtype of T includes all subtypes of T:
        - Choose T to be the(*) subtype that includes others
    - Else:
        - Error for now, the rest needs more thought. In particular, do results
            depend on which type variable chosen in "find any type variable"?
        - Walk towards wider types, finding all unions that include the subtypes,
            including indirect unions
        - If exactly one union found:
            - Choose T to be that type
        - Else:
            - Error

(*) From convert-equals rule,
it follows that there can't be multiple matching subtypes,
as they would convert to each other.

-------------

Problems: `autotyped == blah`, `autotyped.attrib`, `autotyped.method()`
- Should left side convert to right side? Or right to left?
- Solution: Leave as is, convert separately afterwards
