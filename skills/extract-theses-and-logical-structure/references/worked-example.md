# Fictional worked example

`scripts/make_mock_knowledge.py` contains two complete synthetic transcripts and their extraction. Generate fully serialized TOML with valid exact pointers in a fresh workspace:

```sh
conda run -n structured_anarchy_py python scripts/make_mock_knowledge.py --root /tmp/my-extraction-example
conda run -n structured_anarchy_py python scripts/knowledge.py --root /tmp/my-extraction-example validate
```

Read that workspace's `data/knowledge/knowledge.toml` and two `data/refined-transcripts/*.txt` files. Use a fresh temporary directory each time: the generator refuses to overwrite existing `data/`. Never run it in the real repository's data directory.

The first session yields:

- A = `garden-open`: “The garden should stay open.”
- B = `garden-quiet`: “The garden is quiet.”
- C = `quiet-open`: “Quiet places should stay open.”
- D = `garden-costly`: “The garden is costly.”
- E = `costly-close`: “Costly places should close.”

It supplies `B ∧ C ⇒ A`, `D ∧ E ⇒ ¬A`, and `A ⇒ B`. These are three arguments. The first has two jointly necessary premises; the second opposes A. The third creates a cycle, which is recorded without treating it as independent evidence.

The second session introduces `library-open` and `library-quiet`, reusing C in `library-quiet ∧ C ⇒ library-open`. It revisits A, adding an occurrence and passage without duplicating the proposition. “What do we mean by costly?” remains an open question; no definition is invented.

Quiet has four meanings globally:

1. Normative (undeclared).
2. Little traffic noise, permitting birdsong: two disjoint passages define this meaning.
3. A place that feels calm.
4. An absence of all sound.

The speaker deliberately selects meanings 2 and 3, so the binding is `collective`. Meaning 4 is explicitly excluded and remains in the base. Meaning 1 is unselected but not explicitly rejected. The second session explicitly refers back to the same meanings, warranting reuse. Without that context, do not infer reuse from the word alone.

| Tempting output | Correct action |
| --- | --- |
| Invent “all costly places are bad” as a bridge | Record only the actual closing principle; retain other gaps as questions. |
| Turn a definition question into a definition | Keep the default meaning and record the question. |
| Count a repeated argument twice | Reuse the rule ID, union evidence, and record occurrences. |
| Delete the silent meaning | Retain it globally and mark its local exclusion. |
| Infer confidence from the cycle | Preserve graph identity; inference is deferred. |
| Cite a large range spanning unrelated tangents | Use the smallest sufficient union of passages. |

The tests in `tests/test_knowledge.py`, `tests/test_vault.py`, and `tests/test_structural_map_browser.py` exercise these invariants. Passing them does not replace semantic review of a real extraction.
