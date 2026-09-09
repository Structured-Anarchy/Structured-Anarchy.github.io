# Authoring schema, version 1

The authoritative schema is `schemas/knowledge.schema.json`; semantic checks live in `sitegen/knowledge.py`. Author `data/knowledge/knowledge.toml`. Set `schema_version = 1`. Every top-level array below is required, even when empty. IDs are globally unique lowercase kebab strings; preserve existing IDs. Prefixes such as `p-`, `argument-`, `symbol-`, and `meaning-` help avoid collisions.

| TOML array | Required fields | Meaning |
| --- | --- | --- |
| `[[sources]]` | `id`, `file_name`, `sha256`, `label` | A byte-versioned refined transcript. Generate with `register-source`. |
| `[[sessions]]` | `id`, `title`, `source_ids` | One session; optional ISO `date` string only when known. |
| `[[symbols]]` | `id`, `label`, `aliases` | Vocabulary family and surface spellings. |
| `[[meanings]]` | `id`, `symbol_id`, `kind`, `definition`, `origins` | `kind`: `normative` or `defined`. |
| `[[propositions]]` | `id`, `text`, `scope`, `kind`, `thesis`, `topics`, `origins`, `bindings` | `kind`: `empirical`, `normative`, `definitional`. `thesis` is boolean. Optional `evidence_status` is `sourced` (the default) or `induced`; the latter requires `induction`. |
| `[[arguments]]` | `id`, `premises`, `conclusion`, `explicitness`, `explanation`, `origins` | Premises jointly imply one signed conclusion. `explicitness`: `explicit` or `reconstructed`. |
| `[[occurrences]]` | `id`, `session_id`, `target_type`, `target_id`, `stance`, `origins` | Target type: `proposition`, `argument`, `meaning`. Optional source-grounded `attribution`. |
| `[[questions]]` | `id`, `text`, `proposition_ids`, `symbol_ids`, `origins` | Add `origin_kind = "session"` and `session_id` for a verified participant question; use `origin_kind = "extraction_review"` for a private review question. Related-ID arrays may be empty. Unclassified legacy questions are hidden. |

Each origin has exactly `file_name`, `start_char`, `stop_char`, `first_6_chars`, `last_6_chars`. Generate the TOML inline table with `scripts/knowledge.py cite`; register its refined source first. Source-substantiated assertion, binding, literal, argument and occurrence origins are nonempty. The normative placeholder's origins are empty. The induced-premise exception below does not relax provenance for sourced records. Every actual pointer, including induction context, is validated.

A binding goes in `[[propositions.bindings]]` immediately below its owning proposition, before the next `[[propositions]]`:

- `start_char`, `stop_char`: positions in the proposition's text, not the transcript.
- `symbol_id`: its label or aliases must match the span, ignoring case.
- `meaning_ids`: at least one meaning belonging to this symbol.
- `excluded_meaning_ids`: explicitly excluded meanings only, possibly empty.
- `selection`: `specified` (one meaning), `ambiguous` (unresolved alternatives), or `collective` (deliberately combined).
- `origins`: transcript passages establishing this usage.

Bindings cannot overlap. Repeated words need separate ranges. Identically worded claims with different referents, time, or meanings must have distinct scope/bindings rather than silently sharing an inference variable.

Question origin fields are an additive version-1 extension. Only questions explicitly classified as `session` are shown. Their required `session_id` must reference a session containing every cited source, and the passages must actually ask the question (a semantic check, not an automatic consequence of valid pointers). Review questions and unclassified legacy records remain recoverable but invisible in the website explorer.

A literal has `proposition_id`, boolean `negated`, and `origins`. `premises` is a nonempty array of literals of any arity; `conclusion` is one literal. Source-substantiated literals require nonempty origins. Argument origins substantiate the interpreted argumentative connection; literal origins substantiate assertions in that argument. These are separate from the logical-completeness obligation.

## Induced premises

The additive version-1 extension preserves existing sourced records unchanged. An induced proposition has `evidence_status = "induced"`, `origins = []`, and an `induction` table with:

- `rationale`: why this specific missing commitment is necessary, including what would fail without it.
- `argument_ids`: nonempty IDs of existing clauses actually using this atom as a premise.
- `context_origins`: nonempty validated passages locating the incomplete inference. These are explicitly **not assertion evidence**.

Its symbol bindings still need valid surface ranges and meaning selections; their origins may be empty when no usage was attested. Literal origins referring to induced atoms may likewise be empty. Do not invent a source occurrence for an induced assertion. Genuine sourced questions or rejections may be recorded, but an induced atom cannot claim an asserted/withdrawn occurrence. A supporting inference can target an induced atom without making that atom an explicit source assertion.

Every clause must contain at least one source-substantiated premise with nonempty literal origins. An all-induced antecedent is invalid, even if context passages exist. Clauses using induced premises must be `reconstructed`. An induced atom may receive its own support/refutation clauses subject to the same constraint. If actual assertion evidence is subsequently found, set status to `sourced`, add genuine origins/binding provenance and occurrences, and retain `induction` as historical metadata.

TOML placement matters: fields after `[[propositions.bindings]]` belong to that binding until the next table header. Do not accidentally put proposition fields beneath a binding header. Inspect the generated complete example for safe nesting. Unknown fields such as `confidence`, `probability`, or `accepted` fail validation.
