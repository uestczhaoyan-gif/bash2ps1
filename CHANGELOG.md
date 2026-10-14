# Changelog

## 1.0.0

- 完成面向常用、可移植 Bash 自动化脚本的核心结题版本，输出原生 PowerShell 5.1/7。
- 用原始字节流修正 printf、命令替换、重定向、wc 和外部程序管道，保留空参数、字段拆分、通配符及标准错误合并顺序。
- 补齐函数/local/return、索引与常见关联数组、整数算术/C 风格 for、case、组合命令/子 Shell、位置参数、here-document 及常用重定向。
- 扩展 cat/grep/head/tail/wc/sort/uniq/cut/tr/tee/sed/awk/xargs/read/seq/env 等常用命令，明确常见选项与无法移植操作的诊断。
- 修正 PowerShell 5.1/7 的空环境变量与删除变量差异，自动返回最终 Bash 状态。
- 加入真实 Bash 与两种 PowerShell 的对照验收，比较输出、错误流、退出码及文件内容；保留 Qwen 流水线模拟回归。
- 同步版本、打包模块、README、验收记录和 Windows CI；生成脚本不依赖 Bash/WSL。

## 0.2.0

- 说明原生 PowerShell 转换目标与实际兼容边界，新增 Bash/PowerShell 输出差异审计；不将已通过用例宣传为任意脚本等价转换。

- 补齐真实训练流水线常见语法：`if/elif/else`、`while/until`、列表 `for`、`!`、`$()`/反引号和嵌套 `${...}` 默认值及必填检查。
- 支持 `$0`/位置参数、变量指定的可执行程序、`set -a`、`pipefail` 和文本管道退出码；grep 无匹配返回失败。
- 转换 `sleep`、`date -Is`、`dirname/basename`、常用 `find` 选项和多占位符 `printf`，文件重定向保留 printf 的精确换行。
- 文件入口自动递归转换并嵌入静态引用的子脚本，区分 source 共享变量与 bash 子进程隔离；`.env` 运行时读取，不执行其中的 Shell 代码。
- GUI 保留原文件路径和建议输出名，CLI 使用相同的文件转换流程；运行错误标出原 Bash 行号。
- 新增原始 Qwen 工作流回归用例，在 PowerShell 5.1/7 用本地模拟程序验证重试、训练/预测/评估参数、环境继承和完成文件。

## 0.1.0

- 中文桌面界面：输入、预览、诊断定位、剪贴板、文件导入和 `.ps1` 保存。
- 保留 Bash 引号边界、变量、续行和 `&&` / `||` 的常见步骤转换。
- 文件操作和文本处理转换，Windows 外部程序参数和退出码处理。
- 不能可靠转换时生成带停止保护的脚本。
- Windows PowerShell 5.1 / PowerShell 7 实际运行测试与 Windows CI。
