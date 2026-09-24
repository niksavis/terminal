---
name: tracker-board
description: Serve the tracker as a web page and an HTTP API on localhost. Use when a person wants to read or edit the backlog in a browser, or when you build a page, a chart or a tool on the tracker API.
---

# The tracker board

The board kit serves a page and an HTTP API over the tracker ledger. It needs the tracker
kit beside it.

## Rules

- **Bind to localhost.** Do not pass `--host` with another address unless the person asks
  for it. Anyone who can reach the address can write to the ledger.
- **The API is the tracker.** Each endpoint runs the tracker command of the same name and
  returns its JSON. Read a refusal and fix the cause, as for the command.
- **A saved story is not ready.** The page adds the label `refine`. Do the refinement pass
  from the `work-tracker` skill before anyone builds against it.
- **The page shows who holds each story.** Use "Assign to me" to reserve a story and
  "Claim" to start it. The page refuses a story that someone else holds and names them.

## Serve

```sh
python3 .basicly/kit/board/server.py serve .basicly/ledger              # http://127.0.0.1:8765/
python3 .basicly/kit/board/server.py serve .basicly/ledger --web site   # your own page
```

Stop it with Ctrl+C. Tell the person the address that it prints.

## Build on the API

`GET /api/v1` lists the endpoints. `.basicly/kit/board/README.md` has the table of
methods, paths, body keys and status codes. A write sends `Content-Type: application/json`.
`web/index.html` is a complete client to copy from.
