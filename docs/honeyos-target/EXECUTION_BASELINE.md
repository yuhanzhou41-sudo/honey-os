# HoneyOS 目标架构执行基线

日期：2026-11-23  
范围：S0 最小现场核对与 S1 任务分支定位；不是重新执行 M0。

## 源树与保护边界

| 项目 | 现场值 |
| --- | --- |
| 集成工作树 | `/home/zyh20/projects/honey-os-integration` |
| 集成分支 | `integration/u2-v2-off` |
| 冻结 HEAD | `dba87b94ad17377c78199fed88c248512768db1e` |
| 已核对冻结提交 | `86270f61`、`dba87b94` |
| S1 任务分支 | `feat/s1-cognitive-scope-gate`（从冻结 HEAD 创建） |
| 初始 dirty/untracked | 无 |
| U2 producer | `memory.distillation.understanding.enabled=false`，保持关闭 |
| R5 active injection | 未接入，本阶段不修改 |
| 当前 live `PYTHONPATH` | `/home/zyh20/projects/honeyos-releases/study-flashcard2-20261121` |
| live unit | `honeyos-gateway.service`；drop-in `20-verified-study-release.conf` |

原 W/P/R 与当前 release 均不在本阶段修改范围内。不修改生产数据库、systemd、live `PYTHONPATH`，不 merge、不 push、不部署。

## 既有证据核对

- `docs/understanding_v2/INTEGRATION_FREEZE_20261122.md` 的工作树、分支和两个整合提交与现场一致。
- Study salience 同步仍位于 `honeyos/memory/runtime_shadow.py`，本阶段不得回退。
- M0 P0-4 仍成立：Cognitive 注入缺少 owner/lane/session/chat_type/用途权限复核。
- M0 P1-2 仍成立：存在模型可见注入，但没有显式 `off/shadow/active` 配置门。
- 既有 F1/F2 召回、归档明确提及加权、source tombstone 与 namespace 过滤保留，不 redesign。

## S1 实现与授权语义

- 请求域由 `MemoryRequestScope(owner, lane, session_id, chat_type, purpose)` 表示；episode 的显式授权保存在 `memory_episodes.metadata_json["access"]`，不修改冻结 Cognitive schema。
- `access` 必须明确给出 owner、lane、session_scope、chat_type 和 purposes；`session_scope=session` 时还必须有匹配的 session_id。缺失请求域、缺失/不完整授权、任一域不匹配、namespace 不匹配、repository 不可用或鉴权异常均 fail closed。
- `memory.cognitive.context_mode` 支持 `off`、`shadow`、`active`；新配置与升级默认值为 `shadow`，缺失、损坏或未知值也回退到 `shadow`，显式用户配置在升级时保留。
- `off` 不执行 Cognitive 检索/注入，但保留原生 Continuity；`shadow` 保留既有检索和上下文审计，但 Cognitive 文本不得进入最终模型请求或回复前 appraisal；`active` 在 appraisal 前鉴权，并在最终注入前再次鉴权以防 TOCTOU。
- 鉴权复用 `CognitiveMemoryLibrary.get_historical()`，并复核 memory/source tombstone、状态、namespace 和显式 access；dormant 记录仅在 `explicit_recall=True` 时可通过。
- 拒绝审计只记录 ID 与 reason code，不记录 memory summary 或 source key。既有 F1/F2 检索算法、Study salience、明确回忆加权、dormancy/archive、source tombstone、physiology 和条目/字符上限保持不变。
- 仅在既有 `api_server` 本地 owner DM 白名单分支设置 `User`/`dm` 请求域；其他入口不猜测归属，在 `active` 下缺少显式请求域时拒绝注入。

## 测试发现基线

命令使用隔离 `HONEYOS_HOME=/tmp/honeyos-s0-collect`、集成树 `PYTHONPATH` 和既有 W venv，仅执行 `pytest --collect-only -q`，未运行测试或模型。

