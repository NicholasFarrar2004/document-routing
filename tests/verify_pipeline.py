"""Verify the complete fictional classification and copy workflow in temporary folders."""
import argparse, csv, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pwsh', default=shutil.which('pwsh'), help='PowerShell 7.2+ executable')
args = parser.parse_args()
if not args.pwsh:
    parser.error('PowerShell is required; pass --pwsh /path/to/pwsh')
candidate = Path(__file__).resolve().parents[1]
pwsh = Path(args.pwsh).resolve()
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', POWERSHELL_TELEMETRY_OPTOUT='1', DOTNET_CLI_TELEMETRY_OPTOUT='1')
env.pop('PYTHONPATH', None)

def run(args, expected=0):
    p = subprocess.run([str(a) for a in args], text=True, capture_output=True, env=env)
    if p.returncode != expected:
        raise AssertionError(f'Unexpected exit {p.returncode}: {p.stderr[:800]}')
    return p.stdout

def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

with tempfile.TemporaryDirectory(prefix='fictional-exhibit-integration-') as temporary:
    work = Path(temporary).resolve()
    source, destination = work/'source', work/'destination'
    names = ['incoming/ExhibitLabel.txt', 'incoming/LightingNotes.txt', 'incoming/label-lighting.txt', 'incoming/mystery.txt', 'sketches/Atrium.txt']
    for i, name in enumerate(names):
        p = source/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f'Independently invented exhibit document {i}.\n')
    before = hashes(source)
    router = candidate/'python/router.py'
    run([sys.executable, '-B', router, 'scan', source, '--output', work/'catalog.csv'])
    run([sys.executable, '-B', router, 'plan', work/'catalog.csv', '--rules', candidate/'python/examples/rules.json', '--output', work/'plan.csv'])
    run([sys.executable, '-B', router, 'export-copy', work/'plan.csv', '--output', work/'copy.csv'])
    with (work/'copy.csv').open(newline='') as f: mappings = list(csv.DictReader(f))
    assert len(mappings) == 3
    command = [pwsh, '-NoLogo', '-NoProfile', '-File', candidate/'powershell/Copy-WorkshopFiles.ps1', '-CatalogPath', work/'copy.csv', '-SourceRoot', source, '-DestinationRoot', destination, '-AsJson']
    preview = json.loads(run(command))
    assert len(preview) == 3 and all(x['Action']=='WOULD_COPY' for x in preview)
    assert not destination.exists() and hashes(source)==before
    copied = json.loads(run(command+['-Execute']))
    assert len(copied) == 3 and all(x['Action']=='COPIED_VERIFIED' for x in copied)
    for row in mappings:
        assert (source/row['SourceRelativePath']).read_bytes() == (destination/row['DestinationRelativePath']).read_bytes()
    second = json.loads(run(command+['-Execute']))
    assert all(x['Action']=='SKIP_IDENTICAL' for x in second)
    changed = destination/mappings[0]['DestinationRelativePath']
    changed.write_text('Fictional destination conflict preserved.\n')
    conflict = json.loads(run(command+['-Execute'], expected=2))
    assert sum(x['Action']=='CONFLICT' for x in conflict) == 1
    assert changed.read_text() == 'Fictional destination conflict preserved.\n'
    assert hashes(source)==before
    assert len(hashes(destination)) == 3
    print(json.dumps({'status':'passed','fictional_inputs':5,'copy_rows':3,'review_rows_excluded':2,'preview_no_writes':True,'copies_hash_verified':3,'rerun_identical_skips':3,'conflict_preserved':True,'sources_unchanged':True}, indent=2))
