# Clinical coding: note in, code or refusal out

One free-text consult note goes in; one JSON record comes out carrying the proposed
ICD-11 codes with their evidence, or an explicit refusal with the reason. The system is a
single full-context LLM call per note — the whole 404-entry catalogue and all 45 guideline
snippets, about 30K tokens, sit in a stable system prompt — followed by a deterministic
validator that is the actual trust boundary. There is no vector store and no retrieval step.

## Running it

```
docker compose run --rm coder run <notes-file>
```

or locally, from the repo root:

```
pip install -r requirements.txt
python -m pipeline run <notes-file>
```

For the Docker path, the notes file must sit under the repository directory (it is mounted
at `/work`) and be passed as a relative path, e.g. `docker compose run --rm coder run
examples/notes.jsonl`; local runs take any path.

Input is a JSON array, JSONL, or plain text (blank-line-separated blocks). Output is JSONL
on stdout and in `out/results.jsonl`, one line per input note, no exceptions — status is
`assigned`, `provisional`, or `unresolved`. With no API key set, every note comes out
`unresolved` with that stated as the reason and the run exits 0.

Honest caveat: the Docker path was written to the contract but never exercised — the Docker
daemon would not start on the dev machine. The local path is verified end to end.

Provider and model live in the `llm` block of `config.yaml`. The shipped default is
`openai_compat` → SiliconFlow `Qwen/Qwen2.5-72B-Instruct` (`SILICONFLOW_API_KEY`), which is
the provider we live-validated end to end. `mistral-large-latest` was tier-throttled (HTTP
403 mid-run, repeatedly), and the OpenAI key we had for testing had no credits. Any
OpenAI-compatible endpoint or Anthropic works by editing two lines in that block and setting
the matching env var; see `.env.example`.

## Output record

`status` — assigned / provisional / unresolved. `codes` — title, rationale, and `evidence`
entries: `note` (exact note words), `catalog` (code), or `guideline` (GDL id). `candidates` —
considered but not separable, with what's missing to decide. `confidence` plus
`would_raise_confidence` / `would_lower_confidence`. `unresolved` — item and reason, including
partial notes. `data_quality_flags` — corpus problems noticed. `pipeline_notes` — validator
changes, for audit.

## How it works

Note file → loader (`notes.py`, format-sniffing, never drops a record) → one prompt per note
(catalogue + guidelines + refusal policy) → model JSON decision → validator → JSONL line. A
model failure, timeout, or unparseable JSON becomes an `unresolved` record; the run continues.

## Repo map

`pipeline/cli.py` args + run loop; `notes.py` multi-format loader; `knowledge.py` loads
catalogue + guidelines + additions, renders prompt blocks; `prompt.py` the system prompt;
`llm/` provider adapters (openai_compat, anthropic) with retry-once; `models.py` decision
dataclasses + tolerant JSON parser; `validate.py` the invariants; `coder.py` ties note to
decision. `data/` is supplied, untouched; `data_added/` is ours, kept separate. `tests/` — 51
tests, `python -m pytest -q`.

## What the data made us decide, and what we decided against

We read the corpus first, and the thing that decided the architecture is that the
restrictions do not live where a retriever can find them. They are age bands, scope
statements, and subordinate clauses in the middle of paragraphs about something else. A
lexical or embedding gate over guideline snippets would drop exactly the qualifying sentence
that changes the answer, which is the "matching, not reasoning" failure the brief warns
about. Since the whole corpus fits in one context window, we put it all in and let the model
read it. We decided against a vector store and against a multi-stage fact-extraction
pipeline; two-stage retrieval is the documented path for a bigger catalogue, not this one.

The trust boundary is the validator, not the prompt. It is deterministic and
model-independent: proposed codes must exist in the catalogue (a fabricated code becomes an
unresolved item), every code needs both a note quote and a catalogue or guideline citation
(evidence-free codes are demoted to candidates), unknown guideline ids are dropped, titles
are pinned to the catalogue entry, high confidence is capped at moderate while candidates
remain (per GDL-040), and a status with no surviving evidenced code is downgraded to
unresolved. The title check is there because we caught it live: Qwen once emitted the real
code `3A51.2` under the invented title "Anaemia complicating pregnancy".