- 收集结果：`1172 tests collected, 6 errors in 2.85s`。
- 6 个错误均为既有重复测试模块 basename 导致的 `import file mismatch`：Study 的 `test_api_server_routes.py`、`test_models.py`、`test_repository.py`、`test_service.py`、`test_validation.py`，以及 `understanding_v2/test_runtime_shadow.py`。
- 完整发现输出仅保存在临时文件 `/tmp/honeyos-s0-test-discovery.txt`，不纳入交付，不含生产数据库副本。
- 本阶段只运行 S1 新测试及相邻 Cognitive/配置定向测试，不以此基线为由清理缓存或修改无关测试。

## S1 定向验证

所有测试均使用集成树 `PYTHONPATH=/home/zyh20/projects/honey-os-integration`、既有 `/home/zyh20/projects/honey-os/.venv/bin/python`、 `/tmp` 下隔离 `HONEYOS_HOME`/临时 SQLite，不读取或写入真实 `~/.honeyos` 数据库。测试命令统一附加 `-p no:cacheprovider`。

最终复跑命令：

```bash
HONEYOS_HOME=/tmp/honeyos-s1-verify-final \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/memory/test_cognitive_scope_gate.py \
  tests/honeyos/memory/test_runtime_context.py \
  tests/honeyos/memory/test_runtime_shadow.py \
  tests/honeyos/test_config.py
```

| 验证目标 | 结果 |
| --- | --- |
| 上述四个测试文件合并复跑 | `78 passed, 1 failed in 15.91s` |
| `tests/honeyos/memory/test_cognitive_scope_gate.py` 单项 | `17 passed` |
| `tests/honeyos/memory/test_runtime_context.py` 单项 | `32 passed` |
| `tests/honeyos/memory/test_runtime_shadow.py` 单项 | `15 passed` |
| `tests/honeyos/test_config.py` 单项 | `14 passed, 1 failed`（唯一失败见下） |
| 五个修改过的生产模块 `python -m py_compile` | `PY_COMPILE_OK` |
| `git diff --check` | 通过（无输出） |

新增隔离测试覆盖正常 DM、owner/lane/session/chat_type/purpose 不匹配、缺失 access/repository、roleplay 隔离、dormant 明确回忆、archive、Study salience 顺序、source 撤销/TOCTOU、三种模式、非法模式回退及条目/字符上限。对应函数包括 `test_normal_dm_allows_matching_access_and_audit_has_no_private_text`、`test_cross_scope_and_purpose_are_fail_closed`、`test_missing_access_and_missing_repository_never_inject`、`test_context_mode_gate_controls_model_visibility`、`test_missing_mode_defaults_to_shadow`、`test_source_revocation_is_rechecked_at_injection_time` 等。

## 已知既有失败：SOUL 前缀断言

- 测试函数：`tests/honeyos/test_config.py::test_upgrade_companion_capabilities_is_idempotent_and_preserves_user_state`。
- 失败断言：`assert first_soul.startswith("# My formed identity")`（当前分支第 271 行）。
- 实际值：升级后的 SOUL 以 `# HoneyOS Relationship` 开头，用户原文 `# My formed identity ... Keep me.` 被保留在模板后部。这是 `upgrade_companion_capabilities()` 既有的 companion v2 模板迁移行为，位于 `honeyos/companion/config.py` 的 `# HoneyOS Relationship` 迁移分支，本阶段未修改。
- 对照实验：用 `git worktree add --detach /tmp/honeyos-s1-baseline-head dba87b94ad17377c78199fed88c248512768db1e` 在冻结 HEAD 上以相同 Python、相同依赖、相同 `pytest` 参数运行同一测试，结果同样在 `assert first_soul.startswith("# My formed identity")` 失败（冻结版本第 245 行），失败文本与当前分支一致。对照 worktree 已用 `git worktree remove` 清理，未改动其他工作树。
- 归因结论：**既有基线失败，非 S1 引入**。S1 对 `tests/honeyos/test_config.py` 的改动仅为新增 `memory.cognitive.context_mode == "shadow"` 断言，该断言在失败点之前已通过；未修改 SOUL、模板或迁移逻辑。因此不修改 SOUL 语义，也不修改该既有断言。

