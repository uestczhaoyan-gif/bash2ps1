"""Run controlled scripts in real Bash and both PowerShell versions; compare effects."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converter import convert_file
from test_converter import ENGINES, TEST_ROOT


CASES = {
    'printf_no_newline': "printf '%s' hello",
    'substitution_fragments': 'X="$(printf \'%s\' a; printf \'%s\' b)"; printf \'%s\' "$X"',
    'word_splitting': 'WORDS="a b"; printf \'<%s>\\n\' $WORDS',
    'newline_count': "printf 'x' | wc -l",
    'quoted_empty': "X=''; printf '<%s>\\n' \"$X\" '' x",
    'unquoted_empty': "X=''; printf '<%s>\\n' before $X after",
    'prefix_suffix': "X='a b'; printf '<%s>\\n' pre${X}post",
    'ifs_colon': "IFS=:; X='a::b:'; printf '<%s>\\n' $X",
    'ifs_empty': "IFS=''; X='a b'; printf '<%s>\\n' $X",
    'quoted_operators': "printf '%s\\n' 'a && b | c > d; $HOME `date`'",
    'escaped_variables': 'X=value; printf \'%s\\n\' "\\$X" "a\\qb"',
    'ansi_quotes': "printf '%s' $'a\\tb\\n'",
    'echo_options': "echo -n one; echo two; echo -e 'a\\tb'; echo -E 'x\\ny'",
    'echo_escape_stop': "echo -e 'before\\cafter'; echo done",
    'printf_repeat': "printf '%s=%d\\n' one 1 two 2",
    'printf_width': "printf '[%06d][%-5s][%.2f]\\n' 7 x 1.25",
    'printf_escapes': "printf 'literal=%%\\n%s\\t%b' x 'one\\ntwo'",
    'printf_variable': "printf -v X 'number=%03d' 7; printf '%s' \"$X\"",
    'unicode_text': "printf '%s\\n' '你好' '路径 有空格' > data.txt; cat data.txt",
    'default_nested': 'X="${MISSING:-${OTHER:-fallback}/end}"; printf \'%s\' "$X"',
    'default_empty': "X=''; printf '%s\\n' \"${X-no}\" \"${X:-yes}\"",
    'parameter_assignment': ': "${X:=assigned}"; printf \'%s\' "$X"',
    'parameter_alternative': "X=yes; printf '%s\\n' \"${X:+present}\" \"${MISSING:+absent}\"",
    'parameter_length': "X='hello'; printf '%s' \"${#X}\"",
    'parameter_slice': "X='abcdef'; printf '%s\\n' \"${X:1:3}\" \"${X: -2}\"",
    'parameter_trim': "X='dir/sub/file.txt'; printf '%s\\n' \"${X##*/}\" \"${X%.*}\" \"${X#*/}\" \"${X%%/*}\"",
    'parameter_replace': "X='one-two-one'; printf '%s\\n' \"${X/one/ONE}\" \"${X//one/ONE}\"",
    'parameter_case': "X='AbCd'; printf '%s\\n' \"${X^^}\" \"${X,,}\"",
    'indirect_variable': "A=B; B=value; printf '%s' \"${!A}\"",
    'brace_list_range': "printf '<%s>\\n' pre{a,b} {1..3} {03..01} '{x,y}'",
    'brace_nested': "printf '%s\\n' {a,{b,c}}",
    'file_glob': "touch b.txt a.txt .hidden.txt; printf '<%s>\\n' *.txt '*.txt' missing*.txt",
    'glob_nested': "mkdir -p one two; touch one/b.txt one/a.txt two/c.txt; printf '%s\\n' */*.txt",
    'nullglob': "shopt -s nullglob; printf '<%s>\\n' before missing*.txt after",
    'positional_all': "set -- a 'b c' ''; printf '<%s>\\n' \"$@\"; printf '%s' \"$#\"",
    'positional_join': "set -- a 'b c'; printf '<%s>\\n' \"$*\" \"pre$@post\"",
    'positional_shift': "set -- one two three; shift; printf '%s\\n' \"$1\" \"$#\"; shift 2; printf '%s' \"$#\"",
    'array_values': "A=(one 'two words' ''); printf '<%s>\\n' \"${A[@]}\"; printf '%s' \"${#A[@]}\"",
    'array_append': "A=(one); A+=(two); A[3]=four; printf '%s\\n' \"${A[@]}\" \"${A[3]}\"",
    'array_keys': "A=(a b); printf '%s\\n' \"${!A[@]}\"",
    'associative_array': "declare -A A=([one]=1 [two]='two words'); printf '%s\\n' \"${A[one]}\" \"${A[two]}\"",
    'arithmetic_precedence': "n=3; printf '%s\\n' \"$((n+2*4))\" \"$(((n+2)*4))\" \"$((9/2))\"",
    'arithmetic_updates': "n=1; ((n+=2)); printf '%s\\n' \"$((n++))\" \"$((++n))\" \"$((n>2 ? 7 : 9))\"",
    'arithmetic_status': "((0)) || echo zero; ((2)) && echo nonzero",
    'let': "let 'n=2+3'; printf '%s' \"$n\"",
    'arithmetic_for': "for ((i=0; i<3; i++)); do printf '%s' \"$i\"; done",
    'for_quoted_values': "for x in a 'b c'; do printf '<%s>\\n' \"$x\"; done",
    'for_arguments': "set -- a 'b c'; for x; do printf '<%s>\\n' \"$x\"; done",
    'for_break_continue': "for x in a b c; do if [ \"$x\" = a ]; then continue; fi; echo \"$x\"; break; done",
    'while_until': "n=0; while [ \"$n\" -lt 2 ]; do echo \"$n\"; ((n+=1)); done; until [ \"$n\" -eq 3 ]; do ((n+=1)); done; echo \"$n\"",
    'if_elif': "if false; then echo no; elif [ 3 -gt 2 ]; then echo yes; else echo no; fi",
    'extended_test': "X=abc; if [[ $X == a* && $X != xyz ]]; then echo yes; fi",
    'case_alternatives': "X=abc; case \"$X\" in x|y) echo no;; a*) echo yes;; *) echo no;; esac",
    'function_arguments': "f() { printf '<%s>\\n' \"$@\"; }; f a 'b c' ''",
    'function_local': "X=outer; f() { local X=inner; echo \"$X\"; }; f; echo \"$X\"",
    'function_global': "f() { X=changed; }; X=before; f; echo \"$X\"",
    'function_return': "f() { echo before; return 7; echo no; }; f || echo \"$?\"",
    'function_implicit_status': "f() { false; }; f || echo \"$?\"",
    'function_guarded_errexit': "set -e; f() { false; echo survived; }; f || echo no",
    'group_redirection': "{ printf a; printf b; } > grouped.txt; cat grouped.txt",
    'subshell_state': "X=outer; (X=inner; echo \"$X\"); echo \"$X\"",
    'subshell_exit': "(exit 7) || echo \"$?\"; echo after",
    'explicit_exit': "echo before; exit 7; echo no",
    'implicit_exit': 'false',
    'errexit_status': 'set -e; false; echo no',
    'capture_status': "X=\"$(exit 7)\"; echo \"$?\"",
    'capture_isolation': "X=outer; Y=\"$(X=inner; printf '%s' \"$X\")\"; printf '%s\\n' \"$X\" \"$Y\"",
    'heredoc_expanded': "X=world; cat <<EOF\nhello $X\n\"quoted\" $(printf '%s' command)\nEOF\n",
    'heredoc_literal': "cat <<'EOF'\n$X $(echo not-executed)\nEOF\n",
    'heredoc_tabs': "cat <<-EOF\n\talpha\n\tEOF\n",
    'herestring': "cat <<< 'hello world'",
    'input_redirection': "printf '%s' input > data.txt; cat < data.txt",
    'append_redirection': "printf a > data.txt; printf b >> data.txt; cat data.txt",
    'discard_redirection': "echo discarded > /dev/null; echo visible",
    'stderr_redirection': "echo error >&2; echo out",
    'read_line': "printf '%s\\n' 'a b' > data.txt; IFS= read -r X < data.txt; printf '%s' \"$X\"",
    'read_fields': "printf '%s\\n' 'one two three' > data.txt; read A B < data.txt; printf '<%s>\\n' \"$A\" \"$B\"",
    'read_loop': "printf '%s\\n' a b > data.txt; while IFS= read -r line; do echo \"$line\"; done < data.txt",
    'cat_exact_concat': "printf a > a.txt; printf b > b.txt; cat a.txt b.txt",
    'cat_number': "printf '%s\\n' a '' b | cat -n",
    'cat_squeeze': "printf 'a\\n\\n\\nb\\n' | cat -s",
    'grep_fixed': "printf '%s\\n' apple APPLE banana | grep -Fi app",
    'grep_bre': "printf '%s\\n' a+ aa a | grep 'a+'",
    'grep_ere': "printf '%s\\n' a+ aa a | grep -E '^a+$'",
    'grep_number_invert': "printf '%s\\n' a b a | grep -nv a",
    'grep_count': "printf '%s\\n' apple banana apple | grep -c apple",
    'grep_no_match': "printf '%s\\n' apple | grep missing",
    'grep_quiet': "printf '%s\\n' a b | grep -q b; echo \"$?\"",
    'grep_only': "printf '%s\\n' 'a1 a2' | grep -Eo 'a[0-9]'",
    'head_lines': "printf 'a\\nb\\nc' | head -n 2",
    'tail_lines': "printf 'a\\nb\\nc' | tail -n 2",
    'head_bytes': "printf abcdef | head -c 3",
    'tail_bytes': "printf abcdef | tail -c 2",
    'head_negative': "printf '%s\\n' a b c | head -n -1",
    'tail_from': "printf '%s\\n' a b c | tail -n +2",
    'wc_counts': "printf 'hello world\\nnext' | wc -lwmc",
    'wc_unicode': "printf '%s' '你好' | wc -mc",
    'sort_ordinal': "printf '%s\\n' pear apple banana | sort",
    'sort_numeric': "printf '%s\\n' 10 2 1 | sort -nr",
    'sort_unique': "printf '%s\\n' b a b | sort -u",
    'sort_field': "printf '%s\\n' 'a 3' 'b 1' 'c 2' | sort -k2,2n",
    'uniq_counts': "printf '%s\\n' a a b | uniq -c",
    'uniq_repeated': "printf '%s\\n' a a b | uniq -d",
    'cut_fields': "printf '%s\\n' 'a:b:c' '1:2:3' | cut -d: -f1,3",
    'cut_chars': "printf '%s\\n' abcdef | cut -c2-4",
    'tr_case': "printf '%s' 'Hello World' | tr '[:lower:]' '[:upper:]'",
    'tr_delete': "printf 'a\\rb\\r' | tr -d '\\r'",
    'tr_squeeze': "printf '%s' 'a   b' | tr -s ' '",
    'tee_append': "printf first | tee data.txt; printf second | tee -a data.txt; cat data.txt",
    'sed_substitute': "printf '%s\\n' 'foo foo' bar | sed 's/foo/ONE/g'",
    'sed_delete': "printf '%s\\n' a '' b | sed '/^$/d'",
    'sed_address': "printf '%s\\n' a b c | sed -n '2p'",
    'sed_backreference': "printf '%s\\n' abc | sed 's/\\(a\\)b/\\1X/'",
    'sed_inplace': "printf '%s\\n' old > data.txt; sed -i.bak 's/old/new/' data.txt; cat data.txt",
    'awk_fields': "printf '%s\\n' 'a b c' 'one two three' | awk '{print $1,$3}'",
    'awk_delimiter': "printf '%s\\n' 'a:b:c' | awk -F: '{print $2}'",
    'awk_sum': "printf '%s\\n' '2 a' '3 b' | awk '{sum += $1} END {print sum}'",
    'seq_range': 'seq 2 2 6',
    'seq_separator': "seq -s, 3",
    'xargs_group': "printf '%s\\n' a b c | xargs -n2 echo prefix",
    'xargs_quoted': "printf '%s' \"'a b' c\" | xargs -n1 echo",
    'xargs_replace': "printf '%s\\n' 'one two' three | xargs -I{} echo 'item={}'",
    'xargs_zero': "printf 'one two\\0three\\0' | xargs -0 -n1 echo",
    'xargs_empty': "printf '' | xargs -r echo no",
    'file_copy_move': "mkdir -p src; printf '%s' one > src/a; cp -r src dest; cp src/a copy; mv copy moved; cat moved; rm -f moved missing",
    'directory_merge': "mkdir -p src dest/src; printf a > src/a; printf b > dest/src/b; cp -r src dest; cat dest/src/a dest/src/b",
    'touch_preserves': "printf keep > data.txt; touch data.txt; cat data.txt",
    'basename_suffix': "basename 'folder/file.txt' .txt",
    'dirname_relative': "dirname 'folder/file.txt'",
    'source_shared': "printf '%s\\n' 'X=from_source' > helper.sh; . helper.sh; echo \"$X\"",
}

# Source files are provided before conversion, rather than generated during conversion.
FILES = {
    'source_shared': {'helper.sh': 'X=from_source\n'},
}

PYTHON = '"' + Path(sys.executable).as_posix() + '"'
CASES.update({
    'local_unset': "X=outer; f() { local X; printf '%s' \"${X-unset}\"; }; f; echo \"$X\"",
    'local_array': "A=(outer); f() { local A=(inner 'two words'); printf '<%s>\\n' \"${A[@]}\"; }; f; echo \"${A[0]}\"",
    'compound_fallback': "set -e; false || { echo recovered; }; { false; echo survived; } || echo no",
    'heredoc_backslash_quote': 'cat <<EOF\n\\"literal\\"\nEOF\n',
    'native_argv': PYTHON + " -c 'import sys,json; print(json.dumps(sys.argv[1:]))' 'a\"b' '' 'space here' 'C:\\path with space\\'",
    'native_pipeline': PYTHON + " -c 'import sys; sys.stdout.buffer.write(b\"a\\nb\\n\")' | grep -F b | head -n 1",
    'native_input': "printf '%s' 'hello input' | " + PYTHON + " -c 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'",
    'native_binary': PYTHON + " -c 'import sys; sys.stdout.buffer.write(bytes(range(256)))' > data.bin; " + PYTHON + " -c 'from pathlib import Path; print(len(Path(\"data.bin\").read_bytes()))'",
    'native_exit_fallback': PYTHON + " -c 'raise SystemExit(7)' || echo \"$?\"",
    'native_large_exit': PYTHON + " -c 'raise SystemExit(258)' || echo \"$?\"",
    'native_stderr': PYTHON + " -c 'import sys; sys.stderr.buffer.write(b\"error\\n\")' 2> error.txt; cat error.txt",
    'native_merged': PYTHON + " -c 'import sys; sys.stdout.buffer.write(b\"out\\n\"); sys.stdout.flush(); sys.stderr.buffer.write(b\"err\\n\"); sys.stderr.flush()' 2>&1",
    'redirect_order': PYTHON + " -c 'import sys; sys.stdout.buffer.write(b\"out\\n\"); sys.stderr.buffer.write(b\"err\\n\")' 2>&1 > data.txt; cat data.txt",
    'redirect_file_merge': PYTHON + " -c 'import sys; sys.stdout.buffer.write(b\"out\\n\"); sys.stdout.flush(); sys.stderr.buffer.write(b\"err\\n\")' >& data.txt; cat data.txt",
    'pipefail_native': "set -o pipefail; " + PYTHON + " -c 'import sys; sys.stdout.buffer.write(b\"data\\n\"); raise SystemExit(7)' | cat || echo \"$?\"",
    'pipe_statuses': "printf x | grep missing | cat; printf '%s\\n' \"${PIPESTATUS[@]}\"",
    'native_temp_environment': "X=old; export X; X=new " + PYTHON + " -c 'import os; print(os.environ[\"X\"])'; echo \"$X\"",
    'temp_expansion_order': "X=old; X=new echo \"$X\"; echo \"$X\"",
    'env_environment': "env B2PS_ENV=temporary " + PYTHON + " -c 'import os; print(os.environ[\"B2PS_ENV\"])'",
    'xargs_failure': "printf '%s\\n' a | xargs false",
    'empty_export': "export B2PS_EMPTY=''; " + PYTHON + " -c 'import os; print(repr(os.environ.get(\"B2PS_EMPTY\")))'",
    'multiple_temp_environment': "A=one B=two " + PYTHON + " -c 'import os; print(os.environ[\"A\"],os.environ[\"B\"])'",
    'test_empty_path': "X=''; [ -f \"$X\" ] || echo missing",
    'test_word_expansion': "X=''; [ $X = a ] 2>/dev/null || echo \"$?\"",
    'test_parentheses': "[ \\( x = x \\) -a 3 -gt 2 ] && echo yes",
    'cat_visible': "printf 'a\\tb\\r\\n' | cat -An",
    'cat_visible_unicode': "printf '%s' '你好' | cat -A",
    'grep_context': "printf '%s\\n' a b c d e f g | grep -nC1 -e b -e f",
    'grep_after': "printf '%s\\n' a b c d | grep -A1 b",
    'grep_before': "printf '%s\\n' a b c d | grep -B1 c",
})

if os.environ.get('B2PS_CASE_FILTER'):
    selected=set(os.environ['B2PS_CASE_FILTER'].split(','))
    CASES={name:source for name,source in CASES.items() if name in selected}
    if not CASES:
        raise RuntimeError('No differential cases matched the requested filter')


@unittest.skipUnless(ENGINES, 'PowerShell required')
class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates = [os.environ.get('B2PS_BASH'), shutil.which('bash'), r'C:\Program Files\Git\bin\bash.exe']
        cls.bash = next((p for p in candidates if p and Path(p).is_file()), None)
        if not cls.bash:
            if os.environ.get('B2PS_REQUIRE_BASH') == '1':
                raise RuntimeError('Bash reference runtime is required')
            raise unittest.SkipTest('Git Bash required for reference validation')
        probe = subprocess.run([cls.bash, '--noprofile', '--norc', '-c', "printf ready"], capture_output=True, timeout=15)
        if probe.returncode or probe.stdout != b'ready':
            raise RuntimeError('Git Bash cannot start; run the controlled suite outside the restricted process sandbox')
        cls.temporary = tempfile.TemporaryDirectory(prefix='differential ', dir=TEST_ROOT)
        cls.root = Path(cls.temporary.name)
        cls.results = {}
        env = os.environ.copy()
        env.update(LC_ALL='C.UTF-8', LANG='C.UTF-8', PYTHONIOENCODING='utf-8')
        for name, source in CASES.items():
            root = cls.root / ('bash_' + name)
            root.mkdir()
            for file, text in FILES.get(name, {}).items():
                (root / file).write_text(text, encoding='utf-8')
            path = root / 'scenario.sh'
            path.write_text(source + '\n', encoding='utf-8', newline='\n')
            process = subprocess.run([cls.bash, '--noprofile', '--norc', path.as_posix()], cwd=root, env=env, capture_output=True, timeout=15)
            cls.results[(name, 'bash')] = (process.returncode, process.stdout, process.stderr, cls.snapshot(root))
        for number, engine in enumerate(ENGINES):
            manifest = []
            for name, source in CASES.items():
                root = cls.root / ('ps' + str(number) + '_' + name)
                root.mkdir()
                for file, text in FILES.get(name, {}).items():
                    (root / file).write_text(text, encoding='utf-8')
                source_path = root / 'scenario.sh'
                source_path.write_text(source + '\n', encoding='utf-8')
                result = convert_file(source_path)
                if result.errors:
                    raise AssertionError(f'{name}: {result.errors}')
                target = root / 'converted.ps1'
                stdout, stderr = root / 'stdout.bin', root / 'stderr.bin'
                setup = "$script:B2PSIO.Out=[IO.Stream]::Synchronized([IO.File]::Create('" + str(stdout).replace("'", "''") + "')); $script:B2PSIO.Err=[IO.Stream]::Synchronized([IO.File]::Create('" + str(stderr).replace("'", "''") + "'))\n"
                script = result.script.replace('# Main script', setup + '# Main script').replace('# B2PS final status', '$script:B2PSIO.Out.Dispose(); $script:B2PSIO.Err.Dispose()\n# B2PS final status')
                target.write_text(script, encoding='utf-8-sig')
                manifest.append({'name': name, 'path': str(target), 'root': str(root)})
            manifest_path = cls.root / ('manifest' + str(number) + '.json')
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            status_path = cls.root / ('status' + str(number) + '.json')
            driver = cls.root / ('runner' + str(number) + '.ps1')
            driver.write_text("""$cases=Get-Content -Raw -Encoding UTF8 -LiteralPath 'MANIFEST'|ConvertFrom-Json
