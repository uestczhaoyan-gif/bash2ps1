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

## 第一版支持范围

| Bash 步骤 | 转换方式 |
| --- | --- |
| `NAME=value`、`export`、`unset` | 保存 Bash 变量；导出为进程环境变量 |
| `$NAME`、`${NAME}`、`$?`、`~`、`~/...` | 普通变量、上次步骤退出码、用户目录 |
| 单/双引号、转义、反斜杠续行、注释、分号 | 按 Bash 引号边界解析 |
| `&&`、`\|\|` | 按上一条步骤的成功或失败决定后续步骤，支持 5.1 |
| `set -e`、`set -u`、`set +e`、`set +u` | 必需步骤失败时停止、未定义变量检查 |
| 命令前的 `NAME=value command` | 临时设置环境变量，执行后恢复 |
| `cd`、`pwd`、`mkdir -p`、`touch` | 目录与文件操作；touch 保留已有内容 |
| `cp`、`mv`、`rm` | PowerShell 文件命令；支持部分递归/强制选项 |
| `echo`、`printf '%s\n'` | 文本输出 |
| `cat`、`grep`、`head`、`tail`、`wc -l` | UTF-8 文本处理，支持这些命令之间的文本管道 |
| `> file`、`>> file` | 支持已转换文本命令的重定向，UTF-8 无 BOM、LF 换行 |
| `test`、`[ ... ]` | 简单文件判断、字符串判断、整数比较 |
| `git`、`python`、`pip`、`npm`、`node` 等 | 调用真实外部程序，保留参数并检查退出码 |
| `curl`、`wget`、`tar` 等 | 调用真实外部程序；不会调用 PowerShell 同名别名 |

输出脚本包含少量辅助函数，用于变量、退出码、Windows 参数引用和 UTF-8 写入。Python `-c` 等参数中的双引号、空参数、带空格及末尾反斜杠的参数，已在 5.1 和 7 中实际验证。

## 诊断含义与边界

- **待处理（ERROR）**：不能可靠转换。输出脚本顶部会加入 `throw`，在执行任何步骤之前停止。修正输入后重新转换。
- **提示（WARNING）**：可生成脚本，但某些行为有差异，例如正则表达式、未加引号变量的拆分、文件复制覆盖或外部程序可用性。提示也会写入脚本注释。

这是面向安装、配置、构建等**常见步骤**的转换器，不是完整 Bash 编译器。第一版将以下内容标为待处理：`if/for/while/case` 等控制结构、函数、命令替换 `$()`/反引号、复杂 `${...}` 展开、位置参数、here-document、后台任务、子 Shell、`pipefail`、输入和错误重定向、未加引号的通配符、复杂 Unix 文本工具、`sudo`/Linux 包管理器、`chmod/chown` 等。

Unix 的 `/home/...`、`/tmp/...`、`/dev/null` 等绝对路径不会自动映射到 Windows。`PATH` 的冒号分隔和 Unix 路径也不会猜测转换。外部程序需要在 Windows 中安装并能通过 PATH 找到；本工具不会安装程序。Windows 环境变量不区分大小写。

`grep` 只转换文本过滤，**没有匹配时退出码 1 的语义不会保留**；复杂正则需检查，固定字符串优先使用 `grep -F`。`wc -l` 按文本行统计，末尾没有换行时可能与 Bash 不同。二进制输出、外部程序管道及外部程序 `>` 重定向会阻止转换；下载文件建议使用 `curl -o`。

Windows `.cmd/.bat` 参数中出现双引号、`%`、`!` 或换行时会阻止转换或在运行时停止，避免批处理再次解释参数。临时环境赋值与同一命令中的变量引用组合，需要人工改写其展开顺序。未加引号变量按单个字符串传递；本工具不实施 Bash 的单词拆分。

`&&/||` 保留步骤间的成功与失败分支；生成脚本不主动调用 `exit`，最后一步失败且未设置 `set -e` 时，PowerShell 进程退出码不保证与 Bash 脚本一致。需要作为 CI 进程使用时，应检查最终 `$script:B2PSStatus` 并自行决定 `exit`。

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
| `$NAME`, `${NAME}`, `$?`, `~` | Simple values, previous step status, user directory |
| Quotes, escapes, continuations, comments, semicolons | Quote-aware parsing |
| `&&`, `\|\|` | Success/failure branches compatible with PowerShell 5.1 |
| `set -e`, `set -u`, `+e`, `+u` | Required-step failure and undefined-variable checks |
| `NAME=value command` | Temporary process environment, restored afterward |
| `cd`, `pwd`, `mkdir`, `touch`, `cp`, `mv`, `rm` | Directory/file operations with selected options |
| `echo`, `printf '%s\n'` | Text output |
| `cat`, `grep`, `head`, `tail`, `wc -l` | UTF-8 text processing and supported text pipelines |
| `>`, `>>` | Text-only output redirection, UTF-8 without BOM and LF line endings |
| `test`, `[ ... ]` | Simple file, string, and integer tests |
| `git`, `python`, `npm`, `node`, `curl`, and others | Actual external programs with quoted arguments and exit-status checks |

### Diagnostics and limitations

**ERROR / 待处理** means the converter cannot preserve the operation reliably. A `throw` guard is placed before all generated steps. Fix the input and convert again before running the script.

**WARNING / 提示** identifies a behavior difference that needs review. Warnings also appear as comments in the saved script.

This is a practical command-step converter, not a complete Bash compiler. The first release blocks control structures (`if`, `for`, `while`, `case`), functions, command substitution, complex parameter expansion, positional parameters, here-documents, background jobs, subshells, `pipefail`, input/error redirection, unquoted wildcards, Unix-only package managers and permission operations, and complex text tools such as `sed` and `awk`.

Unix absolute paths are not mapped to Windows locations. `PATH` assignments need manual adaptation. External tools must already be installed on Windows, and their options may differ. Windows environment names are case-insensitive even though local Bash variables remain case-sensitive.

`grep` translates text filtering but does not retain Bash's exit status 1 when there are no matches. Regex behavior follows .NET; use `grep -F` for fixed strings. `wc -l` counts text lines and may differ for a file without a final newline. Binary output, external-program pipelines, and external output redirection are blocked; use `curl -o` for downloads.

Unquoted variable values are passed as a single string, without Bash word splitting or glob expansion. A temporary environment assignment combined with variable references in the same command needs manual expansion-order review. Batch-file arguments containing quotes, `%`, `!`, or newlines are blocked during conversion or stopped at runtime to avoid a second interpretation by `.cmd`/`.bat`.

The generated script does not call `exit`. If the final step fails without `set -e`, the PowerShell process exit code is not guaranteed to equal the Bash script's exit code. For CI process integration, inspect `$script:B2PSStatus` and explicitly decide whether to exit.

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
├── converter.py              # Parser, translator, generated helpers
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
