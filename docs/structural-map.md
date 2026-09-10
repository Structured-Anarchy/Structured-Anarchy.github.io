# Structural Map and private session content

The Structural Map stores one shared argument graph across sessions. Theses are entry points into ordinary propositions; conjunctions of premises support or refute one signed proposition. Reused premises keep their identity across views. [Component-wise maximum-entropy inference](probability-inference.md) computes model probabilities separately from extraction, using the agreed clause and leaf priors.

Session extraction is separate from site generation; the fictional graph used in tests is never published as group content. The Discussions index displays the encrypted session catalogue and full transcripts only after unlocking, alongside any public discussion notes.

## Private authoring and encrypted publishing

Everything under `data/*` is ignored. Readable originals remain in `data/transcripts/`, refined text in `data/refined-transcripts/`, and authoring data in `data/knowledge/knowledge.toml`. Optional extraction reviews live in `data/knowledge/reviews/`. The archive includes original/refined transcript text, the authoring TOML, referenced session metadata, and review Markdown. Audio and unrelated local files remain local.

Each session can reference `metadata_file = "data/knowledge/sessions/<session-id>.toml"`. That TOML contains exactly `date` (a full `YYYY-MM-DD` date, quoted or native TOML date) and `location`. It is the source of truth for display metadata: packing derives a `day month year · location` session title and source labels without rewriting the authoring TOML or any transcript bytes. Discussions sorts by session date, newest first; citations, transcript headings and speed-reader labels use the same title. Invalid or missing referenced metadata fails validation. Unpacking preserves both authoring and metadata files, and decrypted verification compares the graph against their resolved content. Older archives without references retain their existing titles.

`encrypted/` is the tracked publishable archive. It contains an opaque manifest and authenticated ciphertext with random filenames. Neither transcript names, statements, meanings, excerpts, nor the passkey are embedded in public HTML/JavaScript. Builds copy only the encrypted archive to `dist/assets/private/`.

Encryption uses AES-256-GCM with a fresh 96-bit nonce per resource, a 128-bit authentication tag, and PBKDF2-HMAC-SHA256 with a random 128-bit salt and 600,000 iterations. The asset name is authenticated as additional data. The format is shared by Python's [AESGCM implementation](https://cryptography.io/en/stable/hazmat/primitives/aead/) and the browser's [Web Crypto key derivation](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey). Repacking generates a new salt, nonces, and opaque filenames.

The Structural Map, Discussions, and Symbols and Meaning display a visible text field for the passkey. The browser derives the key locally; the passkey is not sent to a server. It decrypts the graph on unlock and transcripts lazily. Decoded resources and the key are cached only in page memory. Ordinary archive links navigate within that memory-only view; refreshing, leaving the archive, or selecting “Lock archive” clears it. New tabs must unlock independently. Browser storage retains only existing theme/reader preferences. Public page shells, discussion notes and the landing page do not require unlocking. The Members page and its navigation, image exports, and public manifest entries are no longer generated; profile source files remain untouched.

Every evidence passage links to `/discussions/#source=<source-id>&start=<codepoint>&stop=<codepoint>`. The fragment is resolved after unlocking and is never sent in the HTTP request. Transcript margin markers sit at the rendered row containing each evidence start, regroup when text wraps, and list the focal theses whose recursive graphs use those passages. This includes objections as well as supporting assertions: a marker does not certify the thesis's truth. The source text is rendered with text nodes, preserving decoded codepoints and line endings.

Full transcripts share the existing speed reader with discussion notes and passage popups: WPM, words per glance, font size, highlighting, playback, skipping and keyboard controls. Standalone `MM:SS` / `HH:MM:SS` timecodes and bracketed leading timecodes render in a separate margin, retaining `~` for estimates. Their text nodes carry the existing `data-reader-skip` annotation; neither transcript bytes, provenance offsets nor the reader implementation change. Times within spoken sentences remain part of the reading text. Linked transcripts start at the highlighted passage's first spoken word; text selection can choose another starting point. Provenance anchors do not split spoken words. The reader resets on archive navigation and locking, and never persists transcript text or reading positions.

Transcript views omit the leading refinement-export title and source-filename pair, including its blank separator. Those rows remain hidden and excluded from speed reading without changing source bytes or evidence offsets. Editorial, timing and speaker notes remain visible; matching words elsewhere in the transcript are not removed. The session title is followed directly by the transcript, without an explanatory UI paragraph.

`/symbols-and-meaning/` lists all symbols by descending meaning count by default, with alphabetical tie-breaking; alphabetical sorting is also available. Hovering or selecting a symbol opens an interactive popup listing all its meanings; declared meanings link to their defining passages and exact transcript positions. Undeclared default meanings are counted but explicitly have no definition passage. The same distinction and popup flow are used in the argument explorer.

Thesis counts traverse all incoming support/refutation clauses recursively, counting each clause once and stopping at shared nodes and cycles. Session totals use assertion and literal evidence across every reachable atom. Green/red totals describe each clause's local signed consequent, not its propagated effect on the root. The index can be sorted by topic, support count, refute count or model probability in either direction. Probabilities appear beside counts and inside atom circles; selecting a circle's value explains its assumptions. Negated views display the complementary probability.