## 阶段状态

| 阶段 | 状态 |
| --- | --- |
| S0 基线与分支 | DONE / FROZEN |
| S1 Cognitive 权限 | DONE / FROZEN |
| S2 统一有界上下文与 Codex 通道 | DONE / FROZEN（详见 `S2_CONTEXT_TRANSPORT.md`） |
| S3–S10 | NOT_STARTED，未获本轮执行授权 |

## S0/S1 冻结记录

| 项目 | 值 |
| --- | --- |
| 基线 HEAD（S0 冻结提交） | `dba87b94ad17377c78199fed88c248512768db1e` |
| S1 实现提交 | `64089936705ded48758b335bf68b5280567bae1d` |
| 最终提交（本冻结记录所在提交） | 用 `git log -1 --format=%H -- docs/honeyos-target/EXECUTION_BASELINE.md` 查询；该提交仅含本文件 |
| 任务分支 | `feat/s1-cognitive-scope-gate` |
| 提交范围 | 7 个修改文件 + 2 个新增文件，全部属于 S0/S1 |

S1 实现提交 diff stat（基线 HEAD → `6408993`）：

```text
 honeyos/agent/turn_context.py                |  94 +++++---
 honeyos/companion/config.py                  |   8 +
 honeyos/gateway/platforms/api_server.py      |   2 +
 honeyos/memory/runtime_context.py            | 329 +++++++++++++++++++++++++--
 honeyos/memory/runtime_shadow.py             |   4 +
 tests/honeyos/memory/test_runtime_context.py |  40 +++-
 tests/honeyos/test_config.py                 |  26 +++
 7 files changed, 453 insertions(+), 50 deletions(-)
```

另有新增文件 `tests/honeyos/memory/test_cognitive_scope_gate.py`（17 个用例）与 `docs/honeyos-target/EXECUTION_BASELINE.md`。

验收结论：

- Cognitive 默认开关为 `shadow`，`off`/`shadow`/`active` 行为与 fail-closed 语义由定向测试覆盖。
- `off` 不执行 Cognitive 检索/注入；`shadow` 不产生模型可见注入；`active` 必须通过 owner/lane/session/chat_type/purpose/namespace/tombstone 全部检查。
- 未改动原生 Memory/Continuity、F1/F2 检索、Study salience 与归档语义（`runtime_shadow.py` 仅新增 `explicit_recall` 标志）。
- `git diff --check` 无输出；工作区无无关 dirty/untracked 文件；测试未读写真实 `~/.honeyos`。

## 开销、残余限制与回滚

- 新增模型调用：0；测试模型调用：0；token/付费调用费用：0。
- 历史 episode 没有显式 `access` 时会在 `active` 下拒绝注入；这是 S1 的 fail-closed 设计，本轮不做历史数据迁移。
- 未配置明确 owner/chat_type 的其他入口在 `active` 下同样拒绝注入，不在 S1 猜测或扩大授权。
- 已知既有失败 1 项（SOUL 前缀断言），已在上节用冻结 HEAD worktree 对照证明非 S1 引入；未运行全量测试，S0 的 6 个重复 basename 收集错误同样保持原状。
- 遗留风险：`active` 模式的真实会话覆盖面尚未接入新的鉴权数据，上线前需要单独评估（属于后续阶段，不在 S1 范围）。
- 未修改生产数据库、systemd、live `PYTHONPATH` 或运行中服务；未 merge、push、部署。
- 回滚：在 `feat/s1-cognitive-scope-gate` 上执行 `git revert 64089936705ded48758b335bf68b5280567bae1d` 并撤销本冻结记录提交；或直接切回 `integration/u2-v2-off`。不使用 `git reset --hard`/`git clean -fd`。

