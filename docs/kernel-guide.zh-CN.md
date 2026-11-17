[English](kernel-guide.md) | [简体中文](kernel-guide.zh-CN.md) | [快速入门](../README.zh-CN.md)

# 内核指南（开发者预览）

本进阶页面描述内核，不是显式启用的项目辅助命令。辅助命令仅创建自己使用的协作式控制策略；
详见[接入边界](tool-integrations.md)。

有明确边界的本地证据观测，**不是生产认证**。
这是已公开的开发者预览版本，并非完整的 Hermes 或 MOS 技术栈，也不是规划中的完整证据包。

已实现：显式存在性检查与严格 JSON 检查、只读协作式策略、固定且有资源边界的子进程工作器、
独占回执，以及读取回执并重新计算观测结果的第二个独立子进程。
存在性检查仅确认内容身份；JSON 检查成功仅说明对象可读取，不代表业务验证通过。

已实现的清单功能：显式 scope/attestation/catalog 准入、声明与源文件的原始字节绑定、
一次性不可变冻结，以及六种清单覆盖视图。`fixture --inventory` 生成这一合成契约。
已实现的流程功能：精确绑定已准入的 grant/assertion 字节、完整声明绑定、不同的成功 ID、
最新证据的新鲜度、验收断言、否定断言与清理断言，以及允许的副作用验证。
这是**对所提供证据的验证**，不是经过独立核验的业务工作。
`evaluate` 验证显式流程证据包；已存储的诊断报告仍为 UNKNOWN，不能恢复实时准入。

已实现的 Hermes 功能：固定的 21 项处置目录、版本化的显式脱敏输入、
job/route/registration/timestamp 语义及禁止项检查，目标 I/O 为零。
详见[字段契约](hermes-adapter.md)。这并不证明与任一 Hermes 版本完全兼容。
已实现：固定模块的已执行代码与源文件一致性检查、过期缓存与辅助模块漂移拒绝、
根目录及祖先目录身份检查，以及有上限的声明和检查数量。
固定到 SHA 的只读 CI 工作流已在 Ubuntu 和 macOS 的 Python 3.11、3.12、3.13 上通过；
具体运行记录见[状态与限制](#状态与限制)。
Schema 仍是持续演进的开发契约，不是完整的稳定包。请勿用于认证。

## 安装与试用

需要 Python 3.11 或更高版本，以及本地 POSIX 文件系统。
在源码检出目录的根目录构建分发产物并安装 wheel（非 editable 安装），建议使用虚拟环境。
此示例从源码构建，不假定已有 PyPI 发布版本。
隔离构建会按照 `pyproject.toml` 的声明安装 `setuptools==82.0.1`；该包没有运行时依赖。

```sh
python -m pip install build
python -m build
python -m pip install dist/agent_evidence-0.1.0.dev0-py3-none-any.whl
agent-evidence --help
agent-evidence fixture --out /absolute/physical/path/demo-input
agent-evidence run --input-root /absolute/physical/path/demo-input --manifest manifest.json --output-root /absolute/physical/path/demo-output
```

请选择已经存在、路径各部分均不含符号链接的物理父目录。两个末级目标目录都必须是新目录。
这些仅为合成测试样例，不会扫描宿主机或导出业务数据。
限定范围内的检查可以是 `PASS`，但缺少完整清单和流程证据时，`run` 返回 **1**，且 `complete=false`。
报告使用 `implementation_status=scoped_evidence_pipeline`。
清单示例可使用 `fixture --inventory --out NEW_INPUT`，然后执行相同的 `run` 命令。
回放已存储的报告可使用 `evaluate --input-root OUTPUT --bundle report.json`；
它返回 1 和 `supplied_evidence_only`，绝不会恢复实时准入。
完整的限定范围示例可使用 `fixture --procedures --out NEW_INPUT`，然后执行 `run`：
有效且新鲜的合成证据返回 **0**、`complete=true`，但始终保持 `certified_healthy=false`。
缺失、被拒绝或无效的必需证据会阻止返回 0。
使用 `evaluate --input-root NEW_INPUT --bundle procedures.json` 评估其显式证据包
（退出码为 1，即使所提供的证据为 PASS；离线评估不能恢复实时准入）。
样例中的合成 `live_e2e` 字段是被测试的断言，不表示样例生成器执行了业务流程。
显式 Hermes 示例使用 `fixture --hermes --procedures --out NEW_INPUT`，然后执行
`hermes run --input-root NEW_INPUT --manifest manifest.json --output-root NEW_OUTPUT`。
报告中的 `hermes` 轴保留全部 21 个必需行；字节观测的 PASS 不会将 UNKNOWN 语义结果变为成功。
对于 `run`，退出码 0 还要求限定范围内完整的 PASS。
无效的调用/schema/准入返回 2；已准入但证据为否定或不完整的运行返回 1。
写出回执从不意味着完整性。`report.json` 会被读回，stdout 为 JSON，stderr 仅包含封闭集合的错误码。
输入正文和子进程 stderr 从不返回。

```python
from agent_evidence import run_checks
report = run_checks('/absolute/physical/path/demo-input', 'manifest.json',
                    '/absolute/physical/path/another-output')
assert report['certified_healthy'] is False
```

所有提供的 ID 都必须可安全公开。格式检查不能证明 ID 不是秘密信息。
回执通过设备/inode 摘要表示根目录，而非使用路径。
不提供环境变量回退、HOME 展开、owner 模块导入、执行插件、网络调用、修复操作或策略写入器。

## 状态与限制

[GitHub Actions 运行 44087269853](https://github.com/Charles-beta-he/agent-evidence/actions/runs/44087269853)
在提交 `cc2598ee324a90d3306ac3f6a403bd567c8c2976` 上通过：
`ubuntu-latest` / `macos-latest` × Python 3.11 / 3.12 / 3.13 的全部六个任务均完成分发产物构建，
并验证了干净环境中的非 editable wheel 和 sdist 安装。
这是使用合成输入、限定范围的已安装产物验证证据，不是真实业务 E2E 证明，
也不保证所有平台或 Python 版本都可用。不支持 Windows 观测；不声称 Python 3.14 已通过。

[验证说明](verification.md) 保留了早期本地 macOS 验证记录及复现、覆盖范围细节。
其中“CI 尚未运行”和“Linux/其他 Python 版本尚未测试”的表述描述的是当时的快照；
上方链接的 CI 运行记录仅更新这些状态结论。
不存在生产发布批准、生产认证、业务 E2E 证明或密码学证明。
另见[契约](contracts.md)与[威胁模型](threat-model.md)。
