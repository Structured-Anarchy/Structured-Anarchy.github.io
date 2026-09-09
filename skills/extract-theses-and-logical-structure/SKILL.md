---
name: extract-theses-and-logical-structure
description: Extract or review Structured Anarchy discussion graphs with logically complete Horn clauses, explicitly labelled missing premises, separate support and refutation searches, and exact transcript provenance. Use for session extraction and extraction review, not probability inference.
---

# Extract theses and logical structure

Work from the repository root. Read [the schema guide](references/schema.md) and [logical review procedure](references/logical-review.md) before editing. Use `schemas/knowledge.schema.json` and `scripts/knowledge.py`; do not design a replacement format. For the executable fictional example, follow [the worked example](references/worked-example.md).

## Inputs and private working files

- Session inputs are user-selected files in `data/refined-transcripts/`, decoded as UTF-8 without altering line endings. Raw audio, editorial placeholders, and this skill's examples are not session testimony.
- Read the existing `data/knowledge/knowledge.toml` first, including unused meanings and earlier occurrences.
- If the local base is absent but `encrypted/manifest.json` exists, recover it with `conda run -n structured_anarchy_py python scripts/knowledge.py unpack`. Append `--passkey-file data/.passkey` if the user supplied that ignored local file; never print its contents. If the passkey is unavailable, request it before dependent decryption. Never replace an unavailable existing base with an empty base.
- Only for a new base with no existing archive, run `conda run -n structured_anarchy_py python scripts/knowledge.py init`.
- Keep all readable extracted content, excerpts, scratch notes, and reports under ignored `data/`. Only encrypted artifacts may leave that directory. Never put real session content or the passkey in skills, tests, public assets, or commit messages.
- Run repository Python commands in `structured_anarchy_py`; install `requirements.txt` there if needed.

## 1. Establish the session and source versions

Read the selected transcript completely, in bounded chunks if needed. Preserve source order. Attribute speakers only where the source supports it. Do not infer a year, timestamp, identity, or group agreement from filenames, attendee lists, or silence.

Register a new refined source with:

```sh
conda run -n structured_anarchy_py python scripts/knowledge.py register-source 'data/refined-transcripts/session.txt' --id source-session --label 'Session label'
```

Reuse an existing registration when its hash matches. A hash mismatch means the source version changed: restore the old version or recheck every affected pointer before updating its hash. Never refresh a hash merely to make validation pass. Add/reuse a session with the appropriate source IDs; omit an unknown date.

## 2. Inventory topics and find existing claims

Make a private inventory of claims, definitions, objections, and unanswered questions. One session can contain many interleaved topics. Connect a tangent to its parent topic only when the transcript establishes that relationship.

Before creating a proposition, search the base by wording, aliases, topics, and meanings. Compare assertion and polarity; quantifiers, modality, exceptions, referents, and time; and selected meanings, including ambiguous versus deliberately collective usage. Reuse an ID only when these agree in context.

A repeated phrase or the same `Normative (undeclared)` placeholder does not prove shared understanding. Where uses remain contextually distinct, use separate scope descriptions and proposition IDs. Do not duplicate a claim just because its date or speaker differs.

## 3. Write atomic propositions and generate pointers

Write concise assertive statements, including normative and definitional claims; empirical falsifiability is not mandatory. Preserve `should`, `all`, `some`, `possibly`, negation, and qualifications. Split separately asserted conjuncts. Set `thesis = true` for focal claims; theses remain reusable as premises. Record questions as `questions`, not assertions. Hypothetical and rejected claims may exist, with matching occurrence stances.

Every source-substantiated proposition needs a nonempty origin set. The sole exception is an explicitly induced, unsubstantiated premise under section 5: its assertion origins must be empty, while separately named induction context explains why it is needed. Never cite a discussion of a topic as evidence for a missing assertion. Generate pointers; never estimate positions. Save an exact excerpt in ignored `data/`, then run:

```sh
conda run -n structured_anarchy_py python scripts/knowledge.py cite 'data/refined-transcripts/session.txt' --quote-file data/excerpt.txt
```

The output is a TOML inline table for an `origins` array. A trailing newline in the excerpt counts. Repeated excerpts are rejected: extend the quote or use verified `--start N --stop M` positions. Offsets are zero-based Unicode codepoints with an exclusive stop, as in Python `text[start:stop]`. Decode source bytes directly; do not normalize Unicode, strip text, or convert CRLF. For passages shorter than six characters, both endpoint strings contain the entire passage.