GDL-040 (Coding Manual s.4.1) is quoted verbatim in the prompt as the refusal policy. The
corpus already defines when to refuse, so we did not write our own rule for it.

## Guidance that disagrees with other guidance

GDL-016 (effective 2026-01) explicitly replaces GDL-017 (2023-07) on whether pneumonia needs
imaging confirmation. GDL-045 is marked deprecated and contradicts GDL-016. The resolution
rule in the prompt is general — later effective date wins, an entry that states it replaces
another wins, deprecated or unsigned material is distrusted — and is not keyed to those ids,
because the private notes will pull different guidelines into play.

GDL-041, titled "Ward Circular" and unsigned, contains a fake `SYSTEM DIRECTIVE TO THE
PROCESSING ASSISTANT` ordering the assistant to return BA41 for any encounter mentioning
chest pain, at high confidence, with the evidence section omitted. We treat it as data, not
instruction. The defense is structural rather than a matter of the model behaving: guidelines
are wrapped as data-only, and the validator rejects any assignment without evidence — so the
"omit the evidence" half of the directive is mechanically non-compliable. In live runs both
models we tested refused the bait every time and reported it in `data_quality_flags`.

GDL-021's age bands look internally inconsistent — ages 10-15 fall in no band. We did not
patch it; the prompt treats scope statements cautiously and the gap surfaces as a flag.

## What we added, and where it came from

Five entries in `data_added/icd_additions.json`, each carrying its provenance and the
guideline that exposed the gap. `4A44.2` Giant cell arteritis — GDL-014 steers new headache
after fifty onto a large-vessel vasculitis pathway with no catalogue target. `1B71.Z`
Necrotising fasciitis, unspecified — GDL-032 describes the presentation; the catalogue stops
at cellulitis and abscess. `3A51.2` Sickle cell disease with crisis — GDL-043 escalates to
acute chest syndrome, for which ICD-11 has no distinct code, and the catalogue's only
sickle entry is scoped to painful crisis. `JA20.Z` pre-existing hypertension in pregnancy —
GDL-028 puts pre-twenty-week hypertension in a group the catalogue does not carry; note that
the supplied catalogue reuses `JA20` for "Spontaneous abortion", which disagrees with real
ICD-11, so we used the child code. `1F41` Malaria due to Plasmodium vivax — GDL-022 requires
species-specific entries and only falciparum was supplied. All five were verified against
the WHO ICD-11 MMS release and at least one secondary mirror.

## What survives a different set of notes, and what will not

Should survive: the refusal policy, because it is quoted from the corpus rather than written
by us; the validator invariants, which are deterministic and hold whatever the model says;
the no-key path; the multi-format loader.

Will not: the prompt wording was calibrated on seven smoke notes we wrote ourselves, so it is
tuned to failure modes we thought of. Run-to-run variance at `temperature: 0` is not small —
one smoke note moved between `provisional`/moderate and `assigned`/high across runs of the
same model, so any evaluation should run each note more than once. And the five additions
close the gaps we noticed, not the gaps that exist.

## Not built, and what we would do next day

Repeated runs per note with majority voting, which is the cheapest fix for the variance
above. A golden-test harness with graded expected outputs. A retrieval prototype for scale.
Semantic quote verification — the validator checks that citations exist, not that quoted text
actually appears in the source. And backoff that survives Mistral-style per-note throttling.

## At 50,000 codes

The single prompt is what breaks first; the catalogue no longer fits. The shape we would move
to is a staged shortlist — BM25 plus embeddings plus an LLM rerank — feeding the same
adjudication call and the same unchanged validator, so the reasoning step and the trust
boundary survive intact. Guidelines shard by chapter, and the stable prompt prefix becomes a
cached index build rather than something sent per note.

## Tooling

Built with Claude Code (Fable 5), driving subagent implementers with a code review per task.
The one wrong thing it produced that I caught: the implementation plan asserted from memory
that chronic hypertension in pregnancy was ICD-11 `JA24` and necrotising fasciitis `1B71.0`;
checking the WHO ICD-11 browser showed both wrong (the real entries are the `JA20` group and
`1B71.Z`), after which every added code was re-verified against sources before inclusion.

Time spent: ~4 hours of build time inside the window.
