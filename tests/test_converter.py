from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converter import convert


PS51 = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
PS7 = shutil.which('pwsh')
ENGINES = [str(p) for p in [PS51, PS7] if p and Path(p).is_file()]
TEST_ROOT = Path(__file__).resolve().parents[1] / '.test-work'
TEST_ROOT.mkdir(exist_ok=True)


def run_ps(source, engine, directory, after=''):
    result = convert(source)
    if result.errors:
        raise AssertionError(result.errors)
    script = Path(directory) / 'test.ps1'
    script.write_text(result.script.replace('# B2PS final status', after + '\n# B2PS final status'), encoding='utf-8-sig')
    return subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                          cwd=directory, capture_output=True, timeout=30)


class TranslationTests(unittest.TestCase):
    def test_supported_examples(self):
        sources = ['export KEY="a b"\necho "$KEY"', 'mkdir -p "a b" && cd "a b"',
                   'git status && echo ok || echo failed', 'MODE=x python -V',
                   'rm -rf "build output"', 'cp -r src dest', 'mv old new',
                   'cat a.txt | grep -F word | head -n 2 | wc -l',
                   'touch a b', '[ -f a ] && echo exists', '[ "x" = "x" ]',
                   'unset KEY', 'set -eu\nset +e', 'curl -L -o file.zip "https://example.com/a?x=1&y=2"',
                   'printf \'%s\\n\' "你好" > config.txt', 'echo x \\\n y', 'echo "a\nb"',
                   'git commit -m "多行\n消息"', "mkdir '-p' foo", 'false ||\n echo ok']
        for source in sources:
            with self.subTest(source=source):
                self.assertFalse(convert(source).errors)

    def test_unsupported_input_is_guarded(self):
        sources = ['sudo apt install x', 'if test -f a; then echo ok',
                   'for x in a b; do echo "$x"', 'cat <<EOF\nx\n',
                   'echo $((1+))', 'NAME=$(date', 'echo `date',
                   'echo ${NAME@Q}', 'echo $!', "echo $'unfinished", 'eval "$X"',
                   'chmod +x file', 'echo hello & echo bye', 'set -o noclobber',
                   'trap cleanup EXIT', 'git show |', 'echo hello >',
                   'echo "unfinished', 'echo abc\\', 'echo a 3>&1', 'echo ok &&',
                   'bash other.sh', 'unknown <', 'find . -delete',
                   'cat 0<&1', 'echo x 0>out', 'echo x 2>&3']
        for source in sources:
            with self.subTest(source=source):
                result = convert(source)
                self.assertTrue(result.errors)
                self.assertIn("throw 'Conversion incomplete", result.script)
                self.assertLess(result.script.index("throw 'Conversion incomplete"), result.script.index('$script:B2PSVars'))

    def test_quoting_operators_are_inert(self):
        result = convert('echo \'a && b | c > d; $HOME `date`\'\necho "# not comment"')
        self.assertEqual(result.commands, 2)
        self.assertFalse(result.errors)
        self.assertIn("'a && b | c > d; $HOME `date`'", result.script)

    def test_native_arguments_are_quoted(self):
        result = convert('python -c \'print("hello")\'\ngit commit -m "a,b @thing"')
        self.assertFalse(result.errors)
        self.assertIn("'a,b @thing'", result.script)
        self.assertIn('Invoke-B2PSNative', result.script)

    def test_comment_cannot_inject_code(self):
        result = convert('# ignored\necho \'# still data\' # hello\n# `n anything')
        self.assertEqual(result.commands, 1)
        self.assertFalse(result.errors)

    def test_crlf_bom(self):
        self.assertFalse(convert('\ufeffecho a \\\r\n b\r\n').errors)

    def test_empty(self):
        result = convert(' \n# comment')
        self.assertEqual(result.commands, 0)
        self.assertFalse(result.errors)