“Also used in … theses” links to other thesis entry points whose recursive graphs contain the atom. It excludes the current thesis, the atom itself and non-thesis intermediate claims, deduplicating shared paths and cycles.

Only questions explicitly raised during a session appear in the explorer. They carry `origin_kind = "session"`, a valid `session_id`, and exact passage origins belonging to that session. Extractor-generated questions use `origin_kind = "extraction_review"` and stay private; legacy questions without a reviewed origin kind remain hidden. Question paraphrases must not append a reviewer's inferred challenge to something a participant actually asked.

An atom's labelled “Passages” button opens assertion evidence. The secondary extraction/reconstruction note explains the mapping but supplies no premise. Its “Inference context” link has a distinct purpose: locating the source's argumentative connection. Necessary induced premises display an explicit unsubstantiated badge and dashed circle; their reconstruction context is never labelled assertion evidence.

This is shared-passkey access: anyone with the passkey can copy the decoded content. The passkey must stay out of the public repository. A future passkey change cannot revoke access to older archives already downloaded with the old passkey.

Run commands from the repository root in the required environment:

```sh
conda run -n structured_anarchy_py pip install -r requirements.txt
conda run -n structured_anarchy_py python scripts/knowledge.py unpack
conda run -n structured_anarchy_py python scripts/knowledge.py validate
conda run -n structured_anarchy_py python scripts/knowledge.py infer
conda run -n structured_anarchy_py python scripts/knowledge.py pack
conda run -n structured_anarchy_py python scripts/knowledge.py verify-encrypted
conda run -n structured_anarchy_py python scripts/build_site.py
conda run -n structured_anarchy_py python scripts/check_private_content.py --output dist
```

`unpack` restores into ignored `data/` and refuses to overwrite differing local files. Skip unpack when the current private files already exist. For a genuinely new base with no archive, use `init`. The passkey commands prompt securely in the terminal; alternatively append `--passkey-file data/.passkey`, containing only the passkey plus an optional final newline. There is no command-line argument accepting the passkey itself. Do not commit that file or set the passkey in a shell command saved to history.

Source offsets count Unicode codepoints from decoded bytes, starting at zero, with an exclusive stop. Neither newlines nor Unicode are normalized. Each source SHA-256 pins its complete byte version; each pointer checks range and first/last six characters. Short passages use their entire contents for both endpoint strings. These checks establish provenance integrity, while the extraction skill separately requires semantic review.

## Extraction skill

The versioned skill is [extract-theses-and-logical-structure](../skills/extract-theses-and-logical-structure/SKILL.md). Its references explain the schema, logical review procedure and fictional two-session example. Each clause needs both source warrant and a separate logical-completeness check. Atoms express one direct, independently contestable assertion; empirical assertions need conceivable disconfirmation, while norms and definitions need clear grounds for disagreement. Remove each premise in turn to check that it is necessary, not just contextual padding. Review must cover support and refutation for every atom, including induced premises, with a private coverage ledger. The additive version-1 schema permits an essential induced premise only with empty assertion origins, separately named induction context, a rationale and the IDs of clauses using it. Every clause still needs at least one genuinely sourced premise; all-induced antecedents and fabricated asserted occurrences are rejected. Probability inference is a separate derived export, never an extraction or provenance field.

To register it in a local Codex skills directory, create a symlink named `extract-theses-and-logical-structure` pointing to this checkout's `skills/extract-theses-and-logical-structure` directory. Then invoke `$extract-theses-and-logical-structure` with the refined session filename. The symlink itself is machine-local, not a repository artifact.

## Automated checks

```sh
conda run -n structured_anarchy_py pip install -r requirements-test.txt
conda run -n structured_anarchy_py python -m playwright install chromium
conda run -n structured_anarchy_py pytest --browser-tests
```

Ordinary `pytest` runs schema, provenance, encryption, privacy, and existing site tests. `--browser-tests` additionally runs real Chromium decryption and desktop/mobile navigation, meanings, source passages, speed reading, locking, and existing-page checks against synthetic content.

GitHub Actions runs tests, packaging integrity, a build, and public-file checks on pull requests and main updates. Main builds additionally decrypt in memory, validate the actual graph and all pointers, and check public artifacts for private excerpts/passkeys. Set the repository Actions secret `CONTENT_PASSKEY` to enable that required check. PR jobs never receive the secret; they validate full provenance using mocks. Deployment depends on successful checks and runs only on main.

The plaintext scanner catches tracked private directories, exposed passkeys, long copied transcript fragments, and extracted statements/definitions. It is a regression guard, not a proof against arbitrary paraphrases. Private validation failures are kept generic in public CI logs; run the validator locally for detailed errors. CI cannot judge semantic fidelity of an extraction.

The existing `--production` build still requires configured giscus IDs. Those IDs are currently unset; the Pages workflow retains the existing regular build command.
