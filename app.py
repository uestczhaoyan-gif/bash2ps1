"""Chinese desktop UI; Python standard library only."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from converter import Result, convert, convert_file


EXAMPLE = '''#!/usr/bin/env bash
# 示例：默认值、命令替换、条件判断和多行输出
set -euo pipefail
PROJECT="${PROJECT:-demo project}"
export APP_MODE=development
mkdir -p "$PROJECT"
cd "$PROJECT"
STAMP="$(date -Is)"
printf 'APP_MODE=%s\\ncreated_at=%s\\n' "$APP_MODE" "$STAMP" > .env
if test -f .env; then
  echo "配置已生成：$STAMP"
fi
git init && echo "Git 初始化完成"
npm --version || echo "请先安装 Node.js"
'''


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.result: Result | None = None
        self.source_path: Path | None = None
        self.dirty = True
        self.issue_rows = []
        root.title('Bash → PowerShell · 1.0.0')
        width = min(1180, root.winfo_screenwidth() - 60)
        height = min(790, root.winfo_screenheight() - 100)
        root.geometry(f'{width}x{height}')
        root.minsize(850, 600)
        root.configure(bg='#f2f4f8')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#f2f4f8')
        style.configure('TLabel', background='#f2f4f8', font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 20, 'bold'), foreground='#172b4d')
        style.configure('Sub.TLabel', foreground='#526278')
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=(12, 7))
        style.configure('Accent.TButton', background='#2167c9', foreground='white')
        style.map('Accent.TButton', background=[('active', '#1852a6')])
        style.configure('Treeview', rowheight=29, font=('Microsoft YaHei UI', 9))
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 9, 'bold'))
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Bash → PowerShell', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='粘贴步骤，检查转换，带走可运行的脚本。兼容 PowerShell 5.1 / 7。', style='Sub.TLabel').pack(anchor='w', pady=(4, 14))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill='x', pady=(0, 12))
        ttk.Button(toolbar, text='打开 .sh 文件', command=self.open_file).pack(side='left')
        ttk.Button(toolbar, text='载入示例', command=self.load_example).pack(side='left', padx=8)
        ttk.Button(toolbar, text='清空', command=self.clear).pack(side='left')
        ttk.Button(toolbar, text='转换  Ctrl+Enter', style='Accent.TButton', command=self.run_convert).pack(side='right')
        panes = ttk.Panedwindow(outer, orient='horizontal')
        panes.pack(fill='both', expand=True)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=1)
        ttk.Label(left, text='01  Bash 输入').pack(anchor='w', pady=(0, 7))
        ttk.Label(right, text='02  PowerShell 预览').pack(anchor='w', pady=(0, 7))
        self.input = self.editor(left, '#ffffff')
        self.output = self.editor(right, '#f9fbff', readonly=True)
        self.output.tag_configure('comment', foreground='#5f7c63')
        self.output.tag_configure('error', foreground='#c03336', background='#fff0f0')
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(12, 8))
        self.status = tk.StringVar(value='输入 Bash 命令后点击“转换”。输入内容不会被执行。')
        ttk.Label(actions, textvariable=self.status).pack(side='left')
        self.save_button = ttk.Button(actions, text='保存 .ps1', command=self.save)
        self.save_button.pack(side='right')
        self.copy_button = ttk.Button(actions, text='复制脚本', command=self.copy)
        self.copy_button.pack(side='right', padx=8)
        self.copy_button.configure(state='disabled')
        self.save_button.configure(state='disabled')
        ttk.Label(outer, text='03  转换诊断 · 双击定位输入行', style='Sub.TLabel').pack(anchor='w', pady=(5, 6))
        diagnostic_frame = ttk.Frame(outer)
        diagnostic_frame.pack(fill='x')
        self.diagnostics = ttk.Treeview(diagnostic_frame, columns=('level', 'line', 'message'), show='headings', height=4)
        for column, text, width in [('level', '级别', 76), ('line', 'Bash 行', 76), ('message', '说明', 880)]:
            self.diagnostics.heading(column, text=text)
            self.diagnostics.column(column, width=width, stretch=column == 'message')
        self.diagnostics.pack(side='left', fill='x', expand=True)
        scroll = ttk.Scrollbar(diagnostic_frame, command=self.diagnostics.yview)
        scroll.pack(side='right', fill='y')
        self.diagnostics.configure(yscrollcommand=scroll.set)
        self.diagnostics.tag_configure('error', foreground='#b4232d')
        self.diagnostics.tag_configure('warning', foreground='#9a6510')
        self.diagnostics.bind('<Double-1>', self.go_to_issue)
        ttk.Label(outer, text='支持常用命令、函数、数组、算术、条件循环和重定向。打开 .sh 自动打包子脚本；转换不会执行输入。', style='Sub.TLabel').pack(anchor='w', pady=(9, 0))
        root.bind('<Control-Return>', lambda event: self.run_convert())
        root.bind('<Control-o>', lambda event: self.open_file())
        root.bind('<Control-s>', lambda event: self.save())
        self.input.bind('<<Modified>>', self.on_modified)
        self.input.tag_configure('issue', background='#fff1d8')
        self.input.focus_set()

    def editor(self, parent, color, readonly=False):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, padx=(0, 8))
        editor = tk.Text(frame, wrap='none', undo=not readonly, bg=color, fg='#23344d',
                         insertbackground='#2167c9', selectbackground='#cfe3ff',
                         font=('Consolas', 11), padx=12, pady=12, bd=0, relief='flat',
                         width=35, height=6, tabs=('4c',))
        vertical = ttk.Scrollbar(frame, orient='vertical', command=editor.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=editor.xview)
        editor.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        editor.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        if readonly:
            editor.configure(state='disabled')
        return editor

    def on_modified(self, event=None):
        if not self.input.edit_modified():
            return
        self.input.edit_modified(False)
        self.dirty = True
        self.copy_button.configure(state='disabled')
        self.save_button.configure(state='disabled')
        self.status.set('输入已更改，请重新转换。')
        self.input.tag_remove('issue', '1.0', 'end')

    def run_convert(self):
        # Discard a queued Modified event for the exact text being converted.
        self.input.edit_modified(False)
        source = self.input.get('1.0', 'end-1c')
        if not source.strip():
            self.status.set('请先粘贴 Bash 命令或载入示例。')
            return
        try:
            result = convert(source, self.source_path)
        except Exception as error:
            messagebox.showerror('转换失败', str(error), parent=self.root)
            return
        self.result, self.dirty = result, False
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', result.script)
        for number, line in enumerate(result.script.splitlines(), 1):
            if line.startswith('#'):
                self.output.tag_add('error' if '# ERROR' in line else 'comment', f'{number}.0', f'{number}.end')
        self.output.configure(state='disabled')
        if not result.errors and '# Main script' in result.script:
            first_step = result.script[:result.script.index('# Main script')].count('\n') + 1
            self.output.yview(f'{first_step}.0')
        self.diagnostics.delete(*self.diagnostics.get_children())
        self.issue_rows = result.issues
        for index, issue in enumerate(result.issues):
            self.diagnostics.insert('', 'end', iid=str(index), values=('待处理' if issue.level == 'error' else '提示', issue.line, issue.message), tags=(issue.level,))
        if not result.issues:
            self.diagnostics.insert('', 'end', values=('通过', '—', '已完成转换；运行前核对路径和外部程序。'))
        if result.errors:
            self.status.set(f'{len(result.errors)} 项待处理 · 脚本已加停止保护，请修正后重新转换。')
        else:
            self.status.set(f'已转换 {result.commands} 条命令 · {len(result.warnings)} 条提示')
        self.copy_button.configure(state='normal')
        self.save_button.configure(state='normal')

    def replace_input(self, source, path: Path | None = None):
        self.source_path = path
        self.root.title('Bash → PowerShell · ' + (path.name if path else '1.0.0'))
        self.input.delete('1.0', 'end')
        self.input.insert('1.0', source)
        self.root.update_idletasks()
        self.run_convert()
        self.input.edit_modified(False)

    def load_example(self):
        self.replace_input(EXAMPLE)

    def clear(self):
        self.source_path = None
        self.root.title('Bash → PowerShell · 1.0.0')
        self.input.delete('1.0', 'end')
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.configure(state='disabled')
        self.diagnostics.delete(*self.diagnostics.get_children())
        self.result = None
        self.status.set('输入 Bash 命令后点击“转换”。输入内容不会被执行。')
        self.copy_button.configure(state='disabled')
        self.save_button.configure(state='disabled')

    def open_file(self):
        path = filedialog.askopenfilename(parent=self.root, title='打开 Bash 脚本', filetypes=[('Bash / 文本文件', '*.sh *.bash *.txt'), ('所有文件', '*.*')])
        if path:
            try:
                self.replace_input(Path(path).read_text(encoding='utf-8-sig'), Path(path))
            except (OSError, UnicodeError) as error:
                messagebox.showerror('无法打开', '请使用 UTF-8 编码的文本文件。\n\n' + str(error), parent=self.root)

    def copy(self):
        if self.result and not self.dirty:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result.script)
            self.status.set('脚本已复制。' + ('仍有待处理项，停止保护已保留。' if self.result.errors else ''))

    def save(self):
        if not self.result or self.dirty:
            self.status.set('请先转换当前输入，再保存。')
            return
        filename = self.source_path.with_suffix('.ps1').name if self.source_path else 'converted.ps1'
        path = filedialog.asksaveasfilename(parent=self.root, title='保存 PowerShell 脚本', defaultextension='.ps1', initialfile=filename, filetypes=[('PowerShell 脚本', '*.ps1')])
        if path:
            try:
                # UTF-8 BOM is necessary for Chinese in Windows PowerShell 5.1.
                Path(path).write_text(self.result.script, encoding='utf-8-sig', newline='\r\n')
                self.status.set('已保存：' + path)
            except OSError as error:
                messagebox.showerror('保存失败', str(error), parent=self.root)

    def go_to_issue(self, event=None):
        selection = self.diagnostics.selection()
        if selection and selection[0].isdigit():
            issue = self.issue_rows[int(selection[0])]
            self.input.tag_remove('issue', '1.0', 'end')
            self.input.tag_add('issue', f'{issue.line}.0', f'{issue.line}.end')
            self.input.see(f'{issue.line}.0')
            self.input.mark_set('insert', f'{issue.line}.0')
            self.input.focus_set()


def enable_dpi_awareness():
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def gui_main():
    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


def main():
    parser = argparse.ArgumentParser(description='Bash → PowerShell 桌面转换器；可选命令行入口。')
    parser.add_argument('input', nargs='?', type=Path, help='Bash 文件；不指定时打开桌面窗口')
    parser.add_argument('-o', '--output', type=Path, help='输出 .ps1 文件')
    args = parser.parse_args()
    if args.input:
        try:
            result = convert_file(args.input)
            if args.output:
                args.output.write_text(result.script, encoding='utf-8-sig', newline='\r\n')
            else:
                print(result.script)
            for issue in result.issues:
                print(f'{issue.level.upper()} L{issue.line}: {issue.message}', file=sys.stderr)
            return 2 if result.errors else 0
        except (OSError, UnicodeError) as error:
            print(str(error), file=sys.stderr)
            return 1
    if args.output:
        parser.error('-o 需要同时指定输入文件')
    return gui_main()


if __name__ == '__main__':
    raise SystemExit(main())
