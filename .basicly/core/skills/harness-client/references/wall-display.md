# Wall display

```sh
basicly board serve                      # http://127.0.0.1:8787
basicly board serve --port 0             # take a free port and print it
basicly board serve --no-actions         # for an unattended wall
```

The server takes no lock and writes no file.
By default it has one POST route that runs an operator's command from a closed table.
The table can answer a decision, approve a checkpoint, start, park or resume a record, and kill a lane.
Approve and kill need a typed confirm code.
Use `--no-actions` for a screen that anyone in the room can touch. A POST then returns 405.
Leave `--bind` unset, so the server stays on the loopback address.

With a fresh supervisor heartbeat, the board serves the snapshot that the supervisor wrote.
With no live supervisor, it builds its own snapshot every `--refresh` seconds.
Every panel shows the age of its snapshot, so a frozen screen shows as frozen.
`GET /snapshot.json` returns the same `harness-board/v1` document for other consumers.
