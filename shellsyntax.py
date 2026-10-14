"""Quote-aware shell lexer and a small recursive parser. Never executes input."""
from __future__ import annotations

from dataclasses import dataclass, field
import re


class Unsupported(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    raw: str
    line: int
    kind: str = 'word'
    node: Node | None = None


def expansion_end(text: str, start: int) -> int:
    """Return the exclusive end of ${...}, $(...) or a backtick substitution."""
    if text[start] == '`':
        i = start + 1
        while i < len(text):
            if text[i] == '\\':
                i += 2
            elif text[i] == '`':
                return i + 1
            else:
                i += 1
        raise Unsupported('反引号命令替换没有闭合。')
    closing = '}' if text.startswith('${', start) else ')'
    i, depth, quote = start + 2, 1, None
    while i < len(text):
        c = text[i]
        if c == '\\' and quote != "'":
            i += 2
            continue
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if text.startswith(('${', '$('), i) or c == '`':
            i = expansion_end(text, i)
            continue
        if c in "'\"" and (quote is None or quote == c):
            quote = None if quote == c else c
        elif quote is None:
            if closing == ')' and c == '(':
                depth += 1
            elif c == closing:
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise Unsupported('变量展开或命令替换没有闭合。')


def lex(source: str, start_line: int = 1) -> list[Token]:
    tokens: list[Token] = []
    i, line = 0, start_line
    operators = ('&>>', '<<<', '<<-', ';;', '&&', '||', '&>', '>>', '<<', '>&', '<&', '((', '))', '|', ';', '>', '<', '&', '(', ')')
    pending_here = []
    while i < len(source):
        c = source[i]
        if c in ' \t\r':
            i += 1
            continue
        if source.startswith(('\\\n', '\\\r\n'), i):
            i += 3 if source.startswith('\\\r\n', i) else 2
            line += 1
            continue
        if c == '\n':
            tokens.append(Token('\n', line, 'op'))
            line += 1
            i += 1
            for position, strip_tabs in pending_here:
                delimiter_token = tokens[position]
                delimiter = delimiter_token.raw.replace("'", '').replace('"', '').replace('\\', '')
                quoted = any(c in delimiter_token.raw for c in "'\"\\")
                body = []
                while i < len(source):
                    end = source.find('\n', i)
                    end = len(source) if end < 0 else end + 1
                    value = source[i:end]
                    comparable = value.lstrip('\t') if strip_tabs else value
                    i = end
                    line += value.count('\n')
                    if comparable.rstrip('\r\n') == delimiter:
                        break
                    body.append(comparable)
                else:
                    raise Unsupported(f'第 {delimiter_token.line} 行：here-document 缺少结束标记 {delimiter}。')
                tokens[position] = Token(''.join(body), delimiter_token.line, 'here-literal' if quoted else 'here-expand')
            pending_here.clear()
            continue
        if c == '#':
            end = source.find('\n', i)
            end = len(source) if end < 0 else end
            tokens.append(Token(source[i:end], line, 'comment'))
            i = end
            continue
        numbered = re.match(r'\d+(?:>>|>&|<&|>|<)', source[i:])
        op = numbered[0] if numbered else next((o for o in operators if source.startswith(o, i)), None)
        if op:
            tokens.append(Token(op, line, 'op'))
            i += len(op)
            continue
        start, token_line, quote = i, line, None
        while i < len(source):
            c = source[i]
            if c == '\\' and quote != "'":
                if i + 1 == len(source):
                    raise Unsupported(f'第 {line} 行：末尾反斜杠缺少续行内容。')
                if source.startswith('\\\r\n', i):
                    line += 1
                    i += 3
                else:
                    line += source[i + 1] == '\n'
                    i += 2
                continue
            if quote == "'":
                if c == "'":
                    quote = None
                line += c == '\n'
                i += 1
                continue
            if source.startswith(('${', '$('), i) or c == '`':
                end = expansion_end(source, i)
                line += source[i:end].count('\n')
                i = end
                continue
            if c in "'\"" and (quote is None or quote == c):
                quote = None if quote == c else c
                i += 1
                continue
            if quote is None and (c in ' \t\r\n' or any(source.startswith(o, i) for o in operators)):
                break
            line += c == '\n'
            i += 1
        if quote:
            raise Unsupported(f'第 {token_line} 行：引号没有闭合。')
        tokens.append(Token(source[start:i], token_line))
        if len(tokens) >= 2 and tokens[-2].raw in {'<<', '<<-'}:
            pending_here.append((len(tokens) - 1, tokens[-2].raw == '<<-'))
    if pending_here:
        raise Unsupported('here-document 缺少正文和结束标记。')
    return tokens


@dataclass
class Node:
    kind: str
    line: int
    tokens: list[Token] = field(default_factory=list)
    condition: list[Node] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    branches: list[tuple[list[Node], list[Node]]] = field(default_factory=list)
    otherwise: list[Node] = field(default_factory=list)
    variable: str = ''
    cases: list[tuple[list[Token], list[Node]]] = field(default_factory=list)
    redirections: list[Token] = field(default_factory=list)


class ShellParser:
    RESERVED = {'then', 'elif', 'else', 'fi', 'do', 'done', 'esac', '}'}

    def __init__(self, tokens: list[Token]):
        self.comments = [t for t in tokens if t.kind == 'comment']
        self.tokens = [t for t in tokens if t.kind != 'comment']
        self.index = 0

    def at(self, words: set[str]) -> bool:
        return self.index < len(self.tokens) and self.tokens[self.index].raw in words

    def separators(self):
        while self.at({'\n', ';'}):
            self.index += 1

    def expect(self, word: str):
        self.separators()
        if not self.at({word}):
            line = self.tokens[self.index].line if self.index < len(self.tokens) else (self.tokens[-1].line if self.tokens else 1)
            raise Unsupported(f'第 {line} 行：控制结构缺少 {word}。')
        self.index += 1

    def parse(self, stops: set[str] | None = None) -> list[Node]:
        nodes: list[Node] = []
        stops = stops or set()
        self.separators()
        while self.index < len(self.tokens) and not self.at(stops):
            token = self.tokens[self.index]
            if token.raw in self.RESERVED:
                raise Unsupported(f'第 {token.line} 行：{token.raw} 没有匹配的控制结构。')
            lookahead = [t.raw for t in self.tokens[self.index:self.index + 4]]
            if token.raw == 'function' or (len(lookahead) >= 3 and lookahead[1:3] == ['(', ')']):
                self.index += 1
                if token.raw == 'function':
                    if self.index >= len(self.tokens):
                        raise Unsupported('function 缺少函数名。')
                    name = self.tokens[self.index].raw
                    self.index += 1
                else:
                    name = token.raw
                if self.at({'('}):
                    self.expect('(')
                    self.expect(')')
                self.expect('{')
                body = self.parse({'}'})
                self.expect('}')
                nodes.append(Node('function', token.line, variable=name, body=body))
            elif token.raw == '{':
                self.index += 1
                body = self.parse({'}'})
                self.expect('}')
                nodes.append(Node('group', token.line, body=body))
            elif token.raw == '(':
                self.index += 1
                body = self.parse({')'})
                self.expect(')')
                nodes.append(Node('subshell', token.line, body=body))
            elif token.raw == 'case':
                self.index += 1
                if self.index >= len(self.tokens):
                    raise Unsupported('case 缺少匹配值。')
                value = self.tokens[self.index]
                self.index += 1
                self.expect('in')
                node = Node('case', token.line, tokens=[value])
                self.separators()
                while not self.at({'esac'}):
                    if self.index >= len(self.tokens):
                        raise Unsupported(f'第 {token.line} 行：case 缺少 esac。')
                    patterns = []
                    if self.at({'('}):
                        self.index += 1
                    while self.index < len(self.tokens) and not self.at({')'}):
                        patterns.append(self.tokens[self.index])
                        self.index += 1
                    self.expect(')')
                    node.cases.append((patterns, self.parse({';;', 'esac'})))
                    if self.at({';;'}):
                        self.index += 1
                    self.separators()
                self.expect('esac')
                nodes.append(node)
            elif token.raw == 'if':
                self.index += 1
                condition = self.parse({'then'})
                self.expect('then')
                body = self.parse({'elif', 'else', 'fi'})
                node = Node('if', token.line, branches=[(condition, body)])
                while self.at({'elif'}):
                    self.index += 1
                    condition = self.parse({'then'})
                    self.expect('then')
                    node.branches.append((condition, self.parse({'elif', 'else', 'fi'})))
                if self.at({'else'}):
                    self.index += 1
                    node.otherwise = self.parse({'fi'})
                self.expect('fi')
                if any(not condition for condition, _ in node.branches):
                    raise Unsupported(f'第 {token.line} 行：if 缺少条件命令。')
                nodes.append(node)
            elif token.raw in {'while', 'until'}:
                self.index += 1
                condition = self.parse({'do'})
                self.expect('do')
                body = self.parse({'done'})
                self.expect('done')
                if not condition:
                    raise Unsupported(f'第 {token.line} 行：循环缺少条件命令。')
                nodes.append(Node(token.raw, token.line, condition=condition, body=body))
            elif token.raw == 'for':
                self.index += 1
                if self.at({'(('}):
                    self.index += 1
                    parts = []
                    while self.index < len(self.tokens) and not self.at({'))'}):
                        parts.append(self.tokens[self.index])
                        self.index += 1
                    self.expect('))')
                    self.expect('do')
                    body = self.parse({'done'})
                    self.expect('done')
                    nodes.append(Node('for-arithmetic', token.line, tokens=parts, body=body))
                    nodes[-1]=self.postfix(nodes[-1])
                    self.separators()
                    continue
                header = self.simple()
                if not header or (len(header) > 1 and header[1].raw != 'in'):
                    raise Unsupported(f'第 {token.line} 行：for 目前支持 for 名称 in 值...; do ...; done。')
                self.expect('do')
                body = self.parse({'done'})
                self.expect('done')
                values = header[2:] if len(header) > 1 else [Token('"$@"', token.line)]
                nodes.append(Node('for', token.line, tokens=values, variable=header[0].raw, body=body))
            else:
                nodes.append(Node('command', token.line, tokens=self.simple()))
            if nodes[-1].kind != 'command':
                nodes[-1]=self.postfix(nodes[-1])
            self.separators()
        return nodes

    def postfix(self,node):
        while self.index<len(self.tokens) and re.fullmatch(r'(?:[012])?(?:>>?|<|>&|<&)|&>>?|<<<|<<-?',self.tokens[self.index].raw):
            node.redirections.append(self.tokens[self.index]);self.index+=1
            if self.index>=len(self.tokens):raise Unsupported('重定向缺少目标。')
            node.redirections.append(self.tokens[self.index]);self.index+=1
        if self.at({'&&','||','|'}):
            return Node('command',node.line,tokens=[Token('__compound__',node.line,'block',node)]+self.simple())
        return node

    def simple(self) -> list[Token]:
        result: list[Token] = []
        nesting = 0
        while self.index < len(self.tokens):
            token = self.tokens[self.index]
            if nesting==0 and token.raw in {'{','('} and result and result[-1].raw in {'&&','||','|'}:
                self.index+=1
                closing='}' if token.raw=='{' else ')'
                body=self.parse({closing})
                self.expect(closing)
                block=Node('group' if token.raw=='{' else 'subshell',token.line,body=body)
                result.append(Token('__compound__',token.line,'block',block))
                continue
            if nesting == 0 and token.raw in {';;', 'esac', ')', '}'}:
                break
            if token.raw in {'(', '(('}:
                nesting += 1
            elif token.raw in {')', '))'}:
                nesting -= 1
            if token.kind == 'op' and token.raw in {'\n', ';'} and nesting == 0:
                if token.raw == '\n' and result and result[-1].raw in {'&&', '||', '|'}:
                    self.index += 1
                    continue
                break
            result.append(token)
            self.index += 1
        return result
