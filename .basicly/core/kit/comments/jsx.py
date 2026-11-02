from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

_IDENTIFIER = r"(?:[^\W\d]|[$])[\w$]*"
_NAME = _IDENTIFIER + r"(?:[.:-][\w$]+)*"
_OPEN = re.compile(r"<(" + _NAME + r")(?=[\s/<>])")
_CLOSE = re.compile(r"</(" + _NAME + r")?\s*>")
_TRIVIA = re.compile(r"(?:\s|/\*[\s\S]*?\*/|//[^\r\n]*(?:\r?\n|$))*")
_ASYNC = re.compile(r"\basync" + _TRIVIA.pattern + r"$")
_PARAMETER = re.compile(_IDENTIFIER)
_CLOSING = {")": "(", "]": "[", "}": "{", ">": "<"}
_EXPRESSION_PRECEDERS = frozenset("=([{,:;!&|?<>+-*/%^~")
_EXPRESSION_KEYWORD = re.compile(
    r"\b(?:return|yield|throw|await|case|typeof|void|delete|in|instanceof|of|else|do)\s*$"
)


class JSXError(Exception):
    pass


@dataclass
class _Frame:
    kind: str
    name: str = ""
    depth: int = 0
    type_arguments: bool = True


class State:
    def __init__(
        self,
        *,
        typescript: bool,
        atom_end: Callable[[str, int, str], tuple[int, str] | None],
        lex_error: type[Exception],
    ) -> None:
        self.frames = [_Frame("code")]
        self.typescript = typescript
        self.atom_end = atom_end
        self.lex_error = lex_error

    def advance(self, source: str, index: int, previous: str) -> tuple[int, str] | None:
        frame = self.frames[-1]
        if frame.kind == "text":
            return self._text(source, index, previous)
        if frame.kind == "tag":
            return self._tag(source, index, previous)
        if frame.kind == "type":
            return self._type(source, index)
        return self._code(source, index, previous)

    def _code(self, source: str, index: int, previous: str) -> tuple[int, str] | None:
        frame = self.frames[-1]
        char = source[index]
        if frame.depth and char in "{}":
            frame.depth += 1 if char == "{" else -1
            if frame.depth == 0:
                self.frames.pop()
                return index + 1, "v"
        if char == "<":
            starts_expression = self._starts_expression(source, index, previous)
            if self.typescript and (
                (starts_expression and _generic_arrow(source, index))
                or self._try_async_arrow(source, index)
            ):
                self.frames.append(_Frame("type", depth=1))
                return index + 1, "<"
            if starts_expression:
                return self._open(source, index)
        return None

    def _try_async_arrow(self, source: str, index: int) -> bool:
        if _ASYNC.search(source[:index]) is None or not _generic_arrow(source, index):
            return False
        try:
            end = self._balanced_end(source, index, angles=True)
            if end is None:
                return False
            index = _after_trivia(source, end)
            if source[index : index + 1] != "(":
                return False
            end = self._balanced_end(source, index, angles=False)
            if end is None:
                return False
            index = _after_trivia(source, end)
            return source.startswith("=>", index) or (
                source.startswith(":", index) and self._return_arrow(source, index + 1)
            )
        except self.lex_error, JSXError:
            return False

    def _balanced_end(self, source: str, index: int, *, angles: bool) -> int | None:
        stack = [source[index]]
        for position, char in self._head_tokens(source, index + 1, jsx=not angles):
            if char in "([{" or (char == "<" and angles):
                stack.append(char)
            elif char in ")]}":
                if stack[-1] != _CLOSING[char]:
                    return None
                stack.pop()
            elif char == ">" and angles and source[position - 1] != "=":
                if stack[-1] != "<":
                    return None
                stack.pop()
            if not stack:
                return position + 1
        return None

    def _return_arrow(self, source: str, index: int) -> bool:
        stack: list[str] = []
        for position, char in self._head_tokens(source, index, jsx=False):
            if not stack and source.startswith("=>", position):
                return True
            if char in "([{<":
                stack.append(char)
            elif char in ")]}" or (char == ">" and source[position - 1] != "="):
                if not stack or stack[-1] != _CLOSING[char]:
                    return False
                stack.pop()
            elif char == ";" and not stack:
                return False
        return False

    def _head_tokens(self, source: str, index: int, *, jsx: bool) -> Iterator[tuple[int, str]]:
        state = (
            State(typescript=self.typescript, atom_end=self.atom_end, lex_error=self.lex_error)
            if jsx
            else None
        )
        previous = ""
        while index < len(source):
            transition = state.advance(source, index, previous) if state is not None else None
            atom = transition or self.atom_end(source, index, previous)
            if atom is not None:
                index, previous = atom
                continue
            char = source[index]
            yield index, char
            if char == "\n":
                previous = ""
            elif not char.isspace():
                previous = char
            index += 1
        if state is not None:
            state.finish()

    def finish(self) -> None:
        if len(self.frames) > 1:
            frame = self.frames[-1]
            raise JSXError(f"JSX {frame.kind} {frame.name!r} never closes")

    def _text(self, source: str, index: int, previous: str) -> tuple[int, str]:
        if source.startswith("</", index):
            return self._close(source, index)
        if source[index] == "<":
            opened = self._open(source, index)
            if opened is None:
                raise JSXError("JSX text contains an unreadable opening tag")
            return opened
        if source[index] == "{":
            self.frames.append(_Frame("code", depth=1))
            return index + 1, "{"
        return index + 1, previous

    def _tag(self, source: str, index: int, previous: str) -> tuple[int, str] | None:
        char = source[index]
        if char in "\"'" or source.startswith(("//", "/*"), index):
            if char in "\"'":
                self.frames[-1].type_arguments = False
            return None
        if char == "<" and self.frames[-1].type_arguments:
            self.frames[-1].type_arguments = False
            self.frames.append(_Frame("type", depth=1))
            return index + 1, "<"
        if source.startswith("/>", index):
            self.frames.pop()
            return index + 2, "v"
        if char == ">":
            self.frames[-1].kind = "text"
            return index + 1, "v"
        if char == "{":
            self.frames[-1].type_arguments = False
            self.frames.append(_Frame("code", depth=1))
            return index + 1, "{"
        if char in "</}":
            raise JSXError(f"JSX tag contains unexpected {char!r}")
        if not char.isspace():
            self.frames[-1].type_arguments = False
        return index + 1, previous

    def _type(self, source: str, index: int) -> tuple[int, str] | None:
        char = source[index]
        if char in "\"'`" or source.startswith(("//", "/*"), index):
            return None
        frame = self.frames[-1]
        if char == "<":
            frame.depth += 1
        elif char == ">" and source[index - 1] != "=":
            frame.depth -= 1
            if frame.depth == 0:
                self.frames.pop()
        return index + 1, char

    def _open(self, source: str, index: int) -> tuple[int, str] | None:
        if source.startswith("<>", index):
            self.frames.append(_Frame("text"))
            return index + 2, "v"
        match = _OPEN.match(source, index)
        if match is None:
            return None
        self.frames.append(_Frame("tag", name=match.group(1)))
        return match.end(), "v"

    def _close(self, source: str, index: int) -> tuple[int, str]:
        match = _CLOSE.match(source, index)
        name = self.frames[-1].name
        if match is None or (match.group(1) or "") != name:
            raise JSXError(f"JSX closing tag does not match {name!r}")
        self.frames.pop()
        return match.end(), "v"

    @staticmethod
    def _starts_expression(source: str, index: int, previous: str) -> bool:
        prefix = source[:index].rstrip()
        if previous == "<" and source[index - 1 : index] == "<":
            return False
        if previous in {"+", "-"} and prefix.endswith(previous * 2):
            return False
        if previous == "!":
            operand = prefix.rstrip("!").rstrip()
            if operand and (operand[-1].isalnum() or operand[-1] in "_$)]'\"`"):
                return _EXPRESSION_KEYWORD.search(operand) is not None
        return (
            not previous
            or previous in _EXPRESSION_PRECEDERS
            or _EXPRESSION_KEYWORD.search(source[:index]) is not None
        )


def _generic_arrow(source: str, index: int) -> bool:
    position = _after_trivia(source, index + 1)
    parameter = _PARAMETER.match(source, position)
    if parameter is not None and parameter.group() == "const":
        position = _after_trivia(source, parameter.end())
        parameter = _PARAMETER.match(source, position)
    if parameter is None:
        return False
    position = _after_trivia(source, parameter.end())
    if source[position : position + 1] in {",", "="}:
        return True
    keyword = _PARAMETER.match(source, position)
    if keyword is None or keyword.group() != "extends":
        return False
    position = _after_trivia(source, keyword.end())
    return position < len(source) and source[position] not in "=>/"


def _after_trivia(source: str, index: int) -> int:
    matched = _TRIVIA.match(source, index)
    if matched is None:
        raise JSXError("JSX lookahead extends beyond the source")
    return matched.end()
