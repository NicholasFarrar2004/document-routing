"""Configurable filename routing proposals. Never copies, moves, or deletes inputs."""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from collections import Counter

CATALOG_FIELDS = ['source_path', 'kind']
PLAN_FIELDS = ['source_path', 'status', 'destination', 'rule_ids', 'reason']
SELECTORS = ('name_terms', 'path_terms', 'extensions')


def normalized_words(text: str) -> str:
    """Separate camelCase and punctuation, then compare whole Unicode words."""
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return ' '.join(re.findall(r'[^\W_]+', text.casefold()))


def relative_path(text: str) -> PurePosixPath:
    """Accept either slash convention; reject rooted paths and traversal."""
    if not isinstance(text, str) or not text or any(ord(c) < 32 for c in text):
        raise ValueError('path must be nonempty text without control characters')
    if PureWindowsPath(text).drive or text.startswith(('/', '\\')):
        raise ValueError('path must be relative')
    parts = text.replace('\\', '/').split('/')
    if any(part in ('', '.', '..') or ':' in part for part in parts):
        raise ValueError('path contains an empty, traversal, or drive component')
    return PurePosixPath(*parts)


def validate_rules(config: dict) -> list[dict]:
    if not isinstance(config, dict) or set(config) != {'rules'} or not isinstance(config['rules'], list):
        raise ValueError('configuration must contain only a rules list')
    ids = set()
    for rule in config['rules']:
        if not isinstance(rule, dict) or set(rule) - {'id', 'target', *SELECTORS}:
            raise ValueError('unknown rule field')
        ident = rule.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', ident) or ident in ids:
            raise ValueError('rule IDs must be unique nonempty letters, digits, underscores or hyphens')
        ids.add(ident)
        target = relative_path(rule.get('target'))
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]*', p) or p.endswith(' ') for p in target.parts):
            raise ValueError('target folders must use portable letters, digits, spaces, underscores or hyphens')
        if not any(key in rule for key in SELECTORS):
            raise ValueError('rule must specify at least one selector')
        for key in SELECTORS:
            if key not in rule:
                continue
            terms = rule[key]
            if not isinstance(terms, list) or not terms or not all(isinstance(x, str) and x for x in terms):
                raise ValueError('selectors must be nonempty lists of strings')
            if key == 'extensions':
                if any(not re.fullmatch(r'\.[A-Za-z0-9]+', x) for x in terms):
                    raise ValueError('extensions must include a dot and letters or digits')
            elif any(not normalized_words(x) for x in terms):
                raise ValueError('terms must contain words')
    return config['rules']


def phrase_in(text: str, phrase: str) -> bool:
    return ' ' + normalized_words(phrase) + ' ' in ' ' + normalized_words(text) + ' '


def matches(path: PurePosixPath, rule: dict) -> bool:
    if 'name_terms' in rule and not any(phrase_in(path.stem, x) for x in rule['name_terms']):
        return False
    if 'path_terms' in rule and not any(phrase_in(part, term) for part in path.parts[:-1] for term in rule['path_terms']):
        return False
    if 'extensions' in rule and path.suffix.casefold() not in [x.casefold() for x in rule['extensions']]:
        return False
    return True


def classify(source_path: str, kind: str, rules: list[dict]) -> dict:
    row = dict(source_path=source_path, status='review', destination='', rule_ids='', reason='')
    try:
        path = relative_path(source_path)
    except ValueError:
        row['reason'] = 'invalid_path'
        return row
    row['source_path'] = str(path)
    if kind != 'file':
        row['reason'] = 'nonregular_entry'
        return row
    selected = [r for r in rules if matches(path, r)]
    row['rule_ids'] = ';'.join(sorted(r['id'] for r in selected))
    targets = {str(relative_path(r['target'])) for r in selected}
    if not targets:
        row['reason'] = 'no_signal'
    elif len(targets) > 1:
        row['reason'] = 'ambiguous_rules'
    else:
        row.update(status='routed', destination=str(PurePosixPath(next(iter(targets))) / path.name), reason='unique_target')
    return row


