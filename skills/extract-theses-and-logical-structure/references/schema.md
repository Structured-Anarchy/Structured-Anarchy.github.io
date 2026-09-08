# Authoring schema, version 1

The authoritative schema is `schemas/knowledge.schema.json`; semantic checks live in `sitegen/knowledge.py`. Author `data/knowledge/knowledge.toml`. Set `schema_version = 1`. Every top-level array below is required, even when empty. IDs are globally unique lowercase kebab strings; preserve existing IDs. Prefixes such as `p-`, `argument-`, `symbol-`, and `meaning-` help avoid collisions.

| TOML array | Required fields | Meaning |
| --- | --- | --- |
| `[[sources]]` | `id`, `file_name`, `sha256`, `label` | A byte-versioned refined transcript. Generate with `register-source`. |
| `[[sessions]]` | `id`, `title`, `source_ids` | One session; optional ISO `date` string only when known. |
| `[[symbols]]` | `id`, `label`, `aliases` | Vocabulary family and surface spellings. |
| `[[meanings]]` | `id`, `symbol_id`, `kind`, `definition`, `origins` | `kind`: `normative` or `defined`. |
| `[[propositions]]` | `id`, `text`, `scope`, `kind`, `thesis`, `topics`, `origins`, `bindings` | `kind`: `empirical`, `normative`, `definitional`. `thesis` is boolean. Scope records contextual referents, time, and interpretation. |
| `[[arguments]]` | `id`, `premises`, `conclusion`, `explicitness`, `explanation`, `origins` | Premises jointly imply one signed conclusion. `explicitness`: `explicit` or `reconstructed`. |
| `[[occurrences]]` | `id`, `session_id`, `target_type`, `target_id`, `stance`, `origins` | Target type: `proposition`, `argument`, `meaning`. Optional source-grounded `attribution`. |
| `[[questions]]` | `id`, `text`, `proposition_ids`, `symbol_ids`, `origins` | An unanswered question or unsupported bridge. Related-ID arrays may be empty. |

Each origin has exactly `file_name`, `start_char`, `stop_char`, `first_6_chars`, `last_6_chars`. Generate the TOML inline table with `scripts/knowledge.py cite`; register its refined source first. All origin arrays are nonempty except the normative placeholder's, which must be empty. The validator checks every pointer, including nested binding and literal evidence.

A binding goes in `[[propositions.bindings]]` immediately below its owning proposition, before the next `[[propositions]]`:

- `start_char`, `stop_char`: positions in the proposition's text, not the transcript.
- `symbol_id`: its label or aliases must match the span, ignoring case.
- `meaning_ids`: at least one meaning belonging to this symbol.
- `excluded_meaning_ids`: explicitly excluded meanings only, possibly empty.
- `selection`: `specified` (one meaning), `ambiguous` (unresolved alternatives), or `collective` (deliberately combined).
- `origins`: transcript passages establishing this usage.

Bindings cannot overlap. Repeated words need separate ranges. Identically worded claims with different referents, time, or meanings must have distinct scope/bindings rather than silently sharing an inference variable.

A literal has `proposition_id`, boolean `negated`, and nonempty `origins`. `premises` is a nonempty array of literals; `conclusion` is one literal. Argument origins warrant the implication; literal origins substantiate their roles in that argument. A passage can serve both purposes.

TOML placement matters: fields after `[[propositions.bindings]]` belong to that binding until the next table header. Do not accidentally put proposition fields beneath a binding header. Inspect the generated complete example for safe nesting. Unknown fields such as `confidence`, `probability`, or `accepted` fail validation.
