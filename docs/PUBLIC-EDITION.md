# Background, contribution and public scope

## Internship origin

Nicholas Farrar created the original document-organization and migration automation during his internship at Curo. His work involved defining requirements, directing AI-assisted implementation, iterating on the scripts and troubleshooting their behavior.

This repository presents an adapted public edition of the reusable engineering. It demonstrates how classification decisions, review outputs and filesystem operations can be separated and verified. It does not describe Curo's internal records or operating procedures.

## What the public edition demonstrates

The Python planner scans relative filenames, evaluates configurable rules and records proposed destinations or review reasons. It exports only unambiguous rows for the copy stage. The PowerShell copier previews those rows, requires explicit execution, compares content hashes and reports conflicts without overwriting existing files.

The edition retains and adapts generic filename normalization, path handling, CSV processing, bounded worker execution and per-file reporting. Its configuration format, neutral rules, fixtures, tests and several safety controls were prepared for public demonstration. In particular, its no-overwrite and hash-verification behavior must not be read as a claim about the historical tool's deployed behavior.

## Privacy and provenance

All example documents, catalogs, rules and results were independently invented. No original record was renamed or redacted into a fixture. Organization-specific taxonomies, identity logic, integrations, source records and operational notes are excluded. Mentioning the internship provides background, not an account of confidential client-handling practices.

The source was recovered from a backup whose completeness has not been established. This is not a complete production migration system or a claim of parity with the earlier workflow. Only the checks recorded in [Testing](TESTING.md) are claimed for this edition.

Nicholas directed the original project and the adaptation with AI assistance. The repository does not imply that every line was manually written without those tools.

## Contributing

Use fictional data in examples, bug reports and proposed changes. Include a minimal reproduction, the command used and the expected result. Do not attach private documents or operational logs.

## License

No license has been assigned. Publication does not grant an open-source license.