$results=@()
foreach($case in $cases){
 $saved=[Environment]::GetEnvironmentVariables('Process')
 Set-Location -LiteralPath $case.root
 $global:LASTEXITCODE=0
 & $case.path
 $results+=@{name=$case.name;code=$global:LASTEXITCODE}
 $current=[Environment]::GetEnvironmentVariables('Process')
 foreach($key in $current.Keys){if(-not $saved.Contains($key)){[Environment]::SetEnvironmentVariable($key,$null,'Process')}}
 foreach($key in $saved.Keys){if($current[$key] -cne $saved[$key]){[Environment]::SetEnvironmentVariable($key,$saved[$key],'Process')}}
}
$results|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath 'STATUS'
""".replace('MANIFEST', str(manifest_path).replace("'", "''")).replace('STATUS', str(status_path).replace("'", "''")), encoding='utf-8-sig')
            process = subprocess.run([engine, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(driver)], env=env, capture_output=True, timeout=180)
            if process.returncode:
                raise AssertionError(process.stdout + process.stderr)
            statuses = json.loads(status_path.read_text(encoding='utf-8-sig'))
            for entry in statuses:
                root = cls.root / ('ps' + str(number) + '_' + entry['name'])
                cls.results[(entry['name'], engine)] = (entry['code'], (root / 'stdout.bin').read_bytes(), (root / 'stderr.bin').read_bytes(), cls.snapshot(root))

    @staticmethod
    def snapshot(root):
        files = {}
        for path in root.rglob('*'):
            if path.is_file() and path.name not in {'scenario.sh', 'converted.ps1', 'stdout.bin', 'stderr.bin'}:
                files[path.relative_to(root).as_posix()] = path.read_bytes()
        return files

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_common_scripts_match_bash(self):
        for name in CASES:
            expected = self.results[(name, 'bash')]
            for engine in ENGINES:
                with self.subTest(case=name, engine=Path(engine).name):
                    actual = self.results[(name, engine)]
                    self.assertEqual(actual[0], expected[0], ('exit', actual, expected))
                    self.assertEqual(actual[1], expected[1], ('stdout', actual, expected))
                    self.assertEqual(actual[2], expected[2], ('stderr', actual, expected))
                    self.assertEqual(actual[3], expected[3], ('files', actual, expected))


if __name__ == '__main__':
    unittest.main(verbosity=2)
