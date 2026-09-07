# Configurable routing planner

A small Python tool that inventories relative filenames and proposes folders using rules supplied in JSON. It does not read document contents, copy, move, rename, or delete source files. The included library-exhibit scenario and every fixture were invented independently for this edition.

Requires **Python 3.10+**, standard library only. Verified with **Python 3.12.2** on macOS. Run commands from this directory.

## Try the complete example

```sh
python3 -B demo.py
```

The demo creates five text files in a temporary source tree, scans their names, applies the example rules, and checks its output against `examples/expected-plan.csv`. It prints **3 routed, 2 review** and removes only its own temporary example on exit. It neither requires nor invokes PowerShell.

| Example filename | Proposal |
| --- | --- |
| `incoming/ExhibitLabel.txt` | `Exhibits/Labels/ExhibitLabel.txt` |
| `incoming/LightingNotes.txt` | `Exhibits/Lighting/LightingNotes.txt` |
| `incoming/label-lighting.txt` | Review: two different destinations matched |
| `incoming/mystery.txt` | Review: no signal matched |
| `sketches/Atrium.txt` | `Exhibits/Sketches/Atrium.txt` |

No priority table decides the ambiguous row. A review row has an empty destination.

## CLI and file contracts

```sh
# Scan a directory you choose; reads names only.
python3 router.py scan /path/to/example-root --output new-catalog.csv

# Or use the provided fictional catalog without scanning anything.
python3 router.py plan examples/catalog.csv --rules examples/rules.json --output new-plan.csv

# Export routed rows to the separate PowerShell copy-preview contract.
python3 router.py export-copy new-plan.csv --output new-copy-plan.csv
```

All output files must be new. Existing files are refused, including symlink output paths. Parent output directories must already exist. Outputs are UTF-8 CSV with proper quoting. The planner returns exit code 0 for a valid plan, even when some rows need review; invalid configuration, malformed input, and output errors return 2.

| File | Exact columns |
| --- | --- |
| Catalog | `source_path,kind` |
| Routing plan | `source_path,status,destination,rule_ids,reason` |
| Copy-stage input | `SourceRelativePath,DestinationRelativePath` |

`kind` is `file`, `symlink`, or `other` in scanned catalogs. Only `file` is routed. Planning a supplied CSV does not prove a file exists or remains unchanged; the copy stage must revalidate its source root and actual files. `export-copy` excludes and counts review rows. It rejects malformed routed rows, duplicate source/destination paths, rooted paths, traversal, and names that are not portable to Windows. It exports proposals, not an approval to copy files. Use the separate copy tool's preview and explicit execution controls.

`examples/copy-plan.csv` is the exact three-row handoff for the example. It contains no machine-specific root. Supply source and destination roots separately to the copy stage, using a matching example tree.

## Rule schema

```json
{
  "rules": [
    {
      "id": "label-text",
      "target": "Exhibits/Labels",
      "name_terms": ["label"],
      "extensions": [".txt"]
    }
  ]
}
```

Each rule needs a unique `id`, a relative `target` folder, and at least one selector:

- `name_terms`: whole normalized phrases in the filename stem.
- `path_terms`: whole normalized phrases in an individual parent-directory component.
- `extensions`: case-insensitive final suffixes including the leading dot.

Selectors within a rule combine with AND. Entries within each selector list combine with OR. CamelCase splits before case folding; punctuation becomes word separation. Terms are literal phrases, not regular expressions. For example, `label` matches `ExhibitLabel`, but not `Labels`. No stemming or fuzzy matching is performed. Unknown rule fields, empty selectors, duplicate IDs, and unsafe target paths fail validation.

All matching rules are evaluated. Several matching rules with the same target produce one proposal and preserve all matching rule IDs. Different targets produce `ambiguous_rules`. Duplicate normalized source paths and case-insensitive destination collisions put every affected row into review. No row silently wins.

## API

`router.py` exports `normalized_words`, `relative_path`, `validate_rules`, `matches`, `classify`, `plan`, `inventory`, `read_catalog`, `write_csv`, and `export_copy`. Call `validate_rules` before passing a rules list into `classify` or `plan`.

`classify` returns one decision. `plan` adds cross-row duplicate/collision checks. `inventory` walks without following symlinks and records relative paths in deterministic order. `export_copy` returns `(copy_rows, excluded_review_count)` and performs no filesystem writes itself.

## Verify and limitations

```sh
python3 -B -m unittest discover -s tests -v
```

23 tests pass, covering ambiguous/no-signal decisions, same-target matches, literal phrase boundaries, Windows separators, long paths and special characters, traversal, duplicate/colliding paths, invalid rules, quoted CSV, refusal to overwrite, symlink exclusion, the complete demo, and mixed reviewed/routed handoff export.

This is a proposal generator, not a migration executor or a content classifier. Its case-insensitive collision check is deliberately conservative across platforms. A scan is a snapshot and cannot protect against later filesystem changes. It does not resolve Unicode-normalization aliases, hard-link identity, content equality, or underlying filesystem path-length limits. The copy-export bridge applies stricter Windows name checks than pure planning. Documents are never opened for classification.

## Provenance

This edition adapts generic engineering concepts from earlier automation: separator-aware filename handling, camelCase normalization, boundary-aware keyword checks, and auditable CSV decisions. The configurable engine, conservative multi-rule decision policy, new schema, CLI, copy bridge, tests, and exhibit examples were written for this edition with AI assistance. It is **not** the original classifier with renamed records.

Original organizational taxonomies, rule priorities, routing exceptions, identity resolution, roster inclusion criteria, operational paths, and source data are excluded. No source catalog or record was redacted, pseudonymized, or reused as a fixture. This edition does not claim behavioral parity with the original workflow.

Implementation references: Python's official [CSV documentation](https://docs.python.org/3/library/csv.html) for newline-aware dictionary CSV handling, and [pathlib documentation](https://docs.python.org/3/library/pathlib.html) for explicit path representation and checks.