Keep several disjoint pointers when their union is needed. Do not replace them with a broad range that pulls in unrelated tangents. Provenance substantiates the extraction, not the proposition's truth.

This exception does not permit unspoken derived-only conclusions. Retain those as review notes or explicitly extractor-raised bridge questions tied to their source context. Distinguish an extractor's question from a question actually asked in the session; neither is testimony for its proposed answer.

## 4. Bind symbols to meanings

Identify nontrivial nouns, verbs, and meaning-bearing adjectives such as “natural” and “conscious.” Prefer meaningful phrases such as “stay open”; skip grammatical filler. Reuse symbols/aliases for supported inflections and derivations, including conscious/consciousness when they denote the same conceptual family. Shared spelling alone does not establish the same meaning.

Each symbol has exactly one default meaning: `kind = "normative"`, `definition = "Normative (undeclared)"`, `origins = []`. This is an unresolved placeholder, not an extracted societal definition. Add a defined meaning only with a concise one-line definition and nonempty origins; tangents can supply disjoint passages.

Every relevant surface occurrence needs a binding. Generate its codepoint ranges using:

```sh
conda run -n structured_anarchy_py python scripts/knowledge.py spans proposition-id 'surface phrase'
```

Select at least one meaning ID. Use the default when no contextual meaning can be established. `specified` selects exactly one meaning; `ambiguous` means unresolved alternatives; `collective` means deliberately combined meanings. Do not resolve ambiguity on the speaker's behalf. Attach transcript evidence for the binding itself. Bind induced premise surfaces too, but leave their binding origins empty when the usage was reconstructed rather than attested. A cited definition does not substantiate the induced assertion.

Preserve an explicitly excluded meaning globally and put its ID in the binding's `excluded_meaning_ids`. Mere nonselection is not exclusion. Selected and excluded sets cannot overlap. Reuse definitions across sessions only when contextual equivalence is established; otherwise retain distinct meanings and explain the uncertainty in the private report.

## 5. Construct warranted Horn arguments

An argument has **one or more** premise literals, exactly one conclusion literal, and its own origin set. There is no two-premise requirement. A literal is `{ proposition_id, negated, origins }`. Source-substantiated literals require nonempty pointers. A literal referring to an induced atom may have empty origins; do not manufacture testimony for it. Every clause must have at least one premise with genuine assertion provenance, not merely induction context.

There are two separate obligations: source passages must warrant interpreting the exchange as that argument, and the complete antecedent must suffice for its signed consequent. A speaker saying “because” or “therefore” satisfies neither obligation automatically. Assertion passages establish what was asserted, not its truth; inference-context passages establish the argumentative connection, not logical validity. Follow the counterexample/bridge checks in the logical review procedure before saving each clause.

Use `negated = true` to oppose the canonical proposition. If A says “We should not eat animals,” `¬A` negates that entire statement; it does not assert “We should eat animals.” Do not invent a separate atom called “not-A.”

Keep jointly required premises together. `B ∧ C ⇒ A` is one argument; never split it into independent `B ⇒ A` and `C ⇒ A`. Independent arguments are separate rules. Do not use a disjunctive or multi-atom head.

Strict Horn form allows at most one positive literal after conversion to a disjunction. All-positive premises with either a positive or negative conclusion are permitted. Negative premises can break this restriction. Run the validator; do not invent fake symbols to bypass it. If a warranted relation cannot be represented, retain a sourced open question and explain the limitation in the report.

For an implicit argument, use `explicitness = "reconstructed"`. Explain the exact logical role of each reconstructed step. Search the complete selected transcripts and existing graph for missing premises, including earlier/later returns and unused meanings. Reuse or add a sourced atom when its scope and meaning fit. If no substantiation is found, retain a missing atom only when it is necessary to complete this particular inference and at least one other antecedent atom is source-substantiated. Mark it `evidence_status = "induced"`, `origins = []`, and supply `induction` metadata as described in the schema guide. It is an unsubstantiated commitment open to attack, not something a speaker is claimed to have said. Do not add arbitrary plausible claims or encode the entire desired implication as a catch-all premise merely to force an inference to work. If no defensible minimal completion exists, retain an open question instead of an invalid clause.

