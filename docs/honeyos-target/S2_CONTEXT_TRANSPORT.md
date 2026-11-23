# S2 统一有界上下文与 Codex 通道 · 冻结记录

日期：2026-11-23
分支：`feat/s2-context-transport`（从 S1 冻结提交 `2e26808` 创建）
范围：S2.1–S2.4。未进入 S3–S10，未重跑 M0 审计。

## 基线

| 项目 | 值 |
| --- | --- |
| S1 最终冻结 | `2e26808b9205e82a593606a71fb25a5283a57649` |
| 原始集成基线 | `dba87b94ad17377c78199fed88c248512768db1e` |
| S2 实现提交 | `7fb3f4e403876aab6bf5e1df1d9a45c471aacf96` |
| S2 冻结记录提交 | 本文件所在提交（`git log -1 --format=%H -- docs/honeyos-target/S2_CONTEXT_TRANSPORT.md`） |
| 实现 diff stat | 12 files, +758 / -6（含测试与本文档外的基线表） |

## 复用与改动

| 能力 | 结论 |
| --- | --- |
| `api_content` sidecar（turn_context） | `REUSED`：上下文只进入 API copy，用户原始消息不变 |
| F2.2 `exclude_summaries`（Continuity↔Cognitive 文本去重） | `REUSED`，并补充测试证据 |
| `_strong_current_turn_conflict`（最新纠正覆盖旧推测） | `REUSED`，S1 测试继续覆盖 |
| 主体/时间/推测标注（`_authority_class`/`_visible_line`） | `REUSED` |
| S1 `authorize_silent_memory_context` | `REUSED`，Codex 通道以 `purpose="codex"` 调用 |
| S1 off/shadow/active 门 | `REUSED`，语义未修改 |
| Gateway 每轮伴侣档案 vs 系统提示 IDENTITY/RELATIONSHIP | `FIXED`（真实重复） |
| Gateway 连续记忆快照 vs 每轮结构化召回 | `FIXED`（按条目 ID 去重） |
| Codex app-server 只发送用户消息 | `FIXED`（新增默认关闭的可选通道） |

### 修改文件

- `honeyos/agent/turn_context.py`
  - 新增 `drop_profile_fields_already_in_system_prompt()`：仅当 sidecar 字段标签映射到
    `IDENTITY.md`/`RELATIONSHIP.md` 的托管键，且值在系统提示中完全一致时删除该行；
    改名或新确认的值不在提示中，因此保留。
  - 新增 `drop_known_continuity_entries()`：按 `- [<item id>]` 稳定 ID 去掉 gateway
    sidecar 已送达的连续记忆条目；不同 ID 的相似事实不合并。
  - Cognitive 的 `structured_context` 同时包含 gateway 连续记忆块，使 F2.2 的
    `exclude_summaries` 覆盖两个入口。
- `honeyos/memory/codex_context.py`（新增）
  - `codex_context_mode()`：`off`（默认）/`scoped`；缺失或未知值一律 `off`。
  - `build_codex_context()`：要求 `memory.cognitive.context_mode == "active"`、
    `codex_context_mode == "scoped"`、完整 owner/lane/session/chat_type，并以
    `purpose="codex"` 走 S1 鉴权；总长度上限 1200 字符；任何异常返回空串。
- `honeyos/agent/transports/codex_app_server_session.py`
  - `run_turn(..., context_text="")`：非空时在 `turn/start.input` 前置一个独立
    `{"type":"text"}` 项；`thread/start` 参数保持 `{"cwd": ...}` 不变。
- `honeyos/agent/codex_runtime.py`、`honeyos/run_agent.py`、`honeyos/agent/conversation_loop.py`
  - 传递 `context_text`；Codex 分支默认得到空串，请求结构与改动前一致。
- `honeyos/companion/config.py`
  - 新配置与升级路径写入 `memory.cognitive.codex_context_mode = "off"`，
    显式用户值在升级时保留。
