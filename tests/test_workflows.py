"""Execute realistic converted workflows with local stubs, never a model download."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converter import convert, convert_file
from shellsyntax import lex
from test_converter import ENGINES, TEST_ROOT, run_ps


FIXTURES = Path(__file__).parent / 'fixtures'


class WorkflowTranslationTests(unittest.TestCase):
    def test_nested_expansions_stay_one_word(self):
        tokens = lex('cd "$(dirname "$0")/.."\nCACHE="${CACHE:-${HF_HOME:-$HOME/.cache}/hub}"')
        self.assertEqual(len([t for t in tokens if t.kind == 'word']), 3)
        self.assertEqual(tokens[1].raw, '"$(dirname "$0")/.."')

    def test_supported_structures(self):
        sources = [
            'set -euo pipefail\nset -a\nset +a\nset +o pipefail',
            'while ! "$PY" job.py; do echo "[$(date -Is)] retry"; sleep 0; done',
            'if [ -f file ]; then echo yes; elif test -n "x"; then echo next; else echo no; fi',
            'for x in a "b c"; do if test "$x" = a; then echo A; fi; done',
            'until test -f marker; do touch marker; done',
            'CACHE="${CACHE:-${HF_HOME:-$HOME/.cache}/hub}"',
            ': "${REQUIRED:?set REQUIRED first}"',
            'DIR="$(find "$CACHE/snapshots" -mindepth 1 -maxdepth 1 -type d | head -n 1)"',
            "printf 'completed=%s\\nmodel=%s\\n' \"$(date -Is)\" \"$MODEL\" > done.txt",
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertFalse(convert(source).errors)

    def test_malformed_blocks_and_nested_unsupported_are_guarded(self):
        for source in ['done', 'if true; echo x; fi', 'while true; do echo x',
                       'if true; then chmod +x x; fi', 'X="$(echo $(chmod +x x))"',
                       'find . -delete', "printf '%q' data", 'bash -c "echo x"']:
            with self.subTest(source=source):
                self.assertTrue(convert(source).errors)

    def test_original_pipeline_and_child_convert_without_errors(self):
        result = convert_file(FIXTURES / 'scripts' / 'qwen35_08b_pipeline.sh')
        self.assertFalse(result.errors, result.errors)
        self.assertIn('jevforge.train', result.script)
        self.assertIn('B2PSScripts[', result.script)
        self.assertNotIn("throw 'Conversion incomplete", result.script)

    def test_file_context_is_required_for_shell_dependencies(self):
        self.assertTrue(convert('bash child.sh').errors)
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            folder = Path(folder)
            main = folder / 'main.sh'
            main.write_text('bash missing.sh', encoding='utf-8')
            self.assertTrue(convert_file(main).errors)
            main.write_text('bash main.sh', encoding='utf-8')
            self.assertTrue(convert_file(main).errors)
            child = folder / 'child.sh'
            child.write_text('touch before\nchmod +x x', encoding='utf-8')
            main.write_text('bash child.sh', encoding='utf-8')
            result = convert_file(main)
            self.assertTrue(result.errors)
            self.assertIn('child.sh:L2', result.errors[0].message)


@unittest.skipUnless(ENGINES, 'PowerShell required')
class ExtendedExecutionTests(unittest.TestCase):
    def each_engine(self, source, verify, after=''):
        for engine in ENGINES:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                verify(run_ps(source, engine, directory, after), Path(directory))
    def test_nested_defaults_and_lazy_fallbacks(self):
        source = '''set -u
B2PS_WF_ROOT=base
B2PS_WF_EMPTY=""
echo "${B2PS_WF_MISSING:-${B2PS_WF_ROOT:-missing}/hub}"
echo "${B2PS_WF_EMPTY-default}|${B2PS_WF_EMPTY:-default}"
echo "${B2PS_WF_ROOT:+present}|${B2PS_WF_MISSING:+absent}"
echo "${B2PS_WF_ROOT:-$(touch should-not-exist)}"
: "${B2PS_WF_NEW:=assigned}"
echo "$B2PS_WF_NEW"
'''
        def verify(p, d):
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(b'base/hub', p.stdout)
            self.assertIn(b'|default', p.stdout)
            self.assertIn(b'present|', p.stdout)
            self.assertIn(b'assigned', p.stdout)
            self.assertFalse((d / 'should-not-exist').exists())
        self.each_engine(source, verify)

    def test_required_parameter_fails_before_following_steps(self):
        self.each_engine(': "${B2PS_WF_REQUIRED:?please set the model}"\ntouch unreachable',
                         lambda p, d: (self.assertNotEqual(p.returncode, 0), self.assertFalse((d / 'unreachable').exists())))

    def test_nounset_is_fatal_without_errexit(self):
        self.each_engine('set -u\necho "$B2PS_WF_UNDEFINED"\ntouch unreachable',
                         lambda p, d: (self.assertNotEqual(p.returncode, 0), self.assertFalse((d / 'unreachable').exists())))

    def test_find_depth_type_and_name(self):
        source = '''set -eu
mkdir -p tree/one/nested tree/two
touch tree/a.txt tree/one/b.txt tree/one/nested/c.txt
find tree -mindepth 1 -maxdepth 2 -type f -name '*.txt' | wc -l
DIR="$(find tree -mindepth 1 -maxdepth 1 -type d | head -n 1)"
echo "$DIR"
'''
        self.each_engine(source, lambda p, d: (self.assertEqual(p.returncode, 0, p.stderr),
                         self.assertIn(b'2', p.stdout), self.assertIn(b'one', p.stdout),
                         self.assertNotIn(b'nested', p.stdout)))

    def test_capture_restores_directory_and_variables(self):
        source = '''set -eu
mkdir -p nested
NAME=outer
VALUE="$(cd nested; NAME=inner; printf '%s\\n' "$NAME" 'second')"
echo "$NAME"
printf '%s' "$VALUE" > captured.txt
echo "$(dirname "$0")"
'''
        self.each_engine(source, lambda p, d: (
            self.assertEqual(p.returncode, 0, p.stderr),
            self.assertIn(b'outer', p.stdout),
            self.assertEqual((d / 'captured.txt').read_bytes(), b'inner\nsecond'),
            self.assertFalse((d / 'nested' / 'captured.txt').exists())))

    def test_assignment_preserves_substitution_exit_code(self):
        self.each_engine('VALUE="$(python -c \'raise SystemExit(9)\')"\necho "$?"',
                         lambda p, d: self.assertIn(b'9', p.stdout))
        self.each_engine('set -e\nVALUE="$(false)"\ntouch unreachable',
                         lambda p, d: (self.assertNotEqual(p.returncode, 0), self.assertFalse((d / 'unreachable').exists())))

    def test_if_for_until_and_nested_conditions(self):
        source = '''set -e
for value in a "b c"; do
  if [ "$value" = a ]; then
    echo FIRST
  elif test "$value" = "b c"; then
    echo SECOND
  else
    echo UNREACHABLE
  fi
done
until [ -f marker ]; do touch marker; done
while false; do echo UNREACHABLE; done
if false; then echo UNREACHABLE; fi
echo DONE
'''
        self.each_engine(source, lambda p, d: (
            self.assertEqual(p.returncode, 0, p.stderr), self.assertIn(b'FIRST', p.stdout),
            self.assertIn(b'SECOND', p.stdout), self.assertIn(b'DONE', p.stdout),
            self.assertNotIn(b'UNREACHABLE', p.stdout), self.assertTrue((d / 'marker').exists())))

    def test_pipefail_and_grep_status(self):
        source = '''set -euo pipefail
printf '%s\\n' apple > lines.txt
cat lines.txt | grep -F missing | head -n 1 && echo UNREACHABLE || echo PIPE_FAILED
grep -F missing lines.txt || echo GREP_FAILED
set +o pipefail
cat lines.txt | grep -F missing | head -n 1 && echo LAST_SUCCEEDED
'''
        self.each_engine(source, lambda p, d: (
            self.assertEqual(p.returncode, 0, p.stderr), self.assertIn(b'PIPE_FAILED', p.stdout),
            self.assertIn(b'GREP_FAILED', p.stdout), self.assertIn(b'LAST_SUCCEEDED', p.stdout),
            self.assertNotIn(b'UNREACHABLE', p.stdout)))

    def test_printf_formats_and_exact_file_bytes(self):
        source = "printf 'name=%s\\ncount=%d\\npercent=%%\\n' 'a b' 7 > result.txt\nprintf '%s' 'tail' >> result.txt"
        self.each_engine(source, lambda p, d: (
            self.assertEqual(p.returncode, 0, p.stderr),
            self.assertEqual((d / 'result.txt').read_bytes(), b'name=a b\ncount=7\npercent=%\ntail')))

    def test_env_reader_never_executes_shell_operators(self):
        source = "printf '%s\\n' 'B2PS_WF_ENV=ok; touch injected' > .env\nset -ea\n. ./.env\necho UNREACHABLE"
        self.each_engine(source, lambda p, d: (
            self.assertNotEqual(p.returncode, 0), self.assertFalse((d / 'injected').exists()),
            self.assertNotIn(b'UNREACHABLE', p.stdout)))

    def test_source_shares_locals_and_child_bash_isolates_them(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
                folder = Path(folder)
                (folder / 'shared.sh').write_text('SHARED=source\nprintf \'%s\\n\' "$0" "${BASH_SOURCE[0]}" > sources.txt\n', encoding='utf-8')
                (folder / 'child.sh').write_text('SHARED=child\nexport B2PS_WF_CHILD=child\nmkdir nested\ncd nested\necho "$1"', encoding='utf-8')
                main = folder / 'main.sh'
                main.write_text('set -eu\n. shared.sh\nbash child.sh "child arg"\necho "$SHARED"\nprintf \'%s\\n\' "${B2PS_WF_CHILD:-restored}" > result.txt', encoding='utf-8')
                script = folder / 'main.ps1'
                result = convert_file(main)
                self.assertFalse(result.errors)
                script.write_text(result.script, encoding='utf-8-sig')
                p = subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)], cwd=folder, capture_output=True, timeout=30)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(b'child arg', p.stdout)
                self.assertIn(b'source', p.stdout)
                self.assertEqual((folder / 'result.txt').read_bytes(), b'restored\n')
                self.assertEqual((folder / 'sources.txt').read_text(encoding='utf-8').splitlines(), [str(main), str(folder / 'shared.sh')])

    def test_actual_pipeline_with_mocked_download_train_predict_evaluate(self):
        for engine in ENGINES:
            for with_env in (False, True):
                with self.subTest(engine=engine, with_env=with_env), tempfile.TemporaryDirectory(prefix='workflow space ', dir=TEST_ROOT) as directory:
                    root = Path(directory)
                    scripts = root / 'scripts'
                    scripts.mkdir()
                    pipeline = scripts / 'qwen35_08b_pipeline.sh'
                    # Keep the supplied workflow intact, shortening only the retry delay.
                    pipeline.write_text((FIXTURES / 'scripts' / pipeline.name).read_text(encoding='utf-8').replace('sleep 60', 'sleep 0'), encoding='utf-8')
                    (scripts / 'qwen35_08b.sh').write_bytes((FIXTURES / 'scripts' / 'qwen35_08b.sh').read_bytes())
                    (scripts / 'fetch_hf_model.py').write_text('''from pathlib import Path
import sys
p=Path('attempts.txt')
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
if n < 3: raise SystemExit(7)
cache=Path(sys.argv[sys.argv.index('--cache-dir')+1])
(cache/'models--Qwen--Qwen3.5-0.8B'/'snapshots'/'snapshot space').mkdir(parents=True,exist_ok=True)
''', encoding='utf-8')
                    package = root / 'jevforge'
                    package.mkdir()
                    (package / '__init__.py').write_text('', encoding='utf-8')
                    stub = '''import json,os,sys
from pathlib import Path
with Path('calls.jsonl').open('a',encoding='utf-8') as f:
 f.write(json.dumps({'module':__name__,'argv':sys.argv,'model':os.environ.get('QWEN35_MODEL_DIR'),'run':os.environ.get('RUN_DIR'),'token':os.environ.get('B2PS_WF_TOKEN')})+'\\n')
if '--output-dir' in sys.argv: Path(sys.argv[sys.argv.index('--output-dir')+1]).mkdir(parents=True,exist_ok=True)
'''
                    for module in ('train', 'predict', 'evaluate'):
                        (package / (module + '.py')).write_text(stub, encoding='utf-8')
                    cache = root / ('env cache' if with_env else 'cache space')
                    if with_env:
                        (root / '.env').write_text('CACHE_DIR="' + cache.as_posix() + '"\nB2PS_WF_TOKEN=from_env\n', encoding='utf-8')
                    env = os.environ.copy()
                    for name in ('RUN_DIR', 'PRED_DIR', 'REPORT_DIR', 'HF_HOME', 'STEPS', 'B2PS_WF_TOKEN'):
                        env.pop(name, None)
                    env['PY'] = sys.executable
                    env['CACHE_DIR'] = str(root / 'cache space')
                    result = convert_file(pipeline)
                    self.assertFalse(result.errors, result.errors)
                    output = root / 'converted.ps1'
                    output.write_text(result.script, encoding='utf-8-sig')
                    p = subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(output)], cwd=TEST_ROOT, env=env, capture_output=True, timeout=30)
                    self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                    self.assertEqual((root / 'attempts.txt').read_text(), '3')
                    self.assertEqual(p.stdout.count(b'retrying'), 2)
                    calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
                    self.assertEqual(len(calls), 3)
                    self.assertEqual([Path(c['argv'][0]).stem for c in calls], ['train', 'predict', 'evaluate'])
                    model = cache / 'models--Qwen--Qwen3.5-0.8B' / 'snapshots' / 'snapshot space'
                    for call in calls:
                        self.assertEqual(Path(call['model']), model)
                        self.assertEqual(call['run'], 'runs/qwen35_08b_same_data_v1')
                        self.assertEqual(call['token'], 'from_env' if with_env else None)
                    self.assertIn('qwen35_08b=artifacts/qwen35_08b_same_data_v1', calls[2]['argv'])
                    completion = (root / 'artifacts' / 'qwen35_08b.done').read_bytes()
                    self.assertRegex(completion, rb'^completed_at=\d{4}-\d{2}-\d{2}T')
                    self.assertIn(('model=' + str(model)).encode(), completion)
                    self.assertTrue(completion.endswith(b'report_dir=artifacts/report_qwen35_08b_same_data_v1\n'))


if __name__ == '__main__':
    unittest.main()
