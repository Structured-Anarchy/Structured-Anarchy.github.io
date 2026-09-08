# Structural Map and private session content

The Structural Map stores one shared argument graph across sessions. Theses are entry points into ordinary propositions; conjunctions of premises support or refute one signed proposition. Reused premises keep their identity across views. Probability inference is deliberately absent until its semantics are settled.

The real map initially contains no theses. Session extraction is a separate step; the fictional graph used in tests is never published as group content. Discussions and members also remain empty.

## Private authoring and encrypted publishing

Everything under `data/*` is ignored. Readable originals remain in `data/transcripts/`, refined text in `data/refined-transcripts/`, and authoring data in `data/knowledge/knowledge.toml`. Optional extraction reviews live in `data/knowledge/reviews/`. The archive includes original/refined transcript text, the authoring TOML, and review Markdown. Audio and unrelated local files remain local.

`encrypted/` is the tracked publishable archive. It contains an opaque manifest and authenticated ciphertext with random filenames. Neither transcript names, statements, meanings, excerpts, nor the passkey are embedded in public HTML/JavaScript. Builds copy only the encrypted archive to `dist/assets/private/`.

Encryption uses AES-256-GCM with a fresh 96-bit nonce per resource, a 128-bit authentication tag, and PBKDF2-HMAC-SHA256 with a random 128-bit salt and 600,000 iterations. The asset name is authenticated as additional data. The format is shared by Python's [AESGCM implementation](https://cryptography.io/en/stable/hazmat/primitives/aead/) and the browser's [Web Crypto key derivation](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey). Repacking generates a new salt, nonces, and opaque filenames.

The Structural Map displays a visible text field for the passkey. The browser derives the key locally; the passkey is not sent to a server. It decrypts the graph on unlock and transcripts only when passages are opened. Decoded resources and the key are cached in page memory. Refreshing, leaving the page, or selecting “Lock archive” clears that state. Browser storage retains only existing theme/reader preferences. The public landing, discussions, and members pages do not require unlocking.

This is shared-passkey access: anyone with the passkey can copy the decoded content. The passkey must stay out of the public repository. A future passkey change cannot revoke access to older archives already downloaded with the old passkey.

Run commands from the repository root in the required environment:

```sh
conda run -n structured_anarchy_py pip install -r requirements.txt
conda run -n structured_anarchy_py python scripts/knowledge.py unpack
conda run -n structured_anarchy_py python scripts/knowledge.py validate
conda run -n structured_anarchy_py python scripts/knowledge.py pack
conda run -n structured_anarchy_py python scripts/knowledge.py verify-encrypted
conda run -n structured_anarchy_py python scripts/build_site.py
conda run -n structured_anarchy_py python scripts/check_private_content.py --output dist
```

`unpack` restores into ignored `data/` and refuses to overwrite differing local files. Skip unpack when the current private files already exist. For a genuinely new base with no archive, use `init`. The passkey commands prompt securely in the terminal; alternatively append `--passkey-file data/.passkey`, containing only the passkey plus an optional final newline. There is no command-line argument accepting the passkey itself. Do not commit that file or set the passkey in a shell command saved to history.

Source offsets count Unicode codepoints from decoded bytes, starting at zero, with an exclusive stop. Neither newlines nor Unicode are normalized. Each source SHA-256 pins its complete byte version; each pointer checks range and first/last six characters. Short passages use their entire contents for both endpoint strings. These checks establish provenance integrity, while the extraction skill separately requires semantic review.

## Extraction skill

The versioned skill is [extract-theses-and-logical-structure](../skills/extract-theses-and-logical-structure/SKILL.md). Its references explain the schema and a complete fictional two-session example. The skill includes exact pointer/span helpers, conservative reuse decisions, treatment of missing premises, and mandatory validation before completion.

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
