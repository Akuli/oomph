import re
from typing import Iterator, Tuple

import more_itertools

_TOKEN_REGEX = (
    r'(?P<keyword>\b(let|func|void|class|new)\b)|'
    r'(?P<var>[A-Za-z_][A-Za-z0-9_]*)|'
    r'(?P<int>[1-9][0-9]*|0)|'
    r'(?P<op>[=+(),\n:\.]|->)|'
    r'(?P<indent>(?<=\n) +(?!\n))|'
    r'(?P<ignore> |#.*)|'
    r'(?P<error>.)'
)


def _raw_tokenize(code: str) -> Iterator[Tuple[str, str]]:
    if not code.endswith('\n'):
        code += '\n'

    for match in re.finditer(_TOKEN_REGEX, code):
        tokentype = match.lastgroup
        assert tokentype is not None
        value = match.group()
        assert tokentype != 'error', repr(value)
        if tokentype != 'ignore':
            yield (tokentype, match.group())


def _find_blocks(tokens: Iterator[Tuple[str, str]]) -> Iterator[Tuple[str, str]]:
    indent_level = 0
    while True:
        head, tokens = more_itertools.spy(tokens, 3)
        if not head:
            break

        if len(head) >= 3 and head[:2] == [('op', ':'), ('op', '\n')] and head[2][0] == 'indent':
            indent_level += 1
            assert head[2][1] == ' '*4*indent_level
            yield ('begin_block', ':')
            next(tokens)
            next(tokens)
            next(tokens)
            continue

        yield next(tokens)

        if head[0] == ('op', '\n'):
            if len(head) >= 2 and head[1][0] == 'indent':
                new_level = len(head[1][1]) // 4
                assert head[1][1] == ' '*4*new_level
                next(tokens)   # skip indent
            else:
                new_level = 0
            assert new_level <= indent_level
            while indent_level != new_level:
                yield ('end_block', '')
                indent_level -= 1


def _clean_newlines(tokens: Iterator[Tuple[str, str]]) -> Iterator[Tuple[str, str]]:
    token_iter = more_itertools.peekable(tokens)

    # Ignore newlines in beginning
    while token_iter.peek(None) == ('op', '\n'):
        next(token_iter)

    while True:
        try:
            token = next(token_iter)
        except StopIteration:
            break

        # Ignore newlines after beginning of block, end of block, or another newline
        while (token in {('op', '\n'), ('begin_block', ':'), ('end_block', '')} and
               token_iter.peek(None) == ('op', '\n')):
            next(token_iter)

        yield token


def tokenize(code: str) -> Iterator[Tuple[str, str]]:
    return _clean_newlines(_find_blocks(_raw_tokenize(code)))
