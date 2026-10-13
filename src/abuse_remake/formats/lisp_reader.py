"""A reader (not an evaluator) for the original Abuse Lisp files.

Only the *data* in ``def_char`` forms is extracted from the Lisp: animation states, abilities,
flags, ranges and variable names. Behaviour functions are hand-ported to Python and cited one
by one. The syntax follows abuse/src/lisp.c ``compile``: ``;`` line comments, ``/* */`` block
comments, ``'`` quote, a backquote and ``,`` unquote, double-quoted strings, integers and symbols.
"""

from __future__ import annotations

from dataclasses import dataclass


class Symbol(str):
    """A Lisp symbol; plain ``str`` values are Lisp strings."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Symbol({str.__repr__(self)})"


@dataclass(frozen=True)
class Located:
    form: object
    path: str
    line: int


class LispSyntaxError(ValueError):
    pass


def _tokens(text: str, path: str):
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == ";":
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise LispSyntaxError(f"{path}:{line}: unterminated /* comment")
            line += text.count("\n", i, end)
            i = end + 2
        elif c in "()'`,":
            yield c, line
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if text[j] == "\n":
                    line += 1
                buf.append(text[j])
                j += 1
            yield ("STR", "".join(buf)), line
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()'`,;\"":
                j += 1
            yield ("ATOM", text[i:j]), line
            i = j


def _atom(tok: str):
    try:
        return int(tok)
    except ValueError:
        pass
    if tok in ("T", "t"):
        return True
    if tok in ("nil", "NIL"):
        return None
    return Symbol(tok)


def read_forms(text: str, path: str = "<lisp>") -> list[Located]:
    """Parse every top-level form, remembering the line it starts on."""
    toks = list(_tokens(text, path))
    pos = 0

    def parse():
        nonlocal pos
        tok, line = toks[pos]
        pos += 1
        if tok == "(":
            items = []
            while True:
                if pos >= len(toks):
                    raise LispSyntaxError(f"{path}:{line}: unclosed (")
                if toks[pos][0] == ")":
                    pos += 1
                    return items
                items.append(parse())
        if tok == ")":
            raise LispSyntaxError(f"{path}:{line}: unexpected )")
        if tok == "'":
            return [Symbol("quote"), parse()]
        if tok == "`":
            return [Symbol("backquote"), parse()]
        if tok == ",":
            return [Symbol("unquote"), parse()]
        kind, value = tok
        return value if kind == "STR" else _atom(value)

    out = []
    while pos < len(toks):
        line = toks[pos][1]
        out.append(Located(parse(), path, line))
    return out


def head(form) -> str | None:
    if isinstance(form, list) and form and isinstance(form[0], Symbol):
        return str(form[0])
    return None
