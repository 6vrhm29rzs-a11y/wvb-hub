# Ask Digby — the chat panel

Phase 2 of Digby. Phase 1 (the per-team summaries) is `docs/digby.md`.

## Running it

```
export ANTHROPIC_API_KEY=sk-ant-<your key>     # your shell, never a file here
python3 scripts/live_server.py                 # then open the URL it prints
```

The key lives in the server process only. It is never written to a file, never
logged, never sent to the page. Open `Cody/START-HERE.html` straight off disk
and everything still works except the chat — the button reports that the server
is not running.

Ask from the command line instead:

```
python3 scripts/digby_chat.py "how does Nebraska's rotation look for 2026?"
```

## What it sends

Not the page. The built page is ~2.8 MB (~700k tokens); a question is matched
against team names, conference names and player names, and only the matched
records go out — typically 2–8 KB. The ranked field ships with every question as
one line per team, so "who is number one" works without naming anybody.

## The gate

`digby.verify()`, unchanged from the summaries. Every number in the answer must
appear in the context at the precision it was written, and every cited field
must exist. **An answer that fails is not shown** — the panel says it had one and
is withholding it, rather than showing it with a caveat.

"That isn't in the hub's data" is a first-class answer, and most volleyball
questions get it: injuries, recruiting, how a team looked, anything about a
match nobody has played.

## Two retrieval rules, both paid for

**A conference is not five of its teams.** The first version sent full records
for the top few members and let Digby answer "who is best in the Big Ten" off a
third of the league. Every number it quoted would have been real, cited, and
wrong — invisible to the gate, which checks numbers and cannot check whether the
right teams were in the room. A named conference now contributes a one-line row
for **every** member, with full records for the few at the top.

**A bare surname needs two things: uniqueness and a capital letter.** Measured:
*"who is the best team in the WCC"* retrieved **Green Bay**, because Best is a
unique surname on its roster. Roughly a quarter of the surnames here are also
ordinary words — Best, Ball, Battle, Beach, Archer. Capitalisation is the signal
a writer already gives for a proper noun; it needs no word list (the system
dictionary is useless here — it contains Murray, Anderson and Alexander, so it
would block real names) and it fails toward *not found* rather than toward the
wrong player. Four players are called Murray, so an ambiguous surname resolves
to nobody and says so. Full names match in any case.

Both guarded in `scripts/test_digby_chat.py`, against a synthetic league — a
guard that depends on who is currently on a roster stops being a guard the
moment somebody transfers. The surname test has a positive control: a
capitalised unique surname must still resolve, or the "fix" would just be
"never match surnames".

## Safety

- **The server binds 127.0.0.1 and must stay that way.** On a routable address,
  anything on the network can spend the key. A `Host` header check is the second
  lock, against DNS-rebinding from the browser.
- **The answer is inserted with `textContent`, never `innerHTML`.** It is the
  only text on the page a model wrote. Verified in a real browser: markup fed
  through that path stays text.
- **Body capped at 4 KB, question at 500 characters**, two seconds between
  questions, 200 per server run — so a stuck page cannot spend in a loop.
- **The public build has none of it.** CSS, panel and script are emitted only in
  the private build, and `PRIVATE_MARKERS` aborts the public build if any of the
  three appear. Verified by reintroducing the leak: the build aborts.
