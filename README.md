# bash2ps1 — Bash → PowerShell

[简体中文](#简体中文) · [English](#english)

**把常见 Bash 安装、配置和构建步骤，转换为 Windows PowerShell 5.1 / PowerShell 7 可运行的脚本。**

**Convert common Bash setup, configuration, and build steps into scripts for Windows PowerShell 5.1 and PowerShell 7.**

本地桌面工具，提供粘贴、预览、诊断定位、复制和保存功能。转换不联网、不执行输入。不能可靠转换的语法会生成明确诊断和停止保护。

A local desktop utility with paste, preview, source-line diagnostics, copy, and save. Conversion runs offline and never executes the input. Unsupported syntax produces explicit diagnostics and an execution guard.

![Desktop interface / 桌面界面](docs/screenshot.png)

## 简体中文

## 打开与使用

1. 下载或克隆项目后，双击 `Launch.cmd`。本机也可使用已创建的 **Bash 转 PowerShell** 桌面快捷方式。
2. 在左侧粘贴 Bash 命令，或选择“打开 .sh 文件”。“载入示例”可用于试用。
3. 点击“转换”或按 **Ctrl+Enter**。
4. 查看下方诊断；双击诊断会定位到 Bash 输入行。
5. 点击“复制脚本”或“保存 .ps1”。修改输入后，需要重新转换才能复制或保存。

保存文件使用 UTF-8 BOM，以便 Windows PowerShell 5.1 正确读取中文。输出脚本兼容 Windows PowerShell 5.1 与 PowerShell 7。相对路径以运行时的当前目录为基准；在所需目录中运行，例如：

```powershell
.\converted.ps1
```

运行桌面工具需要 **Python 3.10+ 和 Tkinter**，本机已具备。没有第三方运行依赖。也可直接运行：

```powershell
python .\app.py
```

可运行 `CreateShortcut.ps1` 创建指向当前项目的桌面快捷方式。可选安装方式：`python -m pip install .`，之后运行 `bash2ps1-gui`。

## 支持范围（0.2.0）

| Bash 步骤 | 转换方式 |
| --- | --- |
| `NAME=value`、`export`、`unset` | 保存 Bash 变量；导出为进程环境变量 |
| `$NAME`、`${NAME}`、`$?`、`$0`、`$1`、`~` | 普通变量、退出码、脚本位置、位置参数、用户目录 |
| `${NAME:-value}`、`${NAME:?message}` 等 | 嵌套默认值、替代值、赋默认值和必填检查；按需展开 |
| `$()`、反引号 | 捕获文本输出、去掉末尾换行，隔离目录与变量更改 |
| `if/elif/else`、`while/until`、列表 `for`、`!` | 条件判断、重试循环、嵌套代码块和条件取反 |
| 单/双引号、转义、反斜杠续行、注释、分号 | 按 Bash 引号边界解析 |
| `&&`、`\|\|` | 按上一条步骤的成功或失败决定后续步骤，支持 5.1 |
| `set -e/-u/-a`、对应 `+` 选项、`set -o pipefail` | 失败停止、未定义变量检查、自动导出、管道退出码 |
| 命令前的 `NAME=value command` | 临时设置环境变量，执行后恢复 |
| `cd`、`pwd`、`mkdir -p`、`touch` | 目录与文件操作；touch 保留已有内容 |
| `cp`、`mv`、`rm` | PowerShell 文件命令；支持部分递归/强制选项 |
| `echo`、多占位符 `printf` | `%s/%d/%i/%%`、换行/制表转义；printf 文件输出保留精确字节 |
| `sleep`、`date -Is`、`dirname`、`basename` | PowerShell/.NET 原生命令，无需安装 Unix 工具 |
| `find` | 单路径、深度、文件/目录类型、名称匹配；输出 Windows 绝对路径 |
| `. ./.env`、`source helper.sh`、`bash child.sh` | 读取环境赋值；文件入口递归打包静态子脚本 |
| `cat`、`grep`、`head`、`tail`、`wc -l` | UTF-8 文本处理，支持这些命令之间的文本管道 |
| `> file`、`>> file` | 支持已转换文本命令的重定向，UTF-8 无 BOM、LF 换行 |
| `test`、`[ ... ]` | 简单文件判断、字符串判断、整数比较 |
| `git`、`python`、`pip`、`npm`、`node` 等 | 调用真实外部程序，保留参数并检查退出码 |
| `curl`、`wget`、`tar` 等 | 调用真实外部程序；不会调用 PowerShell 同名别名 |

输出脚本包含少量辅助函数，用于变量、退出码、Windows 参数引用和 UTF-8 写入。Python `-c` 等参数中的双引号、空参数、带空格及末尾反斜杠的参数，已在 5.1 和 7 中实际验证。

## 诊断含义与边界

- **待处理（ERROR）**：不能可靠转换。输出脚本顶部会加入 `throw`，在执行任何步骤之前停止。修正输入后重新转换。
- **提示（WARNING）**：可生成脚本，但某些行为有差异，例如正则表达式、未加引号变量的拆分、文件复制覆盖或外部程序可用性。提示也会写入脚本注释。

这是面向安装、配置、构建等**常见步骤**的转换器，不是完整 Bash 编译器。仍会将以下内容标为待处理：`case`、函数、算术展开、数组、参数切片、`$@/$*`、here-document、后台任务、显式子 Shell、输入和错误重定向、命令参数中的未加引号通配符、复杂 Unix 文本工具、`sudo`/Linux 包管理器、`chmod/chown` 等。列表 `for` 不实施 Bash 单词拆分或文件通配展开。

Unix 的 `/home/...`、`/tmp/...`、`/dev/null` 等绝对路径不会自动映射到 Windows。`PATH` 的冒号分隔和 Unix 路径也不会猜测转换。外部程序需要在 Windows 中安装并能通过 PATH 找到；本工具不会安装程序。Windows 环境变量不区分大小写。

`grep` 无匹配时保留退出码 1，`pipefail` 使用最右侧失败步骤的退出码；复杂正则需检查，固定字符串优先使用 `grep -F`。`wc -l` 按文本行统计，末尾没有换行时可能与 Bash 不同。二进制输出、外部程序管道及外部程序 `>` 重定向会阻止转换；下载文件建议使用 `curl -o`。

Windows `.cmd/.bat` 参数中出现双引号、`%`、`!` 或换行时会阻止转换或在运行时停止，避免批处理再次解释参数。临时环境赋值与同一命令中的变量引用组合，需要人工改写其展开顺序。未加引号变量按单个字符串传递；本工具不实施 Bash 的单词拆分。

`&&/||` 保留步骤间的成功与失败分支；生成脚本不主动调用 `exit`，最后一步失败且未设置 `set -e` 时，PowerShell 进程退出码不保证与 Bash 脚本一致。需要作为 CI 进程使用时，应检查最终 `$script:B2PSStatus` 并自行决定 `exit`。

## 转换整个脚本及子脚本

请用“打开 .sh 文件”选择原文件。文件入口会解析 `bash scripts/child.sh` 或 `source helper.sh`，递归读取同一项目中的静态子脚本并嵌入一个 `.ps1`，无需 Bash。`bash child.sh` 仅继承已导出的变量，执行后恢复父脚本目录和环境；`source helper.sh` 共享本地变量。

打开文件时 `$0` 对应原 `.sh` 路径，因此 `cd "$(dirname "$0")/.."` 能定位原项目。输出可以保存到其他目录；原项目搬家后需重新转换。纯粘贴模式缺少文件位置，涉及子脚本时会提示改用文件入口，不会生成缺少子脚本的半成品。

`.env` 在脚本运行时读取，转换时不会读取或嵌入秘密。支持 `NAME=value`、引号、普通变量引用、注释和 `export`；`set -a` 会自动导出。复杂默认表达式、命令替换或其他 Shell 语句会在运行时明确报错。`.sh/.bash` 的 source 按子脚本转换，其他 source 文件按环境赋值文件读取。

`find` 支持 `-mindepth/-maxdepth/-type d或f/-name/-iname`，结果按名称排序。`date` 支持 ISO 时间和常见格式，`printf` 支持 `%s/%d/%i/%%`；文本管道和命令替换按文本行处理，独立控制台输出的无末尾换行 printf 会显示为一行。无法无损处理的二进制管道仍会阻止转换。

原始 Qwen 工作流位于 `tests/fixtures/scripts/`。回归测试用本地模拟程序代替下载和训练，验证实际转换后的完整流程；真实训练仍需要原项目的 Python 环境、依赖和数据。

## 可选命令行入口

```powershell
python .\app.py .\examples\setup.sh -o .\converted.ps1
```

没有 `-o` 时输出脚本到标准输出。诊断写入标准错误。返回码：`0` 转换完成，`2` 存在待处理项，`1` 文件读取或写入失败。

## 验证

```powershell
python -m unittest discover -s tests -v
```

测试覆盖引号、变量、保护机制和两种 PowerShell 的实际执行，包括中文文件、带空格路径、UTF-8 重定向、touch 不截断、条件连接、外部退出码、临时环境恢复及外部参数传递。测试只在项目的 `.test-work` 临时子目录操作文件。

语法参考：[Bash 手册](https://www.gnu.org/software/bash/manual/bash.html)、[PowerShell 参数解析](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing)、[PowerShell 条件连接运算符](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_pipeline_chain_operators)。

## English

### What it does

`bash2ps1` translates common Bash command sequences into self-contained PowerShell scripts. It is intended for Windows users following Bash-oriented setup instructions. The desktop interface is in Chinese; this guide describes each action in English.

The converter parses quote boundaries and operators instead of blindly replacing command names. Generated scripts include helper functions for Bash-style variables, step status, temporary environment variables, Windows native arguments, and UTF-8 text output. Conversion never runs the pasted commands or makes network requests.

### Quick start

Requires **Python 3.10+ with Tkinter on Windows**. There are no third-party runtime dependencies.

```powershell
git clone https://github.com/uestczhaoyan-gif/bash2ps1.git
cd bash2ps1
python .\app.py
```

You can also double-click `Launch.cmd`. Run `CreateShortcut.ps1` to create a desktop shortcut for your local checkout. Optional package installation:

```powershell
python -m pip install .
bash2ps1-gui
```

1. Paste your Bash commands into the left editor, or use **打开 .sh 文件** (Open file).
2. Select **载入示例** (Load example) to try the included example.
3. Click **转换** (Convert), or press **Ctrl+Enter**.
4. Review the diagnostics. Double-click an issue to locate its source line.
5. Use **复制脚本** (Copy script) or **保存 .ps1** (Save script).

Changing the input disables copy and save until the new text is converted. Saved scripts use UTF-8 with a BOM so Windows PowerShell 5.1 can read Chinese correctly. Relative paths resolve from your current working directory when you run the resulting script.

### Supported steps

| Bash feature | Translation |
| --- | --- |
| Assignments, `export`, `unset` | Case-sensitive local variables and Windows process environment |
| `$NAME`, `${NAME}`, `$?`, `$0`, `$1`, `~` | Values, status, source path, arguments, user directory |
| `${NAME:-value}`, `${NAME:?message}` | Lazy nested defaults, alternatives, assignment and required checks |
| `$()`, backticks, `if`, `while`, `until`, list `for`, `!` | Text capture, subshell isolation, conditions and loops |
| Quotes, escapes, continuations, comments, semicolons | Quote-aware parsing |
| `&&`, `\|\|` | Success/failure branches compatible with PowerShell 5.1 |
| `set -e/-u/-a`, corresponding `+` options, `pipefail` | Failure handling, undefined values, automatic export and pipeline status |
| `NAME=value command` | Temporary process environment, restored afterward |
| `cd`, `pwd`, `mkdir`, `touch`, `cp`, `mv`, `rm` | Directory/file operations with selected options |
| `echo`, multi-placeholder `printf` | Text output and exact printf file bytes |
| `sleep`, `date`, `dirname`, `basename`, common `find` options | Native PowerShell/.NET implementations |
| `. ./.env`, `source helper.sh`, `bash child.sh` | Assignment-file loading and embedded script dependencies |
| `cat`, `grep`, `head`, `tail`, `wc -l` | UTF-8 text processing and supported text pipelines |
| `>`, `>>` | Text-only output redirection, UTF-8 without BOM and LF line endings |
| `test`, `[ ... ]` | Simple file, string, and integer tests |
| `git`, `python`, `npm`, `node`, `curl`, and others | Actual external programs with quoted arguments and exit-status checks |

### Diagnostics and limitations

**ERROR / 待处理** means the converter cannot preserve the operation reliably. A `throw` guard is placed before all generated steps. Fix the input and convert again before running the script.

**WARNING / 提示** identifies a behavior difference that needs review. Warnings also appear as comments in the saved script.

This is a practical command-step converter, not a complete Bash compiler. Remaining unsupported constructs include `case`, functions, arithmetic, arrays, parameter slicing, `$@/$*`, here-documents, background jobs, explicit subshells, input/error redirection, unquoted wildcard command arguments, Unix-only package managers and permission operations, and complex text tools such as `sed` and `awk`. List `for` loops do not perform shell word splitting or filename expansion.

Unix absolute paths are not mapped to Windows locations. `PATH` assignments need manual adaptation. External tools must already be installed on Windows, and their options may differ. Windows environment names are case-insensitive even though local Bash variables remain case-sensitive.

`grep` retains exit status 1 when there are no matches; `pipefail` returns the rightmost failing text stage's status. Regex behavior follows .NET; use `grep -F` for fixed strings. `wc -l` counts text lines and may differ for a file without a final newline. Binary output, external-program pipelines, and external output redirection are blocked; use `curl -o` for downloads.

Unquoted variable values are passed as a single string, without Bash word splitting or glob expansion. A temporary environment assignment combined with variable references in the same command needs manual expansion-order review. Batch-file arguments containing quotes, `%`, `!`, or newlines are blocked during conversion or stopped at runtime to avoid a second interpretation by `.cmd`/`.bat`.

The generated script does not call `exit`. If the final step fails without `set -e`, the PowerShell process exit code is not guaranteed to equal the Bash script's exit code. For CI process integration, inspect `$script:B2PSStatus` and explicitly decide whether to exit.

### File conversion and workflow support

Open the original `.sh` file or use the CLI to embed recursively referenced static child scripts into one output. `bash child.sh` inherits exports and restores the parent directory and environment; `source helper.sh` shares variables. `$0` refers to the original input path, so directory changes based on `dirname "$0"` work even if the output is saved elsewhere. Reconvert after moving the original project. Pasted text without file context cannot include child files.

Environment files are read at runtime, never embedded. The assignment reader accepts `NAME=value`, quotes, simple variables, comments and `export`, and rejects executable Shell statements or complex expansions. Non-`.sh/.bash` source files use this reader. `find` emits sorted absolute Windows paths. Text pipelines and captures use text lines; standalone printf output without a final newline is displayed as a line, while printf file redirection preserves exact text.

The Qwen workflow regression fixtures run with local stub programs on both PowerShell versions. They verify retry handling, child training, prediction, evaluation and completion-file bytes without downloading or training a model. Actual execution still requires the original project's Python dependencies and data.

### Command-line use

```powershell
python .\app.py .\examples\setup.sh -o .\converted.ps1
```

Without `-o`, the script is written to standard output. Diagnostics are written to standard error. Exit codes: `0` conversion completed, `2` unsupported input remains, `1` input/output error.

### Development and validation

```powershell
python -m unittest discover -s tests -v
```

The test suite checks translation boundaries and executes generated scripts in Windows PowerShell 5.1 and PowerShell 7 when available. It covers Unicode and spaced paths, UTF-8 output, non-truncating touch, short-circuit chains, native exit codes, environment restoration, native argument quoting, and the unsupported-input guard. File operations are limited to temporary directories beneath `.test-work`. GitHub Actions runs the suite on Windows with Python 3.10 and 3.13.

```text
bash2ps1/
├── app.py                    # Desktop UI and CLI
├── converter.py              # Translator and recursive file bundling
├── shellsyntax.py            # Quote-aware lexer and structured parser
├── psruntime.py              # Embedded PowerShell workflow helpers
├── Launch.cmd                # Windows launcher
├── CreateShortcut.ps1        # Portable shortcut creation
├── pyproject.toml            # Optional package installation
├── README.md                 # Chinese and English documentation
├── CHANGELOG.md
├── examples/                 # Bash and generated PowerShell examples
├── docs/screenshot.png
├── tests/                    # Unit/integration tests and optional UI preview
└── .github/workflows/        # Windows CI
```

References: [Bash manual](https://www.gnu.org/software/bash/manual/bash.html), [PowerShell argument parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing), [PowerShell pipeline chain operators](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_pipeline_chain_operators).
