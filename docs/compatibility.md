# 1.0.0 核心验收与结题记录

日期：2026-10-14。结题范围：常见、可移植的 Bash 自动化脚本，输出原生 Windows PowerShell 5.1 / PowerShell 7，不依赖 Bash/WSL。

用户已将“所有可能脚本”调整为“常用、广泛使用的命令”，并要求完成语义修正、常用语法/命令覆盖和对照测试三项工作。1.0.0 按 README 的具体支持清单验收；Linux 专用系统操作、动态 Shell 代码、后台/交互/无限输出和高级工具方言保留明确适配边界。

## 三项验收

| 项目 | 结果与证据 |
| --- | --- |
| 修正已接受语法中的行为差异 | 输出改为原始字节流；保留 printf 精确换行、无换行命令替换片段、空参数、IFS 拆分、通配符、临时环境展开顺序、退出码和文件内容；Windows 原生错误流用同一 OS 管道合并 |
| 补齐常用语法和命令 | 函数/local/return、数组、整数算术/C 风格 for、case、位置参数、组合命令、子 Shell、here-document、常用重定向；补齐 grep/sort/uniq/cut/tr/tee/sed/awk/xargs/read/env 等实际操作，选项范围由 command_specs.py 定义 |
| Bash 对照与真实工作流回归 | 160 个受控场景分别与 PowerShell 5.1、7 比较，共 320 组引擎对照；检查标准输出、标准错误、退出码和文件内容。另保留原有回归及 Qwen 完整流水线模拟；桌面文件上下文、复制状态及 CLI 输出已验证 |

本地完整测试：`python -m unittest discover -s tests -v`，40 个测试入口通过，其中对照入口包含 154 场景/308 组引擎对照。之后增加 5 个 cat/grep 选项场景，并连同 4 个受影响旧场景在两个引擎中对照通过；最后增加的标准输出/错误流文件合并场景和受影响重定向场景也已在两个引擎对照通过。最终测试集合共 160 场景，CI 对完整集合运行，禁止以缺少 Bash 后跳过测试视为通过。

所有执行测试仅使用本地受控程序和项目 `.test-work` 临时目录。原始 Qwen 工作流通过模拟下载失败两次、第三次成功，继而训练、预测、评估与完成文件的过程验证；未下载模型或实际训练。

## 0.2.0 审计问题的修复结果

以下输入在旧代码基线 `726031e` 曾存在行为差异。1.0.0 两种 PowerShell 的标准输出与真实 Bash 完全相同，表中用字节转义表示换行。

| 输入 | 旧 PowerShell 输出 | 1.0.0 与 Bash 输出 |
| --- | --- | --- |
| `printf '%s' hello` | `hello\r\n` | `hello` |
| `WORDS="a b"; printf '<%s>\n' $WORDS` | `<a b>\r\n` | `<a>\n<b>\n` |
| `printf 'x' \| wc -l` | `1\r\n` | `0\n` |
| `X="$(printf '%s' a; printf '%s' b)"; printf '%s' "$X"` | `a\r\nb\r\n` | `ab` |

同时验证了普通文本以外的二进制重定向、native stdin/stdout/stderr、错误流合并顺序、重定向顺序、8 位 Bash 退出码、函数局部变量、空环境变量、两种 PowerShell 的环境变量删除差异和多项临时环境赋值。

## 已知边界

- Bash 的可移植语法可以继续实现；本版本保证范围以 README 清单和回归用例为准，不声称完整实现 Bash 或完整 sed/awk/GNU 工具方言。
- 外部程序需要对应的 Windows 可执行版本、依赖和数据。文件路径及权限使用 Windows 语义；Unix 包管理器、权限/内核接口不能靠命令改写提供。
- 有限管道在阶段之间缓冲原始字节，适用于自动化脚本。持续流、TTY 交互、作业控制、Unix 信号/SIGPIPE 和无限输出需要其他执行设计，不在本次结题范围。
- 文本工具以 UTF-8 和普通 BRE/ERE 为核心；特定区域设置、复杂正则、动态 source 路径、任意文件描述符及未列出的选项需要明确适配。
- `.env` 运行时读取普通赋值，不作为完整 Shell 程序执行；原项目移动后需重新转换静态依赖路径。

在用户确认的常用、可移植范围内，三个核心阶段已完成，1.0.0 可作为结题版本。后续维护按具体可复现脚本处理转换缺陷，不将周边功能作为本次完成条件。

参考：[Bash 手册](https://www.gnu.org/s/bash/manual/bash.html)、[GNU Coreutils](https://www.gnu.org/software/coreutils/manual/coreutils.html)、[Windows 子进程重定向](https://learn.microsoft.com/en-us/windows/win32/procthread/creating-a-child-process-with-redirected-input-and-output)。
