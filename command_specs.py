"""Explicit supported option sets, used for conversion-time rejection."""
import re
from shellsyntax import Unsupported

# switches, required-value options, optional-value options, long names
OPTIONS = {
    'cat': ('nbsvETA', '', '', 'number number-nonblank squeeze-blank show-ends show-tabs show-all'),
    'grep': ('ivFEnclLqohHwxrRa', 'efmABC', '', 'ignore-case invert-match fixed-strings extended-regexp line-number count quiet recursive regexp file max-count after-context before-context context'),
    'head': ('qv', 'nc', '', 'lines bytes quiet silent verbose'),
    'tail': ('qv', 'nc', '', 'lines bytes quiet silent verbose'),
    'wc': ('lwcm', '', '', 'lines words bytes chars'),
    'sort': ('rnfusb', 'kto', '', 'reverse numeric-sort ignore-case unique stable key field-separator output'),
    'uniq': ('cdui', '', '', 'count repeated unique ignore-case'),
    'cut': ('s', 'fdcb', '', 'fields delimiter characters bytes only-delimited'),
    'tr': ('dscC', '', '', 'delete squeeze-repeats complement'),
    'sed': ('nEr', 'e', 'i', 'quiet silent regexp-extended expression in-place'),
    'awk': ('', 'F', '', ''),
    'xargs': ('0rt', 'nIdP', '', 'null no-run-if-empty max-args replace delimiter max-procs'),
    'mkdir': ('p', '', '', 'parents'),
    'touch': ('', '', '', ''),
    'cp': ('rfRa', '', '', 'recursive force'),
    'mv': ('f', '', '', 'force'),
    'rm': ('rfR', '', '', 'recursive force'),
    'rmdir': ('', '', '', ''),
    'read': ('r', 'ap', '', ''),
    'ln': ('sfn', '', '', ''),
    'declare': ('aA', '', '', ''),
}


def validate_options(name, arguments):
    if name not in OPTIONS:
        return
    switches, values, optional, long = OPTIONS[name]
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        index += 1
        if arg == '--':
            break
        if arg is None or not arg.startswith('-') or arg == '-':
            continue
        if name in {'head', 'tail'} and re.fullmatch(r'-\d+', arg):
            continue
        if arg.startswith('--'):
            if arg[2:].split('=')[0] not in long.split():
                raise Unsupported(f'{name} 不支持选项 {arg}。')
            # Runtime validates long option operands; don't misclassify negative values.
            if name in {'head', 'tail'} and '=' not in arg:
                index += 1
            continue
        for position, flag in enumerate(arg[1:], 1):
            if flag in values + optional:
                if position == len(arg) - 1 and flag in values:
                    index += 1
                break
            if flag not in switches:
                raise Unsupported(f'{name} 不支持选项 -{flag}。')


def validate_sed(source):
    index = 0
    while index < len(source):
        while index < len(source) and (source[index].isspace() or source[index] == ';'):
            index += 1
        if index == len(source):
            break
        match = re.match(r'(\d+(?:,\d+)?|\$|/(?:\\.|[^/])*/)', source[index:])
        if match:
            index += match.end()
        if index >= len(source):
            raise Unsupported('sed 地址后缺少命令。')
        operation = source[index]
        index += 1
        if operation in 'dpq':
            continue
        if operation != 's' or index >= len(source):
            raise Unsupported('sed 支持 s 替换与带地址的 d/p/q；其他程序需人工适配。')
        delimiter = source[index]
        index += 1
        for _ in range(2):
            while index < len(source) and source[index] != delimiter:
                index += 2 if source[index] == '\\' else 1
            if index >= len(source):
                raise Unsupported('sed 替换表达式没有闭合。')
            index += 1
        start = index
        while index < len(source) and not source[index].isspace() and source[index] != ';':
            index += 1
        if not re.fullmatch('[gIp]*', source[start:index]):
            raise Unsupported('sed 替换标志支持 g/I/p。')


def validate_awk(source):
    printing = re.fullmatch(r'(?:(NR)\s*(==|!=|>=|<=|>|<)\s*(\d+)\s*)?\{\s*print(?:\s+(.+?))?\s*;?\s*\}', source.strip())
    summing = re.fullmatch(r'\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*\+=\s*\$\d+\s*;?\s*\}\s*END\s*\{\s*print\s+\1\s*;?\s*\}', source.strip())
    if not printing and not summing:
        raise Unsupported('awk 支持常用字段打印、NR/NF 和简单列求和；其他程序需人工适配。')