- `tests/honeyos/test_config.py`
  - 默认值断言更新为同时包含 `context_mode=shadow` 与 `codex_context_mode=off`；
    升级用例验证 `scoped` 被保留。

## Codex 通道当前能力

- 默认关闭：未配置时 `codex_context_mode` 为 `off`，请求与旧版完全一致。
- 开启条件（全部满足）：`context_mode=active` + `codex_context_mode=scoped` +
  companion 作用域完整 + 记录显式授予 `purpose` 含 `codex`。
- 发送内容：仅经授权、截断后的记忆块；不含完整 system prompt、USER.md、MEMORY.md。
- 不持久化：上下文只作为本轮独立的 text item，用户消息正文与历史不变。
- 非 companion 代码执行模式没有 owner/lane/chat_type，恒为空串。

## 测试

命令统一使用隔离 `HONEYOS_HOME=/tmp/...`、`PYTHONPATH` 指向集成树、既有 W venv。

| 目标 | 结果 |
| --- | --- |
| `tests/honeyos/memory/test_codex_context.py` | 13 passed |
| `tests/honeyos/memory/test_context_dedupe.py` | 11 passed |
| `tests/honeyos/agent/test_codex_context_transport.py` | 3 passed |
| 三个 S2 新文件合并 | `27 passed in 0.83s` |
| S2 新文件 + S1 权限门 | `44 passed in 1.69s` |
| `tests/honeyos/memory` + continuity/gateway/prompt/agent 相邻回归 | `170 passed in 10.01s` |
| `tests/honeyos/test_config.py` | `14 passed, 1 failed`（既有 SOUL 失败，见下） |
| 修改模块 `py_compile` | 通过 |
| `git diff --check` | 通过 |

已知既有失败：`test_upgrade_companion_capabilities_is_idempotent_and_preserves_user_state`
的 `assert first_soul.startswith("# My formed identity")`。S1 阶段已用冻结 HEAD
worktree 对照证明与 S1 无关；本轮未修改 SOUL，也未新增失败。其失败点之前的
`context_mode` 断言仍通过。

## 指标（改动前 → 改动后，来自单元夹具）

| 指标 | 前 | 后 |
| --- | --- | --- |
| 伴侣档案 sidecar 字符数（与提示同值） | 87 | 0 |
| 连续记忆块字符数（2 条中 1 条重复） | 147 | 124 |
| Continuity 选中条目 | 2 | 1（重复条目不再注入） |
| Continuity↔Cognitive 同摘要条目（1 条选中） | 1 注入 | 0（`duplicate_context`） |
| 估算输入 token（按 len/4，粗略） | 58 | 31 |
| 模型调用 | 0 | 0 |
| 原始用户消息 | 不变 | 不变 |
| 越权注入 | 未测出 | 0（跨 owner/lane/session/chat_type/purpose 均拒绝） |

生产数据下的真实 token 节省未测；上表仅覆盖夹具场景，不推算到线上。

## 成本与边界

- 模型调用：0；token 与费用：0；未调用外部账号或付费模型。
- 未修改 U2 v2 默认关闭状态、G2 规则、模拟生理算法、Study 数据与冻结接口。
- 未改动 S1 权限语义；S1 专项测试继续通过。
- 未修改生产 release、systemd、live `PYTHONPATH` 或真实 `~/.honeyos` 数据库。
- 未 push、未合并、未部署。

## 回滚

```bash
git revert 7fb3f4e403876aab6bf5e1df1d9a45c471aacf96
git revert <S2 冻结记录提交>
```

或切回 `feat/s1-cognitive-scope-gate`。未使用 `reset --hard`/`clean -fd`。

## 遗留风险

- Codex 通道的真实账号联调未执行（本轮禁止调用真实外部账号），只以 fake client
  断言协议 JSON。
- 历史 episode 仍需显式授予 `purposes` 含 `codex` 才会进入 Codex 通道；
  未做数据迁移。
- 去重按稳定 ID 与完全同值字段，不做语义相似合并；这是本轮有意保留的边界。
