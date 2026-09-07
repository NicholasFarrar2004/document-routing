"""Exercise the copier using new fictional files only; Python 3.10+ and pwsh required."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pwsh', default='pwsh')
parser.add_argument('--work-root', type=Path, required=True, help='existing parent for a new isolated test directory')
args = parser.parse_args()
script = Path(__file__).resolve().parent / 'Copy-WorkshopFiles.ps1'
work = Path(tempfile.mkdtemp(prefix='workshop-test-', dir=args.work_root)).resolve()
source = work / 'source'
source.mkdir()
checks = []

def mapping(name, rows):
    path = work / (name + '.csv')
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['SourceRelativePath', 'DestinationRelativePath'])
        writer.writerows(rows)
    return path

def run(catalog, destination, execute=False, extra=(), expected=0):
    command = [args.pwsh, '-NoProfile', '-NonInteractive', '-File', str(script),
               '-CatalogPath', str(catalog), '-SourceRoot', str(source),
               '-DestinationRoot', str(destination), '-AsJson', *extra]
    if execute:
        command.append('-Execute')
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != expected:
        raise AssertionError(f'Unexpected exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip().startswith('[') else None

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

names = ['bench (draft) [A] & notes.txt', 'reading, list.txt', 'trailing space ']
if os.name != 'nt':
    names.append('poster "draft".txt')
for i, name in enumerate(names):
    (source / name).write_text(f'Fictional workshop item {i}\n')
rows = [(name, 'display/' + name) for name in names]
catalog = mapping('quoted', rows)
destination = work / 'destination'
before = {str(p.relative_to(work)): digest(p) for p in work.rglob('*') if p.is_file()}
preview = run(catalog, destination)
assert all(row['Action'] == 'WOULD_COPY' for row in preview)
assert not destination.exists()
assert before == {str(p.relative_to(work)): digest(p) for p in work.rglob('*') if p.is_file()}
checks.append('Preview is read-only; quoted CSV, punctuation and trailing spaces preserved')

log = work / 'copy-log.csv'
result = run(catalog, destination, True, extra=('-LogPath', str(log)))
assert all(row['Action'] == 'COPIED_VERIFIED' for row in result)
assert all(digest(source / a) == digest(destination / b) for a, b in rows)
with log.open(newline='') as stream:
    logged = list(csv.DictReader(stream))
assert sorted(row['SourceRelativePath'] for row in logged) == sorted(names)
checks.append('Explicit execute copies with SHA-256 verification and round-trippable CSV logging')
result = run(catalog, destination, True)
assert all(row['Action'] == 'SKIP_IDENTICAL' for row in result)
checks.append('Rerun identifies equal content by SHA-256')

victim = destination / rows[0][1]
original = victim.read_bytes()
victim.write_bytes(b'x' * len(original))
conflict_before = victim.read_bytes()
result = run(catalog, destination, True, expected=2)
assert result[0]['Action'] == 'CONFLICT' and victim.read_bytes() == conflict_before
victim.write_bytes(b'longer unrelated fictional file')
conflict_before = victim.read_bytes()
result = run(catalog, destination, True, expected=2)
assert result[0]['Action'] == 'CONFLICT' and victim.read_bytes() == conflict_before
checks.append('Same-size different-content and different-size conflicts never overwrite')

assert run(mapping('missing', [('absent.txt','missing.txt')]), work / 'missing', expected=2)[0]['Action'] == 'MISSING_SOURCE'
assert not (work / 'missing').exists()
checks.append('Missing sources are reported without creating destination folders')

for label, bad_rows in [('traversal', [('bench (draft) [A] & notes.txt','../escape.txt')]),
                        ('absolute', [('bench (draft) [A] & notes.txt', str(work / 'escape.txt'))]),
                        ('duplicate', [(names[0],'same.txt'),(names[1],'SAME.txt')]),
                        ('parent-collision', [(names[0],'same'),(names[1],'same/child.txt')]),
                        ('stream', [(names[0],'name:stream')])]:
    target = work / ('invalid-' + label)
    run(mapping(label,bad_rows), target, True, expected=1)
    assert not target.exists()
checks.append('Traversal, absolute paths, duplicates, file/parent collisions and stream syntax rejected before writes')

bad_header = work / 'bad-header.csv'
bad_header.write_text('Wrong,Header\none,two\n')
run(bad_header, work / 'bad-header-target', True, expected=1)
assert not (work / 'bad-header-target').exists()
checks.append('Invalid CSV headers rejected')

long_relative = '/'.join(['long-workshop-folder-' + str(i) + '-' + 'a'*24 for i in range(7)]) + '/notes.txt'
long_source = source / long_relative
long_source.parent.mkdir(parents=True)
long_source.write_text('Fictional long-path workshop note\n')
assert len(str(long_source)) > 260
long_dest = work / 'long-destination'
result = run(mapping('long', [(long_relative,long_relative)]),long_dest,True)
assert result[0]['Action']=='COPIED_VERIFIED' and digest(long_source)==digest(long_dest/long_relative)
checks.append('Actual path longer than 260 characters copied and hash-verified on this host')

many=[]
for i in range(32):
    name=f'batch-{i}.txt';(source/name).write_text(f'Fictional batch note {i}\n');many.append((name,'shared/'+name))
parallel = run(mapping('parallel',many),work/'parallel',True,extra=('-ThrottleLimit','8'))
assert len(parallel)==32 and all(row['Action']=='COPIED_VERIFIED' for row in parallel)
checks.append('Eight-worker shared-directory copy: all 32 files hash-verified')

if os.name != 'nt':
    (source/'linked').symlink_to(work, target_is_directory=True)
    run(mapping('symlink',[('linked/outside.txt','outside.txt')]),work/'symlink-destination',True,expected=1)
    assert not (work/'symlink-destination').exists()
    checks.append('Symbolic-link ancestor refused')

run(catalog,source,True,expected=1)
checks.append('Overlapping roots refused')
log_before=log.read_bytes()
run(catalog,work/'log-existing-target',True,extra=('-LogPath',str(log)),expected=1)
assert log.read_bytes()==log_before and not (work/'log-existing-target').exists()
checks.append('Existing log cannot be overwritten')

root_log = work / 'destination-as-log'
run(catalog, root_log, True, extra=('-LogPath', str(root_log)), expected=1)
assert not root_log.exists()
checks.append('Log path equal to destination root refused before writes')

case_overlap = source.parent / (source.name.upper()) / 'nested'
run(catalog, case_overlap, True, expected=1)
assert not case_overlap.exists()
checks.append('Case-variant overlapping roots conservatively refused')


report={'passed':len(checks),'checks':checks,'host':os.name,
        'limits':['Windows extended-path and UNC branches require Windows validation.',
                  'No network shares or concurrent hostile path changes tested.']}
(work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
print('Fictional test files retained for inspection in the generated work directory.')
