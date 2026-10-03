# usecases/

Empty on purpose. A usecase lives here only when logic spans **more than one
domain** and is too involved for one domain to call another's repository interface.

## When to add one

Business logic starts in the route handler. Pull it out when one of these becomes
true:

1. **A second caller appears** — another route, another transport (gRPC,
   WebSocket), a script, a job.
2. **It has a branch worth testing without HTTP.**
3. **The handler passes ~30 lines or needs more than two collaborators.**

If the logic belongs to one domain, it goes in that domain (`src/<domain>/`), not
here. `usecases/` is for orchestration **across** domains.

## The one rule

`usecases/` sits **above** the domains: it may import any of them, and **no domain
may import `usecases`**. One-way, so circular imports cannot happen.
`tests/test_boundaries.py` enforces it.

## Transactions

A usecase never opens its own session. It receives the request's unit of work
(`src/database.py` → `UowDep`) and hands the same session to every repository it
uses — py-common's `UnitOfWork` spans a single engine, and two sessions would
commit separately.
