[English](README.md) | [简体中文](README.zh-CN.md)

# agent-evidence（开发者预览）

**让 Codex 或 Claude Code 提供真实、有边界的本地文件观测，而不只是声称“完成”。**
明确选择文件，主动调用技能，即可得到经过内核独立读回的 PASS / FAIL / UNKNOWN。
不需要手写 manifest、inventory 或 receipt。
本预览验证文件可读性／字节身份及用户显式指定的 JSON 标量字段等值，例如 config.json 的 version 等于 JSON 整数 2。
**不能证明测试实际执行／通过、一般业务正确或整个任务完成**。
Codex 有原生调用证据；Claude 已验证安装／发现，但实际模型调用仍为 **未验证**（OAuth 过期，保留用户登录门）。
它不是完整的 Hermes/MOS 技术栈，也不是生产认证。

## 按工具安装

需要 Python 3.11+、本地 POSIX 文件系统，以及已安装并登录的 Codex 或 Claude Code CLI。
不假定存在 PyPI 发布版本。在本源码检出目录执行：

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install .
# 选择其中一个，填写现有项目的绝对物理路径：
agent-evidence-project install --tool codex --project /absolute/path/my-project
agent-evidence-project install --tool claude --project /absolute/path/my-project
```

在 `my-project` 中启动工具时，保持此环境位于 PATH。安装后重启已有工具会话。
Codex 项目技能位于 `.agents/skills/agent-evidence`；Claude Code 项目技能位于
`.claude/skills/agent-evidence`。这是各自的**原生项目技能**，不是共用的插件／扩展安装协议。
不会安装全局配置、hooks 或 MCP。**安装不等于执行；已关闭模型自动调用。**

### Codex

```text
$agent-evidence 验证当前项目 config.json 的 version 字段等于 JSON 整数 2，证据写入 /absolute/path/my-project-evidence-001。分别报告限定验收和观测；不要声称测试实际执行或整个任务完成。
```

### Claude Code

```text
/agent-evidence 验证当前项目 config.json 的 version 字段等于 JSON 整数 2，证据写入 /absolute/path/my-project-evidence-001。分别报告限定验收和观测；不要声称测试实际执行或整个任务完成。
```

请替换为实际存在、明确授权且可安全公开的文件。
证据目录必须是**项目外的新目录**，其物理父目录已存在，路径各部分均无符号链接。
不会自动选择文件。辅助命令在项目内创建私有 `.agent-evidence-<随机值>/` 控制目录，
并读取选中的原文件，不复制其正文。不要选择秘密文件；控制清单包含所选相对路径。

### 不使用模型／排障

```sh
agent-evidence-project check --project /absolute/path/my-project \
  --output /absolute/path/my-project-evidence-002 --expect-json config.json version '2'
# 或 --json config.json 仅检查可读性（验收 UNKNOWN）。
# 或使用 --file README.md 检查存在性／可读字节身份。
```

`OUT/report.json` 是未经改动的内核报告；`OUT/integration.json` 和 stdout 总结本次范围。
请读取 verdict，而不是仅看进程退出码：

| 限定验收 | 含义 |
| --- | --- |
| PASS | 与内核独立验证观测字节绑定的显式类型字段等值成立 |
| FAIL | 已验证字节上的字段存在，但不符合指定类型和值 |
| UNKNOWN | 无预期、字段缺失、JSON 无效、证据不可用或字节漂移 |

`observation_verdict` 单独保留内核语义。字段路径为有界 ASCII 对象键点分路径，不是表达式。
预期必须显式提供 JSON 标量（不接受数组／对象），并会写入报告；**不要提供秘密值**。
类型严格区分：`true` 不等于 `1`，`2` 不等于 `2.0`。

**即使 PASS，检查也退出 1**：`task_verdict=UNKNOWN`、`complete=false`、
`certified_healthy=false`。退出 2 表示调用／准入无效。安装和卸载退出 0 仅表示该安装操作成功。
文件里的 `{"complete":true}` 声明和合成 fixture 都不能证明任务完成。

## 卸载

```sh
agent-evidence-project uninstall --tool codex --project /absolute/path/my-project
agent-evidence-project uninstall --tool claude --project /absolute/path/my-project
```

只删除与安装版本字节完全一致的技能。有编辑或额外文件时拒绝卸载，不触碰相邻配置或技能。
证据及控制目录保留供审阅。详见[接入细节与限制](docs/tool-integrations.md)。

## 进阶／状态

- [内核安装、合成示例、CI 记录及限制](docs/kernel-guide.zh-CN.md)
- [架构](docs/architecture.md)、[契约](docs/contracts.md)、[威胁模型](docs/threat-model.md)
- [Hermes 适配器](docs/hermes-adapter.md)、[验证说明](docs/verification.md)

此次接入没有修改内核。内核的 check revision 标识内核代码，不覆盖技能／辅助命令。
已有 CI 证据不构成本次新接入的认证。契约仍在演进；不存在生产发布批准、业务 E2E 证明或密码学证明。

[MIT 许可](LICENSE) · [第三方声明](THIRD_PARTY_NOTICES.md)
