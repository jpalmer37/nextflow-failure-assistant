# Nextflow failure assistant

Reads a `.nextflow.log`, extracts the failed task's evidence, sanitizes it, and
returns a cause, the log lines supporting it, and a ranked list of checks — or
`insufficient_evidence` when the log does not say enough.

It ships with a labelled corpus and an evaluation, because the interesting
question is not whether it produces plausible answers. It is whether it beats
`grep`.

Status: **evaluated local application.** Not deployed, not in production. The
model arm runs against a hosted model.

## Result

The test split was frozen before either arm ran on it: 12 cases, 7 injected and
5 real, with no cause family shared with the dev split.

| Metric | Keyword baseline | claude-sonnet-5 |
| --- | --- | --- |
| Cause accuracy, all 12 | 0.92 | 0.92 |
| First-check accuracy, all 12 | 0.92 | **1.00** |
| Cause accuracy, 5 real cases | 0.80 | 0.80 |
| First-check accuracy, 5 real cases | 0.80 | **1.00** |
| Quote grounding | 1.00 | 1.00 |
| Abstained when it should, 3 cases | 1.00 | 1.00 |
| Abstained when it should not | 0.00 | 0.00 |
| Median latency | 0.00 s | 5.44 s |

**The baseline is hard to beat, which was the hypothesis.** Nextflow prints the
cause in plain text under `Command error:` often enough that matching a dozen
regexes gets 11 of 12. On cause category the two arms tie.

The difference is which case each one misses, and that is the whole finding:

- `real-gzx-filename` — a stray character produced `reads.fastq.gzx`, so the
  tool reported `No such file or directory`. The baseline believes the error
  text and says `missing_input`. The model reads the command as executed, sees
  a path where a coverage number belongs, and says `bad_interpolation`. This is
  the case where surface matching is structurally unable to win.
- `real-missing-reference` — a plain missing FASTA. The model overreads it as
  `bad_interpolation` and gets the category wrong, but still puts
  `missing_input.0` first in its checks, so the advice it gives is right.

So the model's advantage is narrow and specific: it helps when the error string
names a symptom rather than a cause, and it costs 5 seconds a call. For a first
triage pass, run the baseline; reach for the model when the baseline's answer
looks like it is just restating the error.

Both arms are given the same knowledge. The notes in `nfdx/notes.py` are the
single source for the baseline's regexes and the model's prompt, so a win
cannot come from one arm simply being told more.

Full per-case rows: `reports/`.

## Corpus

19 cases, one directory each, holding a sanitized failure block and a label that
pre-registers the cause and the one check that resolves it.

**5 real** failures recovered from local Nextflow runs: a conda solve failure
(`spades=3.15.3*` absent for the platform), a corrupt gzip caught by
`fastp`/igzip, a missing reference FASTA in `augur align`, a `.gzx` filename
from a bad interpolation, and `-Xmxnullg` from a null memory value.

**14 injected** by running a small pipeline that breaks on purpose
(`corpus/build_injected.py`). These are real Nextflow logs; only the trigger is
chosen, which is what makes the label ground truth. One further scenario,
`container_unavailable`, is defined but was skipped because no Docker daemon was
available on the build machine.

All 5 real cases sit in the test split, so the reported number measures whether
tuning on injected failures transfers to real ones. A test asserts that no cause
family appears in both splits.

The dev split exists to iterate on. The baseline scores 1.00 on it by
construction — the signatures and the dev scenarios were written together — so
that number is not evidence and is not reported above.

The notes were changed once on dev before the freeze, to render the exit-status
hints the baseline already used. The model scores 0.86 on dev; its one miss is
`inj-timeout`, covered under limits.

## Running it

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev,sdk]'

# one log
python -m nfdx --log cases/real-gzx-filename/log.txt --arm baseline
python -m nfdx --log cases/real-gzx-filename/log.txt --arm llm

# the evaluation
python evaluate.py --split test --arm baseline --output reports/test-baseline.json
python evaluate.py --split test --arm llm      --output reports/test-llm.json

pytest
```

The model arm uses the Anthropic SDK when `ANTHROPIC_API_KEY` is set and the
Claude Code CLI otherwise; `--backend` forces one. The numbers above were
produced with the CLI backend, recorded in each report.

Rebuild the corpus with `python corpus/build_injected.py`. `corpus/build_real.py`
re-extracts the five real cases and only works on a machine holding the original
run logs; the sanitized output is committed, the source logs are not.

## Sanitization

`nfdx/sanitize.py` runs before anything reaches a model and before anything is
written to `cases/`. It replaces directories with `<path>` while keeping
filenames, since the filename is the diagnostic signal in at least one real
case. It also removes email addresses, IPv4 addresses, and the local username,
and accepts extra patterns via `--redact`.

`tests/test_corpus_is_publishable.py` fails if an absolute path, an address, or
an IP survives in any committed case. The corpus is public, so it is checked
like it.

## Limits

- 19 cases is small. Differences of one case are not significant, and the two
  arms differ by one case.
- Injected failures are easier than wild ones: the trigger is clean and single.
  The real slice is reported separately for that reason, and both arms score
  lower on it.
- Only task failures are handled. A pipeline that fails to compile never emits
  a task-failure block, so `from_log` returns nothing for it.
- `real-xmx-null` and `real-gzx-filename` share a cause family, so the real
  slice covers four distinct causes, not five.
- Grounding is checked on `supporting_lines` only. The free-text `explanation`
  is not verified, and does drift: on `real-gzx-filename` the model wrote
  `fastch.gzx` for `fastq.gzx` while quoting the line correctly. Trust the
  quoted lines, not the paraphrase.
- The label on `inj-timeout` says `timeout`; SIGTERM with exit 143 is also
  consistent with a manual kill. The model abstains there and is arguably not
  wrong. It is left as-is rather than relabelled to flatter either arm.
