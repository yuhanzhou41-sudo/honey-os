# U2 v2 整合冻结记录（2026-11-22）

## 冻结标识

| 项目 | 值 |
| --- | --- |
| 工作树 | `/home/zyh20/projects/honey-os-integration` |
| 分支 | `integration/u2-v2-off` |
| 基线 commit | `d7da159c`（W：`feature/chat-message-batching`） |
| 整合 commit | `86270f61` |
| 冻结 commit | 本文件所在 commit |
| 状态 | 本地提交；未推送、未合并、未部署 |

## 范围

- Phase I：Study salience 对齐、U2 v2 子系统/测试/文档迁入。
- Phase II-A：`config.py`、`distillation.py`、`gateway/run.py`、
  `api_server.py`、`test_config.py` 最小接线。
- Phase II-B：`MemoriesPage` 增加“Honey 的理解”分区，`companion.ts`
  管理客户端，分页与 namespace 下发。
- Phase II-C：关闭态恢复门禁、lane/namespace 合同核对、端到端隔离验收。

U2 v2 **保持默认关闭**（`memory.distillation.understanding.enabled=false`），
**未接入 R5 active context**，未启用 producer，未修改 G2、physiology_shadow、
momentary_state、Cognitive、Continuity 的既有架构。

## 实际文件清单（commit 86270f61，62 files）

### 修改（9）

- `frontend/src/api/companion.ts`
- `frontend/src/features/memories/MemoriesPage.tsx`
- `honeyos/companion/config.py`
- `honeyos/companion/distillation.py`
- `honeyos/companion/react_dist/index.html`
- `honeyos/gateway/platforms/api_server.py`
- `honeyos/gateway/run.py`
- `honeyos/memory/runtime_shadow.py`
- `tests/honeyos/test_config.py`

### 删除（2）

- `honeyos/companion/react_dist/assets/index-8gOYoqcw.js`
- `honeyos/companion/react_dist/assets/index-Bfsq2Ji_.css`

### 新增（51）

前端：

- `frontend/src/features/memories/MemoriesPage.test.tsx`
- `honeyos/companion/react_dist/assets/index-DkedtfIT.css`
- `honeyos/companion/react_dist/assets/index-nSc9lq6j.js`（本树重新构建）

Study salience：

- `honeyos/memory/salience.py`（SHA256 `ce3160d4…64454`）
- `honeyos/study/memory_salience.py`（SHA256 `3017ae54…cc21`）

U2 v2 模块（19）：

- `honeyos/understanding/__init__.py`
- `honeyos/understanding/continuity_adapter.py`
- `honeyos/understanding/contracts.py`
- `honeyos/understanding/fact_adapter.py`
- `honeyos/understanding/fact_index.py`
- `honeyos/understanding/index.py`
- `honeyos/understanding/retrieval.py`
- `honeyos/understanding/u2_cli.py`
- `honeyos/understanding/u2_context.py`
- `honeyos/understanding/u2_contracts.py`
- `honeyos/understanding/u2_maintenance.py`
- `honeyos/understanding/u2_manage.py`
- `honeyos/understanding/u2_pipeline.py`
- `honeyos/understanding/u2_policy.py`
- `honeyos/understanding/u2_proposer.py`
- `honeyos/understanding/u2_runtime.py`
- `honeyos/understanding/u2_search.py`
- `honeyos/understanding/u2_sources.py`
- `honeyos/understanding/u2_store.py`
- （`contracts.py` 等共享模块随 U2 v2 一并纳入）

测试（12 个测试文件 + fixture）：

- `tests/honeyos/understanding_v2/test_context_budget.py`
- `tests/honeyos/understanding_v2/test_diary_context_modes.py`
- `tests/honeyos/understanding_v2/test_failures.py`
- `tests/honeyos/understanding_v2/test_management.py`
- `tests/honeyos/understanding_v2/test_management_api.py`
- `tests/honeyos/understanding_v2/test_r7_offline_readiness.py`
- `tests/honeyos/understanding_v2/test_replay_revocation.py`
- `tests/honeyos/understanding_v2/test_runtime_shadow.py`
- `tests/honeyos/understanding_v2/test_scale.py`
- `tests/honeyos/understanding_v2/test_state_bias.py`
- `tests/honeyos/understanding_v2/test_transports.py`
- `tests/honeyos/understanding_v2/test_u2_engineering.py`
- `tests/honeyos/understanding_v2/fixtures/eval_manifest.json`

文档（13）：

- `docs/understanding_v2/DIARY_STATE_MEMORY_AUDIT.md`
- `docs/understanding_v2/R4_AUTONOMOUS_UNDERSTANDING.md`
- `docs/understanding_v2/R4_DATA_CONTRACT.md`
- `docs/understanding_v2/R4_MODEL_SEMANTIC_AUDIT.md`
- `docs/understanding_v2/R4_MODEL_SYNTHETIC_REPORT.json`
- `docs/understanding_v2/R4_R7_CLOSEOUT_REPORT.md`
- `docs/understanding_v2/R5_EVAL_PROTOCOL.md`
- `docs/understanding_v2/R5_FINAL_CONTEXT_AUDIT.md`
- `docs/understanding_v2/R5_SHADOW_ABCD_REPORT.md`
- `docs/understanding_v2/R5_STATE_SOURCE_AUDIT.md`
- `docs/understanding_v2/R6_R7_USER_ACCEPTANCE_CHECKLIST.md`
- `docs/understanding_v2/R6_UI_AND_PERMISSIONS.md`
- `docs/understanding_v2/R7_OFFLINE_READINESS.md`

评估脚本：

- `scripts/eval_understanding_v2.py`

## 已通过测试

后端（临时 `HONEYOS_HOME`，fake 模型/合成数据）：

- `test_u2_engineering.py`：19 passed
- `test_management.py` + `test_management_api.py` + `test_config.py`
  + `test_memory_distillation.py`：47 passed
- `test_companion_web.py`：72 passed
- `test_replay_revocation.py` + `test_context_budget.py`：4 passed

前端：

- `pnpm typecheck`：通过
- `pnpm build`：通过
- `MemoriesPage.test.tsx`：8 passed
- 全前端：91 passed

## 在原 W 基线复现的既有失败（3 项，未修）

1. `tests/honeyos/test_config.py::test_upgrade_companion_capabilities_is_idempotent_and_preserves_user_state`
   —— SOUL.md 前置标题导致 `startswith("# My formed identity")` 失败，W 基线同样失败。
2. `frontend/src/features/study/StudyCampusPanel.test.tsx::renders today's courses with their period`
   —— W 基线同样失败。
3. `frontend/src/features/study/StudyCampusPanel.test.tsx::shows the no-course-today state only after a confirmed capture`
   —— W 基线同样失败。

## 未包含内容

- 私人记忆数据库、`*.db`、凭证、生产 `config.yaml`、systemd/PYTHONPATH 配置。
- `__pycache__`、`.vite` 缓存、临时探针脚本。
- R 工作树旧 `react_dist` 产物（本树已重新构建）。

## 残余风险

- 本冻结仅代表工程整合完成，不代表 U2 语义质量合格。
- 关闭态恢复已加门禁；恢复仍随蒸馏调度触发，而非 Gateway 启动任务。
- U2 未启用、未部署；上线需单独授权并完成配置、备份、发布与回滚流程。
- R5 active context 未接入。
