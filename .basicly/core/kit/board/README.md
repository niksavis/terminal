# Board kit

The board kit serves a web page and an HTTP API over a tracker ledger, on localhost. It is
an optional add-on to the tracker kit and needs the tracker kit beside it. It uses the
standard library only. It is the one kit that listens on the network: the
`kit-boundary` gate lets it import `http.server`, `http` and `urllib.parse`, and nothing
else that reaches outside.

| File | What it does |
| --- | --- |
| `server.py` | the HTTP API, the static page server, and `serve` |
| `web/index.html` | the default page: counts, the refinement queue, ready, blocked, and a story editor |

## Install

Install the tracker kit first, then this kit:

```sh
uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-tracker basicly-tracker init
uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-board basicly-board init
```

## Serve

```console
$ python3 .basicly/kit/board/server.py serve .basicly/ledger
board: http://127.0.0.1:8765/ serves .basicly/ledger; API at /api/v1
```

Stop it with Ctrl+C. `--port` sets the port. `--web DIR` serves your own page in place of
the default page. In a repository that installs basicly, `basicly tracker serve` runs the
same server and removes machine paths from what it writes.

## The page

The page lists the stories on the left and shows one story on the right. The tabs are
Ready, In progress, Refine, Blocked, Mine, All open and Closed. Search matches titles and ids, and `/`
moves to the search box. Each row shows the priority, the type, the age, the holder and one
warning. The story pane renders the text, offers one main action for the state of the
story (Claim when nobody holds it, Close when you hold it), and keeps the rest in its More
menu. Edit (or the key `e`) opens one form for the whole story. `#/record/<id>` opens a
story, so a link to a story works.

## Refinement

A person writes or edits a story on the page. The page adds the label `refine`. An agent
then does a refinement pass: it reads `refine`, rewrites each record with the full fields
and removes the label. The tracker kit's `work-tracker` skill gives the steps. A record
that carries the label, or that was created under the current rule and fails `dor`, leaves
the Ready tab. An older record that fails `dor` stays there and shows what it owes.

## HTTP API

The API answers under `/api/v1`, and `GET /api/v1` lists every endpoint. Each endpoint runs
the tracker kit command of the same name through `cli.invoke`. It returns the same JSON,
with the same `schema` field and the same refusals, so a client written against the CLI
output works against the API. `GET /api/v1` also names the `holder`, the name that
`assign` and `claim` use by default, so a page can tell your stories from other people's:

| Method and path | Kit command | Body keys |
| --- | --- | --- |
| `GET /api/v1/ready?limit=N` | `ready` | |
| `GET /api/v1/blocked`, `/stats`, `/fields`, `/refine` | same name | |
| `GET /api/v1/scaffold?type=T` | `scaffold` | |
| `GET /api/v1/records?status=S&limit=N` | `list` | |
| `GET /api/v1/records/<id>` | `show` | |
| `GET /api/v1/records/<id>/dor` | `dor` | |
| `POST /api/v1/records` | `create`, or `child` with `parent` | `title`, `description`, `acceptance`, `requirements`, `fields`, `parent`, `prefix` |
| `PATCH /api/v1/records/<id>` | `update` | the create keys except `parent` and `prefix`, and `status`, `add_labels`, `remove_labels` |
| `POST /api/v1/records/<id>/comments` | `comment` | `text` |
| `POST /api/v1/records/<id>/close` | `close` | `reason` |
| `POST /api/v1/records/<id>/deps` | `dep` | `target`, `type` |
| `POST /api/v1/records/<id>/assign` | `assign` | `to`, `take` |
| `POST /api/v1/records/<id>/claim` | `claim` | `to`, `take` |
| `POST /api/v1/records/<id>/unassign` | `unassign` | |

Status codes: 200 or 201 when the command succeeds, 422 when the kit refuses it, 404 for a
missing record, 400 for a malformed request, 403 for a foreign host. A write must send
`Content-Type: application/json`. The server refuses a request whose `Host` or `Origin` is
not this server, so a web page on another site cannot write to your ledger. `--host`
binds another address. Anyone who can reach that address can then write.

## Build your own

- **Your own page:** write static files and run `serve --web DIR`. Call the API with
  `fetch`. `web/index.html` is a complete example of about 630 lines.
- **Your own server or tool:** call the tracker kit directly. `cli.invoke(args)` returns the
  exit code and the report for any command. Build `args` with `cli.arguments.parser()`.
- **Your own chart or report:** read the JSON of `ready`, `blocked`, `stats`, `list` and
  `show`. The `dates` of each record come from the event times.
