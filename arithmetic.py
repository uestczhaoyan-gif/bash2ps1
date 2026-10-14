"""Parse Bash integer expressions into data; never eval host-language code."""
import re
from shellsyntax import Unsupported


class Arithmetic:
    LEVELS = {
        ',': 1, '=': 2, '+=': 2, '-=': 2, '*=': 2, '/=': 2, '%=': 2,
        '<<=': 2, '>>=': 2, '&=': 2, '^=': 2, '|=': 2,
        '||': 4, '&&': 5, '|': 6, '^': 7, '&': 8,
        '==': 9, '!=': 9, '<': 10, '<=': 10, '>': 10, '>=': 10,
        '<<': 11, '>>': 11, '+': 12, '-': 12, '*': 13, '/': 13, '%': 13, '**': 14,
    }
    PATTERN = re.compile(r'\s*(\$?[A-Za-z_][A-Za-z_0-9]*|(?:\d+#)?[0-9][A-Za-z_0-9]*|<<=|>>=|\*\*|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|[+*/%&^|=-]=|[()+*/%&^|~!<>=?:,\[\]-])')

    def __init__(self, text):
        self.tokens = []
        offset = 0
        while offset < len(text):
            if not text[offset:].strip():
                break
            match = self.PATTERN.match(text, offset)
            if not match:
                raise Unsupported('不支持该算术表达式；支持整数、变量、赋值和常用 C 风格运算符。')
            self.tokens.append(match[1])
            offset = match.end()
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else ''

    def take(self):
        token = self.peek()
        self.index += 1
        return token

    def expect(self, value):
        if self.take() != value:
            raise Unsupported(f'算术表达式缺少 {value}。')

    def expression(self, minimum=1):
        token = self.take()
        if not token:
            raise Unsupported('算术表达式为空或缺少操作数。')
        if token in {'+', '-', '!', '~', '++', '--'}:
            left = [token + 'pre', self.expression(14)]
        elif token == '(':
            left = self.expression()
            self.expect(')')
        elif re.fullmatch(r'\$?[A-Za-z_][A-Za-z_0-9]*', token):
            left = ['var', token.lstrip('$')]
            if self.peek() == '[':
                self.take()
                left.append(self.expression())
                self.expect(']')
        elif token[0].isdigit():
            left = ['number', token]
        else:
            raise Unsupported('算术表达式缺少有效操作数。')
        while True:
            op = self.peek()
            if op in {'++', '--'}:
                self.take()
                left = [op + 'post', left]
                continue
            if op == '?' and minimum <= 3:
                self.take()
                middle = self.expression()
                self.expect(':')
                left = ['?:', left, middle, self.expression(3)]
                continue
            priority = self.LEVELS.get(op, 0)
            if priority < minimum:
                break
            self.take()
            right = self.expression(priority if priority in {2, 14} else priority + 1)
            left = [op, left, right]
        return left

    def parse(self):
        result = self.expression() if self.tokens else ['number', '0']
        if self.peek():
            raise Unsupported('算术表达式中存在无法解析的内容。')
        return result


def parse_arithmetic(text):
    return Arithmetic(text).parse()