def plan(rows: list[dict], rules: list[dict]) -> list[dict]:
    results = [classify(row['source_path'], row['kind'], rules) for row in rows]
    sources = Counter(r['source_path'].casefold() for r in results)
    destinations = Counter(r['destination'].casefold() for r in results if r['destination'])
    for row in results:
        if sources[row['source_path'].casefold()] > 1:
            row.update(status='review', destination='', reason='duplicate_source')
        elif row['destination'] and destinations[row['destination'].casefold()] > 1:
            row.update(status='review', destination='', reason='destination_collision')
    return results


def inventory(root: Path) -> list[dict]:
    """Read names only; record but never descend into symlinks."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('scan root must be a real directory, not a symlink')
    root = root.resolve()
    rows = []
    def fail(error):
        raise error
    for directory, folders, files in os.walk(root, followlinks=False, onerror=fail):
        base = Path(directory)
        for name in sorted(folders[:]):
            path = base / name
            if path.is_symlink():
                rows.append(dict(source_path=path.relative_to(root).as_posix(), kind='symlink'))
                folders.remove(name)
        for name in sorted(files):
            path = base / name
            kind = 'symlink' if path.is_symlink() else 'file' if path.is_file() else 'other'
            rows.append(dict(source_path=path.relative_to(root).as_posix(), kind=kind))
    return sorted(rows, key=lambda row: row['source_path'])


def read_catalog(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != CATALOG_FIELDS:
            raise ValueError('catalog header must be source_path,kind')
        rows = list(reader)
    if any(set(row) != set(CATALOG_FIELDS) or any(value is None for value in row.values()) for row in rows):
        raise ValueError('catalog contains a malformed row')
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    # Exclusive creation refuses overwrites, including symlink output paths.
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def portable_copy_path(text: str) -> str:
    path = relative_path(text)
    devices = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    for part in path.parts:
        if re.search(r'[<>"|?*]', part) or part.endswith((' ', '.')) or part.split('.')[0].upper() in devices:
            raise ValueError('copy path contains a nonportable component')
    return str(path)


def export_copy(rows: list[dict]) -> tuple[list[dict], int]:
    """Validate a reviewed proposal for the independent PowerShell copy stage."""
    result = []
    reviewed = 0
    source_keys, destination_keys = set(), set()
    for row in rows:
        if set(row) != set(PLAN_FIELDS) or any(not isinstance(v, str) for v in row.values()):
            raise ValueError('malformed plan row')
        if row['status'] == 'review':
            reviewed += 1
            continue
        if row['status'] != 'routed' or not row['rule_ids'] or row['reason'] != 'unique_target':
            raise ValueError('invalid routed row')
        source = portable_copy_path(row['source_path'])
        destination = portable_copy_path(row['destination'])
        if source.casefold() in source_keys or destination.casefold() in destination_keys:
            raise ValueError('duplicate source or destination in copy export')
        source_keys.add(source.casefold())
        destination_keys.add(destination.casefold())
        result.append({'SourceRelativePath': source, 'DestinationRelativePath': destination})
    return result, reviewed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('scan', help='inventory relative paths without reading document content')
    scan.add_argument('root', type=Path)
    scan.add_argument('--output', required=True, type=Path)
    build = sub.add_parser('plan', help='propose destinations; never execute them')
    build.add_argument('catalog', type=Path)
    build.add_argument('--rules', required=True, type=Path)
    build.add_argument('--output', required=True, type=Path)
    export = sub.add_parser('export-copy', help='export routed rows for a separate copy preview')
    export.add_argument('plan', type=Path)
    export.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'scan':
            rows = inventory(args.root)
            write_csv(args.output, CATALOG_FIELDS, rows)
        elif args.command == 'plan':
            rules = validate_rules(json.loads(args.rules.read_text(encoding='utf-8')))
            rows = plan(read_catalog(args.catalog), rules)
            write_csv(args.output, PLAN_FIELDS, rows)
        else:
            with args.plan.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != PLAN_FIELDS:
                    raise ValueError('unexpected plan header')
                rows, excluded = export_copy(list(reader))
            write_csv(args.output, ['SourceRelativePath', 'DestinationRelativePath'], rows)
            print(f'Excluded {excluded} review rows; no source files were copied.')
        print(f'Wrote {len(rows)} rows to {args.output}')
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f'Error: {error}\n')

if __name__ == '__main__':
    main()
