import sys
sys.dont_write_bytecode = True
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router import (normalized_words, relative_path, validate_rules, classify, plan,
                    inventory, read_catalog, write_csv, export_copy, CATALOG_FIELDS)
ROOT = Path(__file__).resolve().parents[1]

class RulesTests(unittest.TestCase):
    def setUp(self):
        self.rules = validate_rules(json.loads((ROOT/'examples/rules.json').read_text()))
    def test_normalize_camel_case_and_separators(self):
        self.assertEqual(normalized_words('ExhibitLabel__north-wing'), 'exhibit label north wing')
    def test_windows_slashes_and_uppercase_extension(self):
        row=classify(r'incoming\ExhibitLabel.TXT','file',self.rules)
        self.assertEqual(row['destination'],'Exhibits/Labels/ExhibitLabel.TXT')
    def test_extension_is_required_with_name_selector(self):
        self.assertEqual(classify('Label.pdf','file',self.rules)['reason'],'no_signal')
    def test_partial_word_does_not_match(self):
        self.assertEqual(classify('Labels.txt','file',self.rules)['reason'],'no_signal')
    def test_literal_term_not_regex(self):
        rules=validate_rules({'rules':[{'id':'literal','target':'Shelf','name_terms':['a+b']}]})
        self.assertEqual(classify('aaab.txt','file',rules)['reason'],'no_signal')
        self.assertEqual(classify('a+b.txt','file',rules)['status'],'routed')
    def test_ambiguity_never_chooses_a_priority(self):
        row=classify('label-lighting.txt','file',self.rules)
        self.assertEqual((row['reason'],row['destination']),('ambiguous_rules',''))
        self.assertEqual(row['rule_ids'],'label-text;lighting-notes')
    def test_same_target_multiple_rules_is_unambiguous(self):
        rules=validate_rules({'rules':[{'id':'a','target':'Shelf','name_terms':['label']},{'id':'b','target':'Shelf','extensions':['.txt']}]})
        row=classify('label.txt','file',rules)
        self.assertEqual((row['status'],row['rule_ids']),('routed','a;b'))
    def test_directory_signal_not_basename(self):
        self.assertEqual(classify('sketches/north.txt','file',self.rules)['status'],'routed')
        self.assertEqual(classify('sketches.txt','file',self.rules)['reason'],'no_signal')
    def test_invalid_paths(self):
        for path in ['../label.txt','/label.txt',r'C:\label.txt',r'C:label.txt',r'\\server\label.txt','a//label.txt','a/./label.txt','a/../label.txt','a\x00.txt']:
            with self.subTest(path=path):
                self.assertEqual(classify(path,'file',self.rules)['reason'],'invalid_path')
    def test_special_characters_and_long_path_survive_planning(self):
        path='/'.join(['long-directory']*22)+ '/Label (north) [v2] & "copy".txt'
        row=classify(path,'file',self.rules)
        self.assertEqual(row['status'],'routed')
        self.assertTrue(len(row['source_path'])>260)
        self.assertTrue(row['destination'].endswith('Label (north) [v2] & "copy".txt'))
    def test_nonfiles_deferred(self):
        self.assertEqual(classify('Label.txt','symlink',self.rules)['reason'],'nonregular_entry')
    def test_duplicate_source_normalized(self):
        result=plan([{'source_path':'a/Label.txt','kind':'file'},{'source_path':r'a\Label.txt','kind':'file'}],self.rules)
        self.assertTrue(all(r['reason']=='duplicate_source' and not r['destination'] for r in result))
    def test_casefold_destination_collision(self):
        result=plan([{'source_path':'a/Label.txt','kind':'file'},{'source_path':'b/label.txt','kind':'file'}],self.rules)
        self.assertTrue(all(r['reason']=='destination_collision' and not r['destination'] for r in result))
    def test_bad_rules_rejected(self):
        for rule in [{'id':'a','target':'../Shelf','name_terms':['label']},
                     {'id':'a','target':'Shelf'}, {'id':'a','target':'Shelf','name_terms':[]},
                     {'id':'a','target':'Shelf','name_terms':['!']},
                     {'id':'a','target':'Shelf','extensions':['txt']},
                     {'id':'a','target':'Shelf','hidden_priority':4}]:
            with self.subTest(rule=rule), self.assertRaises(ValueError): validate_rules({'rules':[rule]})
    def test_duplicate_rule_ids(self):
        with self.assertRaises(ValueError):validate_rules({'rules':[self.rules[0],self.rules[0]]})

class FilesTests(unittest.TestCase):
    def test_csv_roundtrip_quotes_and_commas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.csv'; rows=[{'source_path':'Shelf/Label, "blue".txt','kind':'file'}]
            write_csv(path,CATALOG_FIELDS,rows)
            self.assertEqual(read_catalog(path),rows)
            with self.assertRaises(FileExistsError):write_csv(path,CATALOG_FIELDS,[])
            self.assertEqual(read_catalog(path),rows)
    def test_malformed_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.csv';path.write_text('source_path,kind\nlabel.txt\n')
            with self.assertRaises(ValueError):read_catalog(path)
    def test_scan_does_not_follow_symlinks_or_change_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir();outside=Path(tmp)/'outside';outside.mkdir()
            (outside/'hidden.txt').write_text('outside')
            original=root/'Label.txt';original.write_bytes(b'unchanged')
            try:(root/'linked').symlink_to(outside,target_is_directory=True)
            except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
            rows=inventory(root)
            self.assertEqual(rows,[{'source_path':'Label.txt','kind':'file'},{'source_path':'linked','kind':'symlink'}])
            self.assertEqual(original.read_bytes(),b'unchanged')
    def test_cli_demo_and_export(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'demo.py')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('3 routed, 2 review.',result.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'copy.csv'
            result=subprocess.run([sys.executable,'-B',str(ROOT/'router.py'),'export-copy',str(ROOT/'examples/expected-plan.csv'),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('Excluded 2 review rows',result.stdout)
            with out.open(newline='') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),3)
            self.assertEqual(set(rows[0]),{'SourceRelativePath','DestinationRelativePath'})

class CopyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.rules=validate_rules(json.loads((ROOT/'examples/rules.json').read_text()))
        self.good=classify('incoming/Label.txt','file',self.rules)
    def test_mixed_review_and_routed(self):
        output, excluded=export_copy([self.good,classify('unknown.txt','file',self.rules)])
        self.assertEqual(excluded,1)
        self.assertEqual(output,[{'SourceRelativePath':'incoming/Label.txt','DestinationRelativePath':'Exhibits/Labels/Label.txt'}])
    def test_duplicate_export_refused(self):
        with self.assertRaises(ValueError):export_copy([self.good,self.good])
    def test_unsafe_destination_and_source_refused(self):
        for key in ['destination','source_path']:
            for path in ['../escape.txt',r'C:\escape.txt','Shelf/CON.txt','Shelf/a?.txt','Shelf/file.','Shelf/file ']:
                bad=dict(self.good);bad[key]=path
                with self.subTest(key=key,path=path), self.assertRaises(ValueError):export_copy([bad])
    def test_malformed_route_refused(self):
        for key,value in [('status','unknown'),('rule_ids',''),('reason','no_signal'),('destination','')]:
            bad=dict(self.good);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):export_copy([bad])

if __name__ == '__main__':unittest.main()
