# 原生 PowerShell 转换兼容性审计

审计日期：2026-10-14。被审计的代码基线：`726031e`（0.2.0）。

用户要求输出原生 PowerShell 命令，不依赖 Bash 或 WSL。当前代码尚未达到“任意 Bash 文件都能等价转换”的结项要求。此前的 39 项测试和 Qwen 流水线模拟验证证明了这些具体用例通过，不能据此推导任意脚本正确。

## 三类问题需要区分

1. **未覆盖的 Bash 语法。**函数、`case`、数组、算术展开、`$@/$*`、here-document、输入/错误重定向、外部程序管道等仍会被拒绝。这些属于转换器可继续实现的核心能力。
2. **已接受输入的行为差异。**文本换行、未加引号变量的单词拆分、命令替换和文本管道仍有近似行为。没有 ERROR 不等于原样保留语义；其中部分差异会提示，部分仅在 README 中说明。
3. **宿主环境差异。**Bash 可以调用任意外部程序，访问 Linux 专用文件和内核接口，依赖特定服务、权限或工具选项。补齐 Shell 语法不会自动提供这些系统能力。原生 PowerShell 输出需要对应的 Windows 实现、依赖和路径信息；缺少这些信息时无法保证保持原脚本效果。

完整 Bash 语法可以通过编译或在 PowerShell 中实现解释器继续扩展；这不等于解决任意脚本的外部环境依赖。本项目不能作出“无需 Bash/WSL、任意 Linux 脚本自动等价运行”的承诺。

## 已复现的行为差异

下面四个受控输入分别在本机 Git Bash、Windows PowerShell 5.1 和 PowerShell 7 中执行。转换器对它们均未产生 ERROR。两种 PowerShell 的结果相同。表中使用字节转义表示换行。

| 输入 | Bash 标准输出 | 生成的 PowerShell 标准输出 |
| --- | --- | --- |
| `printf '%s' hello` | `hello` | `hello\r\n` |
| `WORDS="a b"; printf '<%s>\n' $WORDS` | `<a>\n<b>\n` | `<a b>\r\n` |
| `printf 'x' \| wc -l` | `0\n` | `1\r\n` |
| `X="$(printf '%s' a; printf '%s' b)"; printf '%s' "$X"` | `ab` | `a\r\nb\r\n` |

第二个用例反映字段拆分差异；第四个用例反映命令替换对无换行输出的拼接差异，不能仅靠将 CRLF 换成 LF 修复。第三个用例要求按换行字符计数，而非按 PowerShell 文本记录数计数。

## 后续核心改进的优先级

1. 修正已接受输入中的输出、参数和状态语义；暂时不能精确保留时应给出明确诊断，避免仅以“成功生成脚本”表示等价。
2. 扩展结构化解析与变量模型，补齐可移植脚本中的函数、数组、算术、位置参数、here-document、重定向和进程管道。
3. 为跨平台命令定义具体兼容范围；未知命令和 Linux 专用操作应明确说明所缺能力，不能把保留同名调用视为已移植实现。
4. 增加 Bash 与 PowerShell 的对照回归测试，比较参数、标准输出、标准错误、退出码和文件变化；新增语法要与错误分支、嵌套、空参数、空格路径和 Unicode 组合验证。

这些是核心转换工作，不需要增加界面、联网转换或其他周边功能。支持范围内的正确性可以逐项验证；有限的测试集合不能证明“所有可能 Bash 文件”的等价性。当前应保持未达到全量结项要求的状态。

参考：[Bash 展开规则](https://www.gnu.org/s/bash/manual/html_node/Shell-Expansions.html)、[PowerShell 参数解析](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing)、[PowerShell 管道](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_pipelines)。
