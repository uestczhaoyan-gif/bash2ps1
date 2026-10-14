"""Compile a portable Bash subset to native PowerShell. No shell is executed."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from arithmetic import parse_arithmetic
from shellsyntax import Node, Token, ShellParser, Unsupported, expansion_end, lex
from runtime_core import RUNTIME
from command_runtime import BUILTINS
from text_runtime import TEXT_RUNTIME
from native_runtime import NATIVE_RUNTIME
from command_specs import validate_options, validate_sed, validate_awk


@dataclass(frozen=True)
class Issue:
    line: int
    level: str
    message: str


@dataclass
class Result:
    script: str
    issues: list[Issue] = field(default_factory=list)
    commands: int = 0

    @property
    def errors(self):
        return [i for i in self.issues if i.level == 'error']

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == 'warning']


def ps_quote(value):
    if '\r' in value or '\n' in value or '\0' in value:
        return '"' + value.replace('`', '``').replace('$', '`$').replace('"', '`"').replace('\r', '`r').replace('\n', '`n').replace('\0', '`0') + '"'
    return "'" + value.replace("'", "''") + "'"


def ps_data(value):
    if isinstance(value, list):
        return '@(' + ', '.join(ps_data(v) for v in value) + ')'
    return ps_quote(str(value))


def literal(token):
    raw, i, quote, out = token.raw, 0, None, []
    while i < len(raw):
        c = raw[i]
        if quote == "'":
            if c == "'":
                quote = None
            else:
                out.append(c)
        elif c in "'\"" and (quote is None or quote == c):
            quote = None if quote == c else c
        elif c == '\\':
            if i + 1 >= len(raw):
                raise Unsupported('末尾反斜杠缺少内容。')
            n = raw[i + 1]
            if n == '\n':
                i += 1
            elif quote == '"' and n not in '$`"\\':
                out.append(c)
            else:
                out.append(n)
                i += 1
        elif c in '$`' or (quote is None and c in '*?[]{}~'):
            raise Unsupported('这里需要固定文本。')
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def brace_words(token):
    raw, quote, i = token.raw, None, 0
    while i < len(raw):
        c = raw[i]
        if c == '\\' and quote != "'":
            i += 2
            continue
        if c in "'\"" and (quote is None or quote == c):
            quote = None if quote == c else c
        elif quote != "'" and raw.startswith(('${', '$('), i):
            i = expansion_end(raw, i)
            continue
        elif quote is None and c == '{':
            depth, end = 1, i + 1
            while end < len(raw) and depth:
                depth += (raw[end] == '{') - (raw[end] == '}')
                end += 1
            if depth:
                return [token]
            inside = raw[i + 1:end - 1]
            pieces, start, depth = [], 0, 0
            for j, ch in enumerate(inside):
                depth += (ch == '{') - (ch == '}')
                if ch == ',' and depth == 0:
                    pieces.append(inside[start:j]); start = j + 1
            if pieces:
                pieces.append(inside[start:])
            elif (match := re.fullmatch(r'(-?\d+|[a-zA-Z])\.\.(-?\d+|[a-zA-Z])(?:\.\.(-?\d+))?', inside)):
                numeric = match[1].lstrip('-').isdigit() and match[2].lstrip('-').isdigit()
                first, last = (int(match[1]), int(match[2])) if numeric else (ord(match[1]), ord(match[2]))
                step = abs(int(match[3] or 1)) * (1 if last >= first else -1)
                if not step or abs(last - first) > 10000:
                    raise Unsupported('花括号范围过大或步长为 0。')
                width = max(len(match[1].lstrip('-')), len(match[2].lstrip('-'))) if numeric and (match[1].startswith('0') or match[2].startswith('0')) else 0
                pieces = [str(n).zfill(width) if numeric else chr(n) for n in range(first, last + (1 if step > 0 else -1), step)]
            else:
                i = end
                continue
            result = []
            for piece in pieces:
                result.extend(brace_words(Token(raw[:i] + piece + raw[end:], token.line)))
            if len(result) > 10000:
                raise Unsupported('花括号展开超过 10000 个参数。')
            return result
        i += 1
    return [token]


class Translator:
    BLOCKED = {'eval', 'exec', 'trap', 'wait', 'sudo', 'su', 'apt', 'apt-get', 'yum', 'dnf', 'pacman', 'chmod', 'chown', 'zsh', 'sh', 'alias', 'unalias'}
    BUILTIN = {'echo','printf','true','false',':','set','shopt','shift','exit','return','break','continue','export','local','unset','declare','read','pwd','cd','pushd','popd','sleep','dirname','basename','realpath','date','mkdir','touch','rmdir','cp','mv','rm','find','seq','tee','printenv','env','which','command','type','ls','cat','grep','head','tail','wc','sort','uniq','cut','tr','sed','awk','xargs','ln'}
    NATIVE = {'git','python','python3','pip','pip3','node','npm','npx','docker','go','cargo','rustc','cmake','dotnet','java','javac','ffmpeg','tar','curl','wget','make','code','uv','ssh','scp','rsync'}
    REDIR = re.compile(r'(?:[012])?(?:>>?|<|>&|<&)|&>>?|<<<|<<-?')

    def __init__(self, source_path=None, bundle=None, active=None):
        self.source_path = Path(source_path).resolve() if source_path else None
        self.bundle = bundle if bundle is not None else {}
        self.active = active if active is not None else set()
        self.issues, self.commands, self.dependencies = [], 0, set()
        self.functions, self.counter, self.loop_depth = set(), 0, 0
        self.export_names = {}

    def warn(self, line, message):
        issue = Issue(line, 'warning', message)
        if issue not in self.issues:
            self.issues.append(issue)

    @staticmethod
    def indent(text):
        return '\n'.join('    ' + s for s in text.splitlines())

    def arithmetic(self, source):
        return '(Invoke-B2PSArithmetic ' + ps_data(parse_arithmetic(source)) + ')'

    def parameter(self, inner, line):
        spread = False
        if inner == 'BASH_SOURCE[0]':
            return "(Get-B2PSValue 'BASH_SOURCE')", False
        if inner in {'@', '*'}:
            return "@(Get-B2PSArray '@')", inner == '@'
        if inner.startswith('#') and len(inner)>1:
            value, is_array = self.parameter(inner[1:], line)
            return ('(@(' + value + ').Count)' if is_array else '([string]' + value + ').Length'), False
        if (m := re.fullmatch(r'!([A-Za-z_][A-Za-z_0-9]*)\[(@|\*)\]', inner)):
            return f'@(Get-B2PSArray {ps_quote(m[1])} -Keys)', m[2] == '@'
        if (m := re.fullmatch(r'!([A-Za-z_][A-Za-z_0-9]*)', inner)):
            return f'(Get-B2PSValue (Get-B2PSValue {ps_quote(m[1])}))', False
        if (m := re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)\[([^\]]+)\](.*)', inner, re.S)):
            if m[2] in {'@', '*'}:
                if m[3]:
                    raise Unsupported('数组整体展开暂不组合字符串替换操作。')
                return f'@(Get-B2PSArray {ps_quote(m[1])})', m[2] == '@'
            index = self.arithmetic(m[2]) if re.fullmatch(r'[0-9+*/%() -]+', m[2]) else self.scalar(Token(m[2], line))
            if m[3]:
                raise Unsupported('数组元素请先取值，再进行字符串变换。')
            return f'(Get-B2PSArrayItem {ps_quote(m[1])} ([string]{index}))', False
        if (m := re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*|\d+|[?#$])(:?[-+=?])(.*)', inner, re.S)):
            return f'(Expand-B2PSParameter {ps_quote(m[1])} {ps_quote(m[2])} {{ {self.scalar(Token(m[3], line))} }})', False
        if (m := re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*):\s*(-?\d+)(?::\s*(-?\d+))?', inner)):
            return f'(Expand-B2PSString (Get-B2PSValue {ps_quote(m[1])}) \'slice\' {ps_quote(m[2] + ("," + m[3] if m[3] else ""))})', False
        if (m := re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)(##?|%%?|\^\^|,,)(.*)', inner, re.S)):
            return f'(Expand-B2PSString (Get-B2PSValue {ps_quote(m[1])}) {ps_quote(m[2])} {self.scalar(Token(m[3],line))})', False
        if (m := re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)(//?)(.*?)/(.*)', inner, re.S)):
            return f'(Expand-B2PSString (Get-B2PSValue {ps_quote(m[1])}) {ps_quote(m[2])} {self.scalar(Token(m[3],line))} {self.scalar(Token(m[4],line))})', False
        if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*|\d+|[?#$]', inner):
            return f'(Get-B2PSValue {ps_quote(inner)})', False
        raise Unsupported('尚不支持该参数展开；请查看已支持的默认值、数组、长度、切片及字符串操作。')

    def parts(self, token, heredoc=False):
        raw, i, quote = token.raw, 0, ('"' if heredoc else None)
        parts, chars = [], []
        literal_quoted = bool(quote)
        def emit(value, quoted, split=False, spread=False, glob=False):
            parts.append('@{ Value=' + value + '; Quoted=$' + str(quoted).lower() + '; Split=$' + str(split).lower() + '; Spread=$' + str(spread).lower() + '; Glob=$' + str(glob).lower() + ' }')
        def flush():
            nonlocal chars
            if chars:
                emit(ps_quote(''.join(chars)), literal_quoted, glob=not literal_quoted)
                chars = []
        if not heredoc and (raw == '~' or raw.startswith('~/')):
            emit("(Get-B2PSValue 'HOME')", True); i = 1
        while i < len(raw):
            c = raw[i]
            if c == '\\' and quote != "'":
                if i + 1 >= len(raw):
                    raise Unsupported('末尾反斜杠缺少内容。')
                n = raw[i + 1]
                if n == '\n':
                    i += 2; continue
                if quote == '"' and (n not in '$`"\\' or (heredoc and n == '"')):
                    chars.append('\\'); i += 1; continue
                flush(); emit(ps_quote(n), True); i += 2; continue
            if quote == "'":
                if c == "'":
                    flush(); quote = None; literal_quoted = False
                else:
                    chars.append(c)
                i += 1; continue
            if not heredoc and c in "'\"" and (quote is None or quote == c):
                flush(); quote = None if quote == c else c; literal_quoted = bool(quote)
                # Empty quoted strings preserve an argument; "$@" is the exception.
                if quote and i + 1 < len(raw) and raw[i + 1] == c:
                    emit("''", True)
                i += 1; continue
            if raw.startswith("$'", i) and quote is None:
                end = i + 2
                while end < len(raw):
                    if raw[end] == '\\': end += 2; continue
                    if raw[end] == "'": break
                    end += 1
                if end >= len(raw): raise Unsupported('ANSI-C 引号没有闭合。')
                flush(); emit('(Convert-B2PSEscapes '+ps_quote(raw[i+2:end])+').Text', True); i=end+1; continue
            if c == '`' or raw.startswith('$(', i):
                end = expansion_end(raw, i); flush()
                if raw.startswith('$((', i):
                    expression = self.arithmetic(raw[i+3:end-2])
                else:
                    parser=ShellParser(lex(raw[i+(1 if c=='`' else 2):end-1], token.line))
                    expression='(Invoke-B2PSCapture {\n'+self.nodes(parser.parse())+'\n})'
                emit(expression, bool(quote), split=not quote, glob=not quote); i=end; continue
            if c == '$':
                flush()
                if raw.startswith('${', i):
                    end=expansion_end(raw,i); expression,spread=self.parameter(raw[i+2:end-1],token.line); i=end
                elif (match := re.match(r'\$([A-Za-z_][A-Za-z_0-9]*|[0-9?@*#$])',raw[i:])):
                    expression,spread=self.parameter(match[1],token.line); i+=len(match[0])
                elif raw.startswith('$!',i):
                    raise Unsupported('后台进程参数 $! 不适用于此原生转换范围。')
                else:
                    chars.append(c); i+=1; continue
                emit(expression,bool(quote),split=not quote,spread=spread,glob=not quote); continue
            chars.append(c); i+=1
        flush()
        if not parts and not raw:
            emit("''", False)
        return '@('+', '.join(parts)+')'

    def scalar(self, token, heredoc=False):
        return '(Join-B2PSScalar -Parts ' + self.parts(token,heredoc) + ')'

    def words(self, tokens, assignments=False):
        out=[]
        for token in tokens:
            if assignments and re.match(r'^[A-Za-z_][A-Za-z_0-9]*=',token.raw):
                out.append(self.scalar(token)); continue
            for expanded in brace_words(token):
                out.append('Expand-B2PSWord -Parts '+self.parts(expanded))
        return '@('+'; '.join(out)+')'

    def assignment(self, match, token):
        name,index,append,value=match.groups()
        if name == 'PWD': raise Unsupported('PWD 由当前目录决定，不作为普通变量赋值。')
        if name.upper()=='PATH': self.warn(token.line,'PATH 将按 Windows 的分号分隔符处理；目录须存在于 Windows。')
        expression=self.scalar(Token(value,token.line))
        if index is not None:
            key=self.arithmetic(index) if re.fullmatch(r'[0-9+*/%() -]+',index) else self.scalar(Token(index,token.line))
            return f'Set-B2PSArrayItem {ps_quote(name)} ([string]{key}) {expression}'
        if append: expression='((Get-B2PSValue '+ps_quote(name)+') + '+expression+')'
        return f'Set-B2PSValue {ps_quote(name)} {expression}'

    ASSIGN=re.compile(r'^([A-Za-z_][A-Za-z_0-9]*)(?:\[([^\]]+)\])?(\+)?=(.*)$',re.S)

    def validate(self,name,args,line):
        if name in self.BLOCKED: raise Unsupported(f'{name} 需要 Shell 动态执行、Unix 系统能力或作业控制；不能作为本版本的原生等价转换。')
        if name not in self.BUILTIN and name not in self.NATIVE and name not in self.functions:
            self.warn(line,f'外部命令 {name} 需安装 Windows 可执行版本；转换器不会安装程序。')
        if name not in self.BUILTIN and name not in self.functions: self.dependencies.add(name)
        fixed=[]
        for arg in args:
            try: fixed.append(literal(arg))
            except Unsupported: fixed.append(None)
        validate_options(name,fixed)
        if name in {'sed','awk'}:
            programs=[];i=0
            while i<len(fixed):
                item=fixed[i]
                if item=='-e' and name=='sed':
                    if i+1<len(fixed):programs.append(fixed[i+1])
                    i+=2;continue
                if item in {'-F'} or (item is not None and item.startswith('--expression') and '=' not in item):i+=2;continue
                if item is not None and item.startswith('-'):i+=1;continue
                if not programs:programs.append(item)
                break
            for program in programs:
                if program is not None:(validate_sed if name=='sed' else validate_awk)(program)
        if name in {'npm','npx','code'} or name.lower().endswith(('.cmd','.bat')):
            if any(x is not None and re.search('["%!\r\n]',x) for x in fixed): raise Unsupported('Windows 批处理参数中的引号、%、! 或换行需人工处理。')
        if name=='set':
            for i,value in enumerate(fixed):
                if value=='--': break
                if value is None: continue
                if value.startswith(('-','+')):
                    if not re.fullmatch(r'[-+][euaxo]+',value): raise Unsupported('set 支持 e/u/a/x 和 -o/+o 的常见选项。')
                elif i==0 or fixed[i-1] is None or not fixed[i-1].endswith('o') or value not in {'pipefail','errexit','nounset','allexport','xtrace'}: raise Unsupported('不支持该 set 选项。')
        if name=='printf':
            position=2 if fixed and fixed[0]=='-v' else 0
            if position<len(fixed) and fixed[position] is not None and re.search(r'%(?![-+ #0]*\d*(?:\.\d+)?[sbdifuoxXc%])',re.sub(r'%%','',fixed[position])): raise Unsupported('printf 支持常见字符串、整数、浮点数、进制、宽度和转义；不支持该格式。')
        if name=='find':
            allowed={'-mindepth','-maxdepth','-type','-name','-iname','-print','-print0'}
            for value in fixed:
                if value and value.startswith('-') and value not in allowed: raise Unsupported('find 支持深度、类型、名称和 print/print0；不支持该谓词。')
        if name=='date':
            for value in fixed:
                if value is None or value in {'-u','--utc','-Is','--iso-8601=seconds'}:continue
                if not value.startswith('+') or re.search(r'%(?![YmdHMSFTszZ%])',value):raise Unsupported('date 支持 -Is、-u 和常见 +格式；不支持该选项或格式。')
        if name in {'grep','sed'} and '-F' not in fixed: self.warn(line,f'{name} 的普通 BRE/ERE 正则转换为 .NET；依赖区域设置或高级 GNU 扩展的表达式需适配。')
        if name in {'curl','wget','tar','ssh','scp','rsync'}: self.warn(line,f'{name} 调用 Windows 外部程序，其选项及远端环境需可用。')

    def script_command(self,name,args,line):
        if not args or args[0].raw.startswith('-'): raise Unsupported(f'{name} 需要脚本路径，不支持动态 -c Shell 代码。')
        try: path_text=literal(args[0])
        except Unsupported:
            if not self.source_path: raise Unsupported('动态子脚本路径需要打开原 .sh 文件。')
            raw=args[0].raw.strip('"')
            raw=re.sub(r'\$\(dirname\s+["\']?\$(?:0|\{BASH_SOURCE\[0\]\})["\']?\)',str(self.source_path.parent).replace('\\','/'),raw)
            if '$' in raw or '`' in raw: raise Unsupported('无法静态定位该子脚本路径；请使用明确路径。')
            path_text=raw
        if name in {'.','source'} and Path(path_text).suffix.lower() not in {'.sh','.bash'}:
            self.warn(line,'环境文件在运行时按 NAME=value 读取，不执行其中的 Shell 代码。')
            return 'Import-B2PSEnv -Path '+self.scalar(args[0])+'\n$script:B2PSStatus=0'
        if not self.source_path: raise Unsupported('调用子脚本请使用“打开 .sh 文件”或 CLI 文件入口，以便同时打包。')
        path=Path(path_text);candidates=[path] if path.is_absolute() else [parent/path for parent in self.source_path.parents]
        resolved=next((p.resolve() for p in candidates if p.is_file()),None)
        if not resolved: raise Unsupported(f'找不到被调用脚本 {path_text}。')
        if resolved in self.active: raise Unsupported(f'脚本循环引用：{path_text}。')
        if resolved not in self.bundle:
            child=Translator(resolved,self.bundle,self.active);self.active.add(resolved)
            try: body=child.body(resolved.read_text(encoding='utf-8-sig'))
            finally: self.active.remove(resolved)
            self.bundle[resolved]=body;self.commands+=child.commands;self.dependencies.update(child.dependencies)
            self.issues.extend(Issue(line,i.level,f'{path_text}:L{i.line}: {i.message}') for i in child.issues)
        return f'Invoke-B2PSScript -Path {ps_quote(str(resolved))} -ArgumentList {self.words(args[1:])}'+(' -Source' if name!='bash' else '')

    def condition(self,args,extended=False):
        for op,psop in [('-o','-or'),('-a','-and')]:
            if len(args)>3:
                for index,token in enumerate(args):
                    if token.raw==op: return '('+self.condition(args[:index],extended)+') '+psop+' ('+self.condition(args[index+1:],extended)+')'
        if not args: return '$false'
        if args[0].raw=='!': return '-not ('+self.condition(args[1:],extended)+')'
        if len(args)==1: return '('+self.scalar(args[0])+').Length -gt 0'
        if len(args)==2:
            op,value=args[0].raw,self.scalar(args[1])
            if op in {'-e','-f','-d','-L','-h','-r','-w','-x'}: return 'Test-Path -LiteralPath '+value+({'-f':' -PathType Leaf','-d':' -PathType Container'}.get(op,''))
            if op=='-s': return '(Test-Path -LiteralPath '+value+' -PathType Leaf) -and (Get-Item -LiteralPath '+value+').Length -gt 0'
            if op in {'-z','-n'}: return '('+value+').Length '+('-eq' if op=='-z' else '-gt')+' 0'
        if len(args)==3:
            left,right=self.scalar(args[0]),self.scalar(args[2]);op=args[1].raw
            if op in {'=','==','!='}:
                if extended and not args[2].raw.startswith(("'",'"')): return f'[string]{left} '+('-cnotmatch' if op=='!=' else '-cmatch')+' (\'^\' + (Convert-B2PSGlob '+right+') + \'$\')'
                return left+(' -cne ' if op=='!=' else ' -ceq ')+right
            if op=='=~' and extended: return left+' -cmatch '+right
            if op in {'-eq','-ne','-gt','-ge','-lt','-le'}: return '[long]'+left+' '+op+' [long]'+right
            if op in {'<','>'} and extended: return '[string]::CompareOrdinal('+left+','+right+') '+('-lt' if op=='<' else '-gt')+' 0'
            if op in {'-nt','-ot','-ef'}: return 'Test-B2PSFileComparison '+left+' '+ps_quote(op)+' '+right
        raise Unsupported('不支持该条件表达式；支持常用文件、字符串、数值和逻辑判断。')

    def redirected(self,code,tokens):
        redirects=[];i=0
        while i<len(tokens):
            op=tokens[i].raw
            if op not in {'<','0<','>','1>','2>','>>','1>>','2>>','&>','&>>','<<','<<-','<<<','>&','1>&','2>&'}:
                raise Unsupported('支持标准输入、标准输出和标准错误的常用重定向；不支持该文件描述符操作。')
            if i+1>=len(tokens): raise Unsupported('重定向缺少目标。')
            target=tokens[i+1]
            if op in {'>&','1>&','2>&'}:
                try: destination=literal(target)
                except Unsupported: destination=None
                if destination is not None and destination not in {'1','2','-'}:
                    if op=='>&' and not destination.isdigit(): op='&>'
                    else: raise Unsupported('文件描述符复制支持 1、2 和 -；其他描述符需人工适配。')
            if op in {'<<','<<-'}: expr=ps_quote(target.raw) if target.kind=='here-literal' else self.scalar(target,heredoc=True)
            else: expr=self.scalar(target)
            redirects.append('@{ Op='+ps_quote(op)+'; Value='+expr+' }');i+=2
        return 'Invoke-B2PSRedirected -Redirections @('+', '.join(redirects)+') -Action {\n'+self.indent(code)+'\n}'

    def command(self,tokens):
        if not tokens: raise Unsupported('缺少命令。')
        if len(tokens)==1 and tokens[0].kind=='block': return self.nodes([tokens[0].node]),False
        if tokens[0].raw=='((' and tokens[-1].raw=='))':
            return '$script:B2PSStatus = [int]('+self.arithmetic(' '.join(t.raw for t in tokens[1:-1]))+' -eq 0)',False
        if tokens[0].raw in {'[','[[','test'}:
            args=tokens[1:];extended=tokens[0].raw=='[['
            if tokens[0].raw!='test':
                if not args or args[-1].raw!=(']]' if extended else ']'): raise Unsupported('条件判断缺少结束括号。')
                args=args[:-1]
            if not extended:return 'Invoke-B2PSTest '+self.words(args),False
            if extended:
                # && / || in [[ ]] are conditions rather than command chains.
                for join,psop in [('||','-or'),('&&','-and')]:
                    for i,t in enumerate(args):
                        if t.raw==join:
                            return '$script:B2PSStatus=[int](-not (('+self.condition(args[:i],True)+') '+psop+' ('+self.condition(args[i+1:],True)+')))',False
            return '$script:B2PSStatus=[int](-not ('+self.condition(args,extended)+'))',False
        # Array assignments keep their parentheses as syntax, not as shell evaluation.
        prefix=[]
        local_array=tokens[0].raw=='local' and len(tokens)>2 and tokens[2].raw=='(' and self.ASSIGN.match(tokens[1].raw)
        if tokens[0].raw=='declare' or local_array:
            while len(tokens)>1 and tokens[1].raw in {'-a','-A'}: prefix.append(tokens[1]);tokens=[tokens[0]]+tokens[2:]
            if len(tokens)>1 and self.ASSIGN.match(tokens[1].raw): tokens=tokens[1:]
        if (match:=self.ASSIGN.fullmatch(tokens[0].raw)) and match[4]=='' and len(tokens)>1 and tokens[1].raw=='(':
            if tokens[-1].raw!=')': raise Unsupported('数组赋值缺少右括号。')
            name,index,append,_=match.groups()
            if index is not None: raise Unsupported('数组元素不能赋整个数组。')
            values=tokens[2:-1]
            keyed=any(re.match(r'^\[.+\]=',t.raw) for t in values)
            if keyed:
                code=f'Set-B2PSArray {ps_quote(name)} @()'
                for item in values:
                    m=re.fullmatch(r'\[(.+)\]=(.*)',item.raw,re.S)
                    if not m: raise Unsupported('关联数组需使用 [key]=value。')
                    code+=f'\nSet-B2PSArrayItem {ps_quote(name)} {self.scalar(Token(m[1],item.line))} {self.scalar(Token(m[2],item.line))}'
                if local_array:code='Invoke-B2PSCommand @('+ps_quote('local')+','+ps_quote(name)+')\n'+code
                return code,True
            code=f'Set-B2PSArray {ps_quote(name)} {self.words(values)}'+(' -Append' if append else '')
            if local_array:code='Invoke-B2PSCommand @('+ps_quote('local')+','+ps_quote(name)+')\n'+code
            return code,True
        assignments=[]
        while tokens and (match:=self.ASSIGN.fullmatch(tokens[0].raw)):
            assignments.append((match,tokens[0]));tokens=tokens[1:]
        if not tokens: return '\n'.join(self.assignment(m,t) for m,t in assignments),True
        if any(t.kind!='word' for t in tokens): raise Unsupported('不支持该 Shell 操作符或作业控制。')
        try: name=literal(tokens[0])
        except Unsupported: name=''
        args=tokens[1:]
        if name in {'.','source','bash'}: code=self.script_command(name,args,tokens[0].line)
        else:
            if name: self.validate(name,args,tokens[0].line)
            else: self.warn(tokens[0].line,'变量指定的外部程序须有 Windows 可执行版本；python3/pip3 在 Windows 映射为 python/pip。')
            if name=='export':
                for arg in args:
                    m=re.match(r'^([A-Za-z_][A-Za-z_0-9]*)',arg.raw)
                    if m:
                        other=self.export_names.get(m[1].upper())
                        if other and other!=m[1]: raise Unsupported('不能导出仅大小写不同的 Windows 环境变量。')
                        self.export_names[m[1].upper()]=m[1]
            if name=='let':
                expressions=[self.arithmetic(literal(t)) for t in args]
                if not expressions: raise Unsupported('let 缺少表达式。')
                code='\n'.join('$b2psArithmetic='+e for e in expressions)+'\n$script:B2PSStatus=[int]($b2psArithmetic -eq 0)'
            else:
                words=self.words(tokens,assignments=name in {'export','local','declare'})
                code='$b2psCommandWords='+words+'\n$script:B2PSPreviousStatus=$script:B2PSStatus\nInvoke-B2PSCommand $b2psCommandWords'
        if assignments:
            if name in {'.','source','bash'}: raise Unsupported('子脚本前的临时赋值请单独 export 后调用。')
            setup=[]
            for m,t in assignments:
                if m[2] is not None or m[3]: raise Unsupported('临时环境赋值支持普通 NAME=value。')
                setup.append('@{ Name='+ps_quote(m[1])+'; Action={ '+self.scalar(Token(m[4],t.line))+' } }')
            # Expand command arguments against the original variables before assignments.
            lines=code.split('\n');first=lines[0];remaining='\n'.join(lines[1:])
            code=first+'\nInvoke-B2PSWithEnvironment @('+', '.join(setup)+') {\n'+self.indent(remaining)+'\n}'
        return code,False

    def pipeline(self,tokens):
        pieces=[[]];redirections=[[]];i=0;bracket=0;arithmetic=0
        while i<len(tokens):
            t=tokens[i]
            if t.raw in {'[','[['}: bracket+=1
            if t.raw in {']',']]'}: bracket-=1
            if t.raw=='((': arithmetic+=1
            if t.raw=='))': arithmetic-=1
            if not bracket and not arithmetic and t.kind=='op' and t.raw=='|': pieces.append([]);redirections.append([])
            elif not bracket and not arithmetic and t.kind=='op' and self.REDIR.fullmatch(t.raw):
                if i+1>=len(tokens): raise Unsupported('重定向缺少目标。')
                redirections[-1].extend(tokens[i:i+2]);i+=1
            else: pieces[-1].append(t)
            i+=1
        codes=[];assignment=False
        for piece,redir in zip(pieces,redirections):
            if not piece: raise Unsupported('管道缺少命令。')
            code,assignment=self.command(piece)
            if redir: code=self.redirected(code,redir)
            codes.append(code)
        if len(codes)==1: return codes[0],assignment
        return 'Invoke-B2PSPipeline -Stages @('+', '.join('{\n'+self.indent(c)+'\n}' for c in codes)+')',False

    def chain(self,tokens):
        segments=[[]];joins=[];depth=0
        for t in tokens:
            if t.raw in {'[[','((','('}: depth+=1
            if t.raw in {']]', '))', ')'}: depth-=1
            if depth==0 and t.kind=='op' and t.raw in {'&&','||'}: joins.append(t.raw);segments.append([])
            else: segments[-1].append(t)
        if any(not s for s in segments): raise Unsupported('&&/|| 缺少前后命令。')
        out=[]
        for i,segment in enumerate(segments):
            line=segment[0].line;negate=segment[0].raw=='!'
            if negate: segment=segment[1:]
            code,assignment=self.pipeline(segment)
            flags=f' -Line {line}'+(' -Required' if i==len(segments)-1 else '')+(' -Negate' if negate else '')+(' -Assignment' if assignment else '')
            step='Invoke-B2PSStep {\n'+self.indent(code)+'\n}'+flags
            if i: step='if ($script:B2PSStatus '+('-eq' if joins[i-1]=='&&' else '-ne')+' 0) {\n'+self.indent(step)+'\n}'
            out.append(step);self.commands+=1
        return '\n'.join(out)

    def nodes(self,nodes):
        out=[]
        self.functions.update(n.variable for n in nodes if n.kind=='function')
        for node in nodes:
            out.append(f'# Bash line {node.line}')
            try:
                if node.kind=='command': code=self.chain(node.tokens)
                elif node.kind=='function':
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',node.variable): raise Unsupported('函数名称无效。')
                    body=self.nodes(node.body) or '$script:B2PSStatus=0'
                    if node.redirections: body=self.redirected(body,node.redirections)
                    code=f'$script:B2PSFunctions[{ps_quote(node.variable)}] = {{\n'+self.indent(body)+'\n}\n$script:B2PSStatus=0'
                elif node.kind=='group': code=self.nodes(node.body)
                elif node.kind=='subshell':
                    code='Invoke-B2PSSubshell {\n'+self.indent(self.nodes(node.body))+'\n}'
                elif node.kind=='if':
                    parts=[]
                    for i,(condition,body) in enumerate(node.branches):
                        parts.append(('if' if i==0 else 'elseif')+' (Test-B2PSCondition {\n'+self.indent(self.nodes(condition))+'\n}) {\n'+self.indent(self.nodes(body) or '$script:B2PSStatus=0')+'\n}')
                    parts.append('else {\n'+self.indent(self.nodes(node.otherwise) or '$script:B2PSStatus=0')+'\n}');code='\n'.join(parts)
                elif node.kind=='case':
                    parts=[];value=self.scalar(node.tokens[0]);parts.append('$b2psCaseValue='+value)
                    for i,(patterns,body) in enumerate(node.cases):
                        alternatives=[t for t in patterns if t.raw!='|']
                        check=' -or '.join('($b2psCaseValue -cmatch (\'^\'+(Convert-B2PSGlob '+self.scalar(p)+')+\'$\'))' for p in alternatives)
                        parts.append(('if' if i==0 else 'elseif')+' ('+check+') {\n'+self.indent(self.nodes(body) or '$script:B2PSStatus=0')+'\n}')
                    parts.append('else { $script:B2PSStatus=0 }');code='\n'.join(parts)
                elif node.kind in {'while','until','for','for-arithmetic'}:
                    self.counter+=1;suffix=str(self.counter);status='$b2psLoopStatus'+suffix;update='';start=''
                    if node.kind=='for':
                        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',node.variable): raise Unsupported('for 变量名称无效。')
                        header=f'foreach ($b2psLoopValue{suffix} in {self.words(node.tokens)}) {{';start=f'Set-B2PSValue {ps_quote(node.variable)} $b2psLoopValue{suffix}\n'
                    elif node.kind=='for-arithmetic':
                        text=' '.join(t.raw for t in node.tokens);parts=text.split(';')
                        if len(parts)!=3: raise Unsupported('算术 for 需要 初始化;条件;更新 三段表达式。')
                        out.append('$null='+self.arithmetic(parts[0]));header='while ('+self.arithmetic(parts[1] or '1')+' -ne 0) {';update='$null='+self.arithmetic(parts[2])+'\n'
                    else: header='while ('+('-not ' if node.kind=='until' else '')+'(Test-B2PSCondition {\n'+self.indent(self.nodes(node.condition))+'\n})) {'
                    self.loop_depth+=1
                    try: body=self.nodes(node.body)
                    finally: self.loop_depth-=1
                    guarded='try {\n'+self.indent(start+body+'\n'+status+'=$script:B2PSStatus')+'\n} catch {\n'+self.indent("$kind=$_.Exception.Data['B2PSControl']\nif ($kind -notin @('break','continue')) { throw }\n$levels=[int]$_.Exception.Data['B2PSExitCode']\nif ($levels -gt 1) { $_.Exception.Data['B2PSExitCode']=$levels-1; throw }\n"+status+"=0\nif ($kind -eq 'break') { break }")+'\n}\n'+update
                    code=status+'=0\n'+header+'\n'+self.indent(guarded)+'\n}\n$script:B2PSStatus='+status
                else: raise Unsupported('尚不支持该控制结构。')
                if node.redirections and node.kind!='function': code=self.redirected(code,node.redirections)
                out.append(code)
            except (Unsupported,OSError,UnicodeError) as error:
                self.issues.append(Issue(node.line,'error',str(error)));out.append('# MANUAL REVIEW: '+' '.join(str(error).splitlines()))
        return '\n'.join(out)

    def body(self,source):
        try:
            parser=ShellParser(lex(source.replace('\r\n','\n').lstrip('\ufeff')));body=self.nodes(parser.parse())
            comments=['# '+line for t in parser.comments if not t.raw.startswith('#!') for line in t.raw[1:].splitlines()]
            return body+('\n# Original comments\n'+'\n'.join(comments) if comments else '')
        except Unsupported as error:
            match=re.search(r'第 (\d+) 行',str(error));self.issues.append(Issue(int(match[1]) if match else 1,'error',str(error)));return '# MANUAL REVIEW'

    def translate(self,source):
        if self.source_path: self.active.add(self.source_path)
        try: body=self.body(source)
        finally:
            if self.source_path: self.active.discard(self.source_path)
        preamble=['# Bash → native PowerShell conversion']
        for issue in self.issues: preamble.append(f'# {issue.level.upper()} L{issue.line}: '+' '.join(issue.message.splitlines()))
        if any(i.level=='error' for i in self.issues): preamble.append("throw 'Conversion incomplete: resolve all ERROR diagnostics and reconvert before running.'")
        if self.dependencies: preamble.append('# Required Windows programs: '+', '.join(sorted(self.dependencies)))
        config=[]
        if self.source_path: config.extend(['$script:B2PSSource='+ps_quote(str(self.source_path)),'$script:B2PSZero=$script:B2PSSource'])
        for path,child in self.bundle.items(): config.append('$script:B2PSScripts['+ps_quote(str(path))+']={\n'+self.indent(child)+'\n}')
        main='\n# Main script\ntry {\n'+self.indent(body)+'\n} catch {\n'+self.indent("if ($_.Exception.Data['B2PSControl'] -in @('exit','return')) { $script:B2PSStatus=[int]$_.Exception.Data['B2PSExitCode'] } else { $script:B2PSStatus=1; Write-B2PSOutput ($_.Exception.Message+\"`n\") -ErrorStream }")+'\n}\n# B2PS final status\nexit $script:B2PSStatus\n'
        return Result('\n'.join(preamble)+'\n\n'+RUNTIME+'\n'+NATIVE_RUNTIME+'\n'+BUILTINS+'\n'+TEXT_RUNTIME+'\n'+'\n'.join(config)+main,self.issues,self.commands)


def convert(source,source_path=None):
    return Translator(source_path).translate(source)


def convert_file(path):
    path=Path(path).resolve()
    return convert(path.read_text(encoding='utf-8-sig'),path)
