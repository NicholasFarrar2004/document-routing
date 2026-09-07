"""Run an entirely invented exhibit example in a temporary folder."""
import sys
sys.dont_write_bytecode = True
import json
import tempfile
from pathlib import Path
from router import inventory, plan, validate_rules, write_csv, PLAN_FIELDS

ROOT = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='exhibit-routing-demo-') as temporary:
    root = Path(temporary) / 'source'
    for name in ['incoming/ExhibitLabel.txt', 'incoming/LightingNotes.txt',
                 'incoming/label-lighting.txt', 'incoming/mystery.txt', 'sketches/Atrium.txt']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('Invented exhibit example. No document content is read by the router.\n')
    rules = validate_rules(json.loads((ROOT / 'examples/rules.json').read_text()))
    rows = plan(inventory(root), rules)
    output = Path(temporary) / 'plan.csv'
    write_csv(output, PLAN_FIELDS, rows)
    expected = (ROOT / 'examples/expected-plan.csv').read_text()
    actual = output.read_text()
    if actual != expected:
        raise SystemExit('Demo differs from the documented expected output')
    print(actual, end='')
    print('3 routed, 2 review. No source files changed; temporary example cleaned up on exit.')