Descriptive facts alone do not establish a moral conclusion. Examples alone do not establish universal claims; analogy needs a relevant transfer premise; correlation needs a causal bridge. Avoid concealed modal, quantifier, temporal, subject or meaning changes. An extraction explanation above the atoms is a review note, not an additional premise: nothing needed for validity may be hidden there. Do not add contrapositives or probability parameters. An objection to premise E undermines an argument using E; it does not automatically support the original thesis.

Before adding a rule, compare its order-independent premise set, conclusion, and polarity with existing rules. Reuse matches, union their origins, and add/reuse occurrences. Repetition must not multiply arguments. Shared dependencies and cycles are allowed; tautological self-support and contradictory antecedents are rejected. When correcting an existing incomplete extraction, preserve source speech history and save the prior clause privately; do not leave the known-invalid version active beside its repair.

## 6. Run separate support and refutation passes

Cover every atom, not only thesis entry points. First search for its supporting reasons and their necessary premises. Then make a separate pass looking for denials, counterexamples, qualifications, alternative meanings and objections in the surrounding dialogue and all later returns. Audit previously bare atoms as well as every new induced premise. Repeat targeted searches when a discovered bridge creates a new claim to contest; do not fabricate a minimum number of red edges or layers.

Record per-atom search coverage in a private ledger, distinguishing “no reason supplied,” “compatible alternative,” “bare disagreement,” “wrong scope/meaning,” “missing bridge” and a warranted signed refutation. An unsupported denial is still a sourced rejected occurrence, but cannot be an empty-antecedent clause. A refutation negates the complete canonical atom; a weaker qualification or opposite policy is not automatically that negation. Search induced premises for both substantiation and refutation before finalising them; promote them to sourced only when actual assertion passages are found, retaining their induction history.

## 7. Preserve development across sessions

Every sourced proposition, argument, and defined meaning requires at least one occurrence. Add/reuse occurrences for this session with source-grounded stances: `asserted`, `questioned`, `rejected`, `hypothetical`, or `withdrawn`. An induced premise has no invented occurrence: only genuine source challenges/questions receive occurrences while it remains unsubstantiated. Attribution is optional. These record speech, not group acceptance or truth.

Keep earlier occurrences when claims are challenged, qualified, or withdrawn. Re-running the same input must reuse matching occurrences and pointer sets. Preserve existing IDs and use consistent ordering for additions.

## Finalization: all checks must pass

1. Run `conda run -n structured_anarchy_py python scripts/knowledge.py validate`. Fix every schema, reference, Horn, source-hash, range, and endpoint error. Never remove required evidence or weaken validation to pass.
2. Re-read the union of passages for **each added or changed** sourced proposition, literal occurrence, implication, defined meaning, and binding. Separately reread every induced atom's context without mislabelling it assertion evidence. Recheck each clause for a counterexample to entailment, not merely for a speaker's assertion of the connection. The deterministic validator cannot do this semantic review.
3. Audit the complete support/refutation coverage ledger, including all induced atoms; check reuse, conjunctions, scope, polarity, excluded meanings and unresolved questions. Confirm a second run would not duplicate results.
4. Save `data/knowledge/reviews/<session-id>.md` with reused/new IDs, corrected/retired clauses, reconstructed rules, induced atoms and why each is necessary, where substantiation was searched, unresolved questions, per-atom support/refutation findings, and validation commands/results. Do not claim human/group approval.
5. Run `conda run -n structured_anarchy_py pytest` and `conda run -n structured_anarchy_py python scripts/build_site.py`.
6. For an update intended for the website, run `scripts/knowledge.py pack` and `scripts/knowledge.py verify-encrypted` with Python inside the conda environment, supplying the authorized passkey securely. Rebuild after packing, then run `python scripts/check_private_content.py --output dist` inside that environment. Only encrypted artifacts may contain session content outside `data/`.
7. For a website update, check the rendered encrypted graph, not just the authoring file: one shell per clause, all joint premises shown, induced atoms visibly unsubstantiated, premise-level support/refutation reachable, exact evidence links opening the matching transcript position, and recursive counts finite under shared dependencies/cycles. Use fictional content for committed browser tests. Do not author public transcript pages containing readable session text.

Do not call extraction complete until provenance validation and semantic review pass. If source text or a necessary passkey is unavailable, preserve completed private work and report the specific incomplete stage without claiming success.
