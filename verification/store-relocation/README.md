# Diagnostic store relocation evidence

The manifest binds frozen generated artifacts, every embedded source module,
committed harnesses and sanitized report content. These are development checks,
not a successful Literate AI lifecycle, release, package, or deployment attestation.
No generated source is committed. The native diagnostic runtime is Elixir 1.18.4
on OTP 27; the declared deployment/toolchain gate must still run independently.

Supply an isolated real Kafka REST endpoint and a generated candidate. The Python
harnesses use the repository's existing pinned SDK test environment and
`tests/multi_support.py`. All fixture data and reports belong under ignored
`_build/`; credentials are private and omitted from retained reports.

```sh
.venv/bin/python tests/multi_store_move.py --hub "$CANDIDATE" \
  --eventing-rest-url "$KAFKA_REST_URL" --with-model \
  --report _build/store-default.json --keep-work _build/store-default
.venv/bin/python tests/multi_store_move.py --hub "$CANDIDATE" \
  --eventing-rest-url "$KAFKA_REST_URL" --no-default \
  --report _build/store-no-default.json --keep-work _build/store-no-default
.venv/bin/python tests/multi_store_move_fault.py --hub "$CANDIDATE" \
  --eventing-rest-url "$KAFKA_REST_URL" --crash-at after-first-snapshot \
  --no-default --report _build/store-kill.json --keep-work _build/store-kill
elixir tests/store_move_native.exs "$CANDIDATE" _build/store-local
.venv/bin/python tests/multi_model_capabilities.py --hub "$CANDIDATE" \
  --with-model --eventing-rest-url "$KAFKA_REST_URL" \
  --report _build/backend-models.json --keep-work _build/backend-models
.venv/bin/python tests/multi_aliases.py --hub "$CANDIDATE" \
  --legacy-hub "$LEGACY_QUALIFIED_HUB" --with-model \
  --eventing-rest-url "$KAFKA_REST_URL" \
  --report _build/store-aliases.json --keep-work _build/store-aliases
```

Use native `elixir`/`erl` on PATH for crash tests. A Docker client wrapper is
insufficient: the fault harness requires its subprocess PID to be the actual
observed BEAM process, proves kernel SIGSTOP state, then checks SIGKILL. It uses a
small independently compiled libc observer to stop real rename/link/unlink calls
at the requested boundary; no generated application fault hooks exist. Supported
`--crash-at` values are before-decision, after-decision, after-first-snapshot,
after-first-checkpoint, before-config, after-config and before-cleanup. Each run
requires a fresh private fixture directory. Failed exploratory runs and their
credentials remain ignored and are not retained proof.

The hot probe creates public originals, source retries, acknowledged and
unacknowledged deliveries in separate projects, rejects a foreign destination,
moves all writers at the same process/revision, verifies 16 concurrently accepted
mutations, kills the real process, and verifies all state after reopening. With
`--with-model`, one real pending semantic job survives provider failure, relocation
and restart, then completes under its original identity after provider recovery.
The local probe additionally verifies callbacks are never executed during a
freeze, rollback releases all writers, newer accepted target state survives
recovery, and a damaged installed snapshot fails closed without replacement.

The alias probe starts the separately supplied prior qualified producer, performs
a real historical project rename, and migrates its actual store. It checks
admitted alias routing, exact old-command cached results, stable canonical new
results, admission denial, dry-validation/update collision rejection, restart and
fail-closed cold startup with a deliberately conflicting registry. Backend model
checks observe actual controlled HTTP attempts from history/retrieval/archive
with matcher absent; replay checks both required effective capabilities and
normal NOT_FOUND lookup without pretending to run a fabricated attempt.
