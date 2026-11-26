from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping, MutableMapping

SESSION = "BASICLY_TRACKER_SESSION"
FALLBACKS = ("ORCH_SESSION_ID", "CLAUDE_CODE_SESSION_ID")


def session_of(environ: Mapping[str, str], given: str | None = None) -> str:
    names = (SESSION, *FALLBACKS)
    return given or next((environ[name] for name in names if environ.get(name)), "")


@contextlib.contextmanager
def given_session(environ: MutableMapping[str, str], given: str | None) -> Iterator[None]:
    if not given:
        yield
        return
    before = environ.get(SESSION)
    environ[SESSION] = given
    try:
        yield
    finally:
        if before is None:
            environ.pop(SESSION, None)
        else:
            environ[SESSION] = before