@unittest.skipUnless(ENGINES, 'PowerShell required')
class PowerShellIntegrationTests(unittest.TestCase):
    def each_engine(self, source, verify, after=''):
        for engine in ENGINES:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                process = run_ps(source, engine, directory, after)
                verify(process, Path(directory))

    def test_file_operations_and_unicode(self):
        source = '''set -e
PROJECT="测试 project"
mkdir -p "$PROJECT"
mkdir -p "$PROJECT"
cd "$PROJECT"
printf '%s\\n' '你好' 'second' > data.txt
echo third >> data.txt
touch empty.txt
cp data.txt copy.txt
mv copy.txt moved.txt
[ -f moved.txt ] && echo EXISTS
rm -f missing.txt
cat data.txt | grep -F second
'''
        def verify(process, directory):
            self.assertEqual(process.returncode, 0, process.stderr)
            folder = directory / '测试 project'
            self.assertEqual((folder / 'data.txt').read_bytes(), '你好\nsecond\nthird\n'.encode())
            self.assertEqual((folder / 'empty.txt').read_bytes(), b'')
            self.assertTrue((folder / 'moved.txt').exists())
            self.assertIn(b'EXISTS', process.stdout)
            self.assertIn(b'second', process.stdout)
        self.each_engine(source, verify)

    def test_touch_never_truncates(self):
        self.each_engine("echo keep > a.txt\ntouch a.txt", lambda p, d: self.assertEqual((d / 'a.txt').read_bytes(), b'keep\n'))

    def test_short_circuit_left_associative(self):
        source = '''false && echo NO1 || echo YES1
true || echo NO2 && echo YES2
false || false && echo NO3
true && false || echo YES3
[ -d missing ] || echo YES4
'''
        def verify(p, d):
            self.assertEqual(p.returncode, 0, p.stderr)
            for word in (b'YES1', b'YES2', b'YES3', b'YES4'):
                self.assertIn(word, p.stdout)
            self.assertNotIn(b'NO', p.stdout)
        self.each_engine(source, verify)

    def test_errexit_stops_required_failure(self):
        self.each_engine('set -e\nfalse\necho UNREACHABLE', lambda p, d: (self.assertNotEqual(p.returncode, 0), self.assertNotIn(b'UNREACHABLE', p.stdout)))

    def test_errexit_does_not_stop_guarded_failure(self):
        self.each_engine('set -e\nfalse && echo NO\necho STILL\nfalse || echo RECOVER', lambda p, d: (self.assertEqual(p.returncode, 0, p.stderr), self.assertIn(b'STILL', p.stdout), self.assertIn(b'RECOVER', p.stdout)))

    def test_native_exit_code_and_fallback(self):
        source = 'python -c \'raise SystemExit(7)\' && echo NO || echo RECOVER\npython -c \'raise SystemExit(3)\'\necho "$?"'
        self.each_engine(source, lambda p, d: (self.assertEqual(p.returncode, 0, p.stderr), self.assertIn(b'RECOVER', p.stdout), self.assertNotIn(b'NO', p.stdout), self.assertIn(b'3', p.stdout)))

    def test_export_and_temporary_environment(self):
        source = '''export B2PS_TEST_ENV=before
B2PS_TEST_ENV=temporary python -c 'import os; print(os.environ.get("B2PS_TEST_ENV"))'
python -c 'import os; print(os.environ.get("B2PS_TEST_ENV"))'
B2PS_TEST_ENV=after
python -c 'import os; print(os.environ.get("B2PS_TEST_ENV"))'
'''
        def verify(p, d):
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(b'temporary', p.stdout)
            self.assertIn(b'before', p.stdout)
            self.assertIn(b'after', p.stdout)
        self.each_engine(source, verify)

    def test_variables_do_not_collide_with_powershell(self):
        source = 'HOME="local-home"\nPID=123\necho "$HOME" "$PID"\necho \'$HOME\'\necho "a\nb" > multiline.txt'
        self.each_engine(source, lambda p, d: (self.assertIn(b'local-home 123', p.stdout), self.assertIn(b'$HOME', p.stdout), self.assertEqual((d / 'multiline.txt').read_bytes(), b'a\nb\n')))

    def test_text_pipeline(self):
        source = "printf '%s\\n' apple APPLE banana apricot > lines.txt\ncat lines.txt | grep -Fi app | head -n 1 | wc -l\ncat lines.txt | grep -Fv apple | tail -n 1"
        self.each_engine(source, lambda p, d: (self.assertEqual(p.returncode, 0, p.stderr), self.assertIn(b'1', p.stdout), self.assertIn(b'apricot', p.stdout)))

    def test_native_argv_preserves_quotes_empty_and_trailing_slashes(self):
        source = '''python -c 'import sys,json; print(json.dumps(sys.argv[1:]))' 'a"b' '' 'space here' 'C:\\path with space\\' 'x,y @thing' '''
        def verify(p, d):
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout), ['a"b', '', 'space here', 'C:\\path with space\\', 'x,y @thing'])
        self.each_engine(source, verify)

    def test_case_sensitive_local_variables(self):
        self.each_engine('Name=upper\nname=lower\necho "$Name" "$name"', lambda p, d: self.assertIn(b'upper lower', p.stdout))

    def test_unset_produces_no_boolean_output(self):
        self.each_engine('A=x\nunset A\necho DONE', lambda p, d: self.assertEqual(p.stdout.strip(), b'DONE'))

    def test_local_case_variant_does_not_change_export(self):
        source = '''export B2PS_NAME=upper
B2PS_name=lower
python -c 'import os; print(os.environ["B2PS_NAME"])'
'''
        self.each_engine(source, lambda p, d: self.assertEqual(p.stdout.strip(), b'upper'))

    def test_unsupported_guard_prevents_partial_execution(self):
        for engine in ENGINES:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                result = convert('touch should-not-exist\nchmod +x file')
                path = Path(directory) / 'blocked.ps1'
                path.write_text(result.script, encoding='utf-8-sig')
                p = subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(path)], cwd=directory, capture_output=True, timeout=30)
                self.assertNotEqual(p.returncode, 0)
                self.assertFalse((Path(directory) / 'should-not-exist').exists())

    def test_generated_examples_parse_in_both_versions(self):
        sources = ['[ -f file ] && echo yes', 'mkdir -p "a b"\ncd "a b"', 'git status && echo ok || echo failed',
                   'FOO=x python -V', 'echo "a\nb" && echo done', 'rm -rf "build output"',
                   'export A=x B=y\nunset A', 'cat a.txt | grep -F x | wc -l', 'echo hi > file.txt',
                   'if x; then y; fi', 'cat <<EOF\na\nEOF']
        for engine in ENGINES:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory(dir=TEST_ROOT) as directory:
                paths = []
                for i, source in enumerate(sources):
                    path = Path(directory) / f'{i}.ps1'
                    path.write_text(convert(source).script, encoding='utf-8-sig')
                    paths.append(str(path))
                manifest = Path(directory) / 'paths.json'
                manifest.write_text(json.dumps(paths), encoding='utf-8')
                check = Path(directory) / 'parse.ps1'
                check.write_text("$paths = Get-Content -Raw -LiteralPath '" + str(manifest).replace("'", "''") + "' | ConvertFrom-Json\nforeach ($path in $paths) { $tokens = $null; $errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors); if ($errors.Count) { $errors | Out-String | Write-Output; exit 1 } }", encoding='utf-8-sig')
                p = subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(check)], capture_output=True, timeout=30)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
