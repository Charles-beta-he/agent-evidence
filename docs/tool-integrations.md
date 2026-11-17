# Native tool integrations / 原生工具接入

## Installation mechanism / 安装机制

Official references checked for this slice:

- [Codex skills](https://developers.openai.com/codex/skills/): project skills under
  `.agents/skills/<name>/SKILL.md`; explicit `$agent-evidence` invocation;
  `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`.
- [Claude Code skills](https://code.claude.com/docs/en/skills): project skills under
  `.claude/skills/<name>/SKILL.md`; explicit `/agent-evidence` invocation;
  `disable-model-invocation: true` is skill frontmatter.

These two native skill mechanisms are deliberately separate. This package does
not install a marketplace plugin, MCP server, hook, global skill or tool CLI.
两种原生技能机制分别处理；不安装 marketplace 插件、MCP、hook、全局技能或工具 CLI。
The Python wheel includes the thin helper and skill templates. An activated
Python environment must remain on PATH in the tool's session. Installing the
project skill alone does not install Python or invoke a check.
Python wheel 包含辅助命令和技能模板；工具会话的 PATH 必须包含已安装环境。
仅安装项目技能不会安装 Python，也不会执行检查。

## Scope / 范围

`agent-evidence-project check --project ABS --output NEW_ABS --file REL --json OTHER_REL`
accepts one to 32 distinct paths, explicitly chosen by the user. Paths use the
kernel's safe ASCII relative-member grammar (no traversal, spaces or shell syntax).
No recursive discovery, inferred inventory, arbitrary command runner or fixture
call exists. The original files are read by the unchanged kernel and independently
read back in its subprocess pipeline. File bodies are not copied into evidence.

接受用户明确选择的 1–32 个不同路径，遵循内核安全 ASCII 相对路径规则（无越级、空格或 shell 语法）。
无递归发现、推断清单、任意命令执行器或 fixture 调用。
未经改动的内核读取原文件，通过子进程管线独立读回，不将文件正文复制到证据目录。

The helper writes only its unique `.agent-evidence-<random>/` controls in the
project and the explicitly requested new output directory. Controls include
selected paths, a cooperative read-only policy and selection digest. This digest
is **not a whole-project revision**; `check_revision` covers only the unchanged
kernel, not the integration. No business grant, scope attestation or success
receipt is synthesized. PASS never fills the missing business evidence.

辅助命令仅写项目内独有的控制目录和明确指定的新输出目录。控制内容包括所选路径、协作式只读策略、
选择摘要。该摘要**不是整个项目的版本**；`check_revision` 仅覆盖未改动内核，不覆盖接入层。
不会合成业务授权、范围证明或成功回执；PASS 不能补足缺失的业务证据。

| Axis / 轴 | Contract / 契约 |
| --- | --- |
| Observation / 观测 | Kernel PASS / FAIL / UNKNOWN, preserved without reinterpretation / 保留内核语义 |
| Task / 任务 | Always UNKNOWN; explicit file observations are insufficient / 始终 UNKNOWN，文件观测不足以证明任务完成 |
| Completeness / 完整性 | Always false in this helper / 此辅助命令始终 false |
| Certification / 认证 | Always false / 始终 false |
| Check exit / 检查退出 | 1 for admitted scoped observations, 2 for invocation/admission errors; never 0 / 准入后限定观测为 1，调用或准入错误为 2，从不为 0 |

Malformed JSON can be FAIL; a missing file is UNKNOWN under the kernel's
conservative unavailable-evidence rule. A supplied JSON object declaring
`complete=true` can be readable (PASS) while task completion stays UNKNOWN.
JSON 格式错误可为 FAIL；文件缺失按内核保守的证据不可用规则为 UNKNOWN。
声明 `complete=true` 的 JSON 对象可读时可为 PASS，但任务完成仍是 UNKNOWN。

## Explicit JSON scalar acceptance / 显式 JSON 标量验收

```sh
agent-evidence-project check --project ABS --output NEW_ABS --expect-json config.json version '2'
```

This assertion adds a separate `acceptance_verdict` and `acceptance` rows. Correct
integer 2 is PASS; integer 1 is FAIL; absent/unreadable/invalid JSON, missing field
or cross-read drift is UNKNOWN. With no assertion, acceptance is UNKNOWN, not
vacuous success. Observation retains the kernel's original semantics.
此断言新增独立 acceptance 轴：整数 2 为 PASS，整数 1 为 FAIL；缺失／不可读／无效 JSON、
字段不可用或跨读漂移为 UNKNOWN；无断言也为 UNKNOWN。观测轴不变。

At most 32 distinct selected files total, one assertion per file. Field paths use
1–16 dot-separated ASCII identifier keys (`[A-Za-z_][A-Za-z0-9_]*`), max 64 chars
per key and 256 total; no arrays, escapes or expressions. Expected JSON is an
explicit scalar up to 4096 UTF-8 bytes; finite numbers only, integers bounded by
2^63−1 magnitude. Parsed types match exactly: true != 1 and 2 != 2.0. JSON strings
need JSON quotes inside shell quotes, e.g. `'"ready"'`; null is explicitly `'null'`.
最多共 32 个不同文件，每文件一个断言；字段为 1–16 段 ASCII 标识符对象键（每段最多 64、总长 256），
不支持数组／转义／表达式。预期为最多 4096 UTF-8 字节的显式 JSON 标量；仅有限数字，整数绝对值不超过
2^63−1。类型严格匹配；字符串需要 JSON 引号，null 必须显式提供。

A fresh descriptor-anchored no-follow read (1 MiB per file; shared 8 MiB/10s
acceptance budget) must match the SHA-256 from the kernel's independently verified
PASS and final policy consistency. Only those same bytes are parsed and compared.
Drift revokes acceptance, not silently reinterprets another snapshot. Rows bind
file/field/typed expectation and its digest to kernel run/check/candidate/revision
and observed byte SHA. The expectation is public evidence: do not supply secrets.
Actual field values and source bodies are not exported. Aggregate FAIL if any
verified mismatch, else UNKNOWN if any unknown/none requested, otherwise PASS.
新读取必须无链接、描述符锚定且有界（每文件 1 MiB，验收共 8 MiB／10 秒），并与内核独立验证的 PASS
字节 SHA 一致且最终策略一致；仅解析和比较这些相同字节。漂移不能被当作旧证据成功。
结果绑定文件、字段、类型预期及其摘要与内核运行／检查／选择／版本／字节身份。预期会公开记录，勿传秘密；
不导出实际字段值或源正文。聚合有确定不符则 FAIL，否则存在未知或未请求则 UNKNOWN，否则 PASS。

This is snapshot scalar equality, **not** proof tests ran or whole-task/business
certification. Cooperative guarantees do not cover hostile same-user mutation or
continuous freshness. All completion/certification flags and exit codes stay unchanged.
这是快照标量等值，**不是**测试执行证明、全任务／业务认证；不覆盖同用户恶意修改或持续新鲜性。
所有完成／认证标志和退出码不变。

## Installation safety / 安装安全

- Explicit physical project root only; no HOME fallback or global settings edits.
  仅接受明确物理项目根目录，无 HOME 回退或全局配置修改。
- Identical installs and already absent uninstalls are idempotent. Existing edited
  or extra skill files cause refusal rather than overwrite/delete. Upgrades require
  uninstalling with the original installed version first, or manual review of the
  conflict. No force flag. Identical installer files are the ownership check, not
  a cryptographic provenance claim.
  相同安装和已不存在的卸载幂等；修改或额外文件导致拒绝。升级需先用原安装版本卸载，
  或人工审阅冲突；无 force 参数。以安装文件字节一致性判断归属，不声称密码学溯源。
- Symlinks and hardlinks are refused at read boundaries; directory accesses are
  descriptor-anchored. This remains a cooperative local tool, not an OS sandbox
  against a hostile same-user filesystem mutator. Interrupted install/uninstall
  may leave partial files, which require manual inspection; no broad cleanup.
  读取边界拒绝符号／硬链接，目录访问使用描述符锚定。这仍是协作式本地工具，
  不是针对同用户恶意文件系统修改者的 OS 沙箱。中断可能留下部分文件，需人工检查，不做广泛清理。
- Evidence and control directories remain for audit, including on failed checks.
  They are not source deliverables. After review, remove only the exact run's paths
  you own; skill uninstall never deletes evidence or adjacent user settings.
  检查失败时也保留证据和控制目录供审计；它们不是源码交付物。审阅后只删除自己拥有的精确运行路径；
  卸载技能不会删除证据或相邻用户配置。

## Verification boundary / 验证边界

Installed CLI probes: Codex 0.163.0 and Claude Code 2.1.239. An installed skill,
a config scan or a model's prose is not proof of actual invocation. The integration
exercise must show native invocation, real helper execution, kernel receipts,
false-completion rejection, and uninstall readback separately for each tool.
Claude's initial auth probe reported expired credentials; no login or secret entry
is performed by this package. A blocked model invocation remains unverified,
even when deterministic installation/helper tests pass. Existing kernel CI runs
are not integration approval. See the delivery's `integration-evidence/` packet
for exact commands/logs and remaining model acceptance gaps; this repository does
not ship machine-local paths, credentials or raw model session logs.

安装的 CLI 探测版本为 Codex 0.163.0、Claude Code 2.1.239。技能安装、配置扫描或模型文字不等于实际调用。
各工具需分别证明原生调用、实际辅助命令执行、内核回执、假完成拒绝和卸载读回。
Claude 初始认证探测显示凭据过期；本包不执行登录或秘密输入。模型调用受阻仍属于未验证，
即使确定性安装／辅助命令测试通过。已有内核 CI 不构成本接入批准。
精确命令／日志和未验项见交付中的 `integration-evidence/`；仓库不附带机器本地路径、凭据或模型会话原始日志。
