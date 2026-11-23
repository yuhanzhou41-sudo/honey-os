# HoneyOS Phase S4.5 — 用户理解图谱与原生记忆召回整合

**冻结状态: DONE / FROZEN（本地冻结；8 场景隔离网关端到端、真实浏览器交互、6/40 旧窗口核对、共享硬上限、历史失败归因，以及 Round 2 的证据/状态同步、图谱记忆详情+时间轨迹、5 个陈旧测试修复均已完成；未 push / merge / deploy）**

> 最终验收细节见 [S4_5_FINAL_ACCEPTANCE.md](./S4_5_FINAL_ACCEPTANCE.md)。

本文件从 `ffb36b0f` 继续，记录本轮增量。

## 0. 元信息

| 项目 | 值 |
|---|---|
| 分支 | feat/s4-5-user-understanding-graph |
| 起始 HEAD | ffb36b0f |
| 本轮提交 | 90b3370c (安全+A/C/D/E) → cfd8e100 (图谱 API+页面) → 11081124 (graph page/API freeze) → 093b656f (hook 修复) → 86a8110a (验收冻结) → d22e7daf (记录哈希) → cded7b39 (Round 2 缺陷修复+功能补齐) → `9731fc11` (Round 2 文档冻结) |
| S4 基线 | dff89780 |
| push / merge / deploy | 未执行 |

## 1. 本轮相对 ffb36b0f 的实际变化

1. **U2 写入不再绕过业务规则（Task A）**
   `gateway/run.py::_honeyos_u2_post_completed` 改为构造 `Proposal` 并调用
   `understanding.u2_maintenance.apply_proposal`（与 U2 policy pipeline 同一
   校验写入路径），不再直接 SQL。新助手 `_honeyos_u2_evidence_meta` 把模型
   引用的 operation_index 解析为真实、仍 active 的 continuity memory，并丢弃
   `forgotten` / 非资格 kind（open_loop / temporary_state）。`apply_proposal`
   负责 user_suppressed 拒绝、证据元数据校验、幂等重放、grade/state 推导。

2. **原生生理加权改为证据驱动（Task C）**
   `continuity.context_for_lane` 删除 kind 梯度（不再假设 episode>commitment>）。
   仅当某条记忆存在 S4 已确认的 `known` 情绪印记时，才在 `_score>=3` 准入后
   获得有界 boost（上限 0.12，静息时衰减为 0）。无印记 → 保持原排序。

3. **外来历史纯检索（Task D）**
   `memory/runtime_shadow.py` 不再读取 Honey 当前生理状态。DeepSeek 导入记忆
   上由 epinephrine 派生的 state_boost 已移除。salience（personal_relevance /
   user_emphasis / 记忆自带 arousal）仍参与重排，但当前模拟状态不再影响它。

4. **S4 印记进入真实回忆上下文（Task E）**
   `context_for_lane` 对 `known` 印记追加一条显式标注为「历史情绪印记 / 当时的
   状态，不代表此刻感受」的有界提示；unknown/neutral 不添加任何内容。已遗忘
   记忆因 list_active 过滤不会进入。

5. **图谱 API（Task G）** `honeyos/runtime/web_routers/understanding.py`
   - GET /api/understanding/graph（分页、owner 作用域、含 evidence + 记忆预览 + 印记）
   - GET /api/understanding/labels/{id}
   - POST /api/understanding/labels/{id}/suppress（忘记标签，不删记忆；返回不再含正文）
   - DELETE /api/understanding/labels/{id}/evidence?ref=（只解除一条关系）
   evidence 若指向已遗忘/不存在的原生记忆则被丢弃 → 用户忘记不会经图谱复活。

6. **图谱页面（Task F）** `frontend/src/features/understanding/`
   路由 `/understanding`，导航「Honey 对我的理解」。SVG 节点图（标签←→记忆，
   支持实线 / 反证虚线），平移+滚轮缩放+重置；分类/时间筛选；点击标签展开详情
   （类别、范围、状态、修订、支持/反证、记忆 kind/时间、known 印记）；操作：忘记
   标签、解除关联；空态与错误态。

7. **emotion hook → 异步 U2 转发修复（最终验收发现）**
   `emotional_imprint.py::emotion_imprint_hook_factory` 的同步 hook 曾调用
   （S4.5 已 async 的）`_honeyos_u2_post_completed` 却不 await，协程被丢弃，
   导致真实 Gateway 路径下 U2 同批次写入被静默跳过。现 hook 返回 downstream
   的返回值，由 `MemoryDistiller` 检测 awaitable 后 await；同步 downstream
   行为不变。回归测试 `test_s45_e2e_acceptance.py::test_scenario_1b_...` 覆盖。

8. **Round 2：证据/状态同步 + 图谱交互补齐（缺陷修复，提交 `cded7b39`）**
   - `u2_maintenance.recompute_label` 在解除关联、来源撤回（记忆被遗忘/归档）、
     反证变化后，用当前仍有效的证据重算 grade/state，修剪指向失活来源的孤儿
     证据；`user_suppressed` 标签绝不复活。`_archive_current` 懒创建
     `label_versions`，存量库缺表不再 500；读侧对缺表降级为空时间轨迹。
   - `continuity._recompute_u2_for_memory` 在记忆 forgotten / 自动归档时触发
     重算（fail-open，不阻塞 continuity 变更）；`gateway/run.py` 与
     `u2_pipeline` 透传 `continuity_db_path`，使写入与恢复路径都针对真实库。
   - 图谱页面：记忆节点可点击查看完整详情与「相关标签（N）」；标签详情新增
     独立「时间轨迹」（形成/支持/反证/修订，含 actor 与状态变化）。
     `GET /labels/{id}` 返回 `versions`，forget 后正文与历史版本快照均遮罩。
   - 5 个 `understanding_v2` 陈旧测试更新为现行契约（未删除/跳过）；新增回归
     `test_s45_evidence_state_recompute`、`test_s45_u2_not_injected_into_chat`。

## 2. 保持不变的既有机制

- MemoryDistiller 触发阈值（20 条 / min_tail 6 / max_batch 40 / 日记权重 3）、
  五种记忆模式、`_score`、operations 各分支（compress/reinforce/update/resolve）、
  一次模型调用。
- `understanding_v2.db` schema（labels/evidence/postings）；U2 policy/sources/
  continuity_adapter/management 未改，仅改为复用 `apply_proposal`。
- G2 两套 DB 与晋升规则；S3.1 自动观察。
- open_loop 完成/隐藏/解决状态机；U2 不纳入 open_loop。
- S4 sidecar schema 与 known/unknown 分类（neutral 保留 CHECK）。
- 九项 momentary_state / 九项 physiology_shadow 定义。
- Study 学习系统、DeepSeek 来源身份。
- 原生记忆手动遗忘（continuity status / cognitive tombstone）语义。

## 3. 检索分流

| 来源 | 召回依据 | physiology |
|---|---|---|
| 原生 continuity（长期记忆/episode/commitment/open_loop） | 话题相关 + 既有评分 + 有界印记 boost | 仅 known 印记、有界、静息归零 |
| 外来 DeepSeek（cognitive_memory） | 纯相关性 + salience | **不使用**当前生理状态 |
| Study | 保持原访问边界（未接入本图谱） | 不涉及 |

## 4. physiology 加权公式

```
phys_factor = min(0.12, max(0, epinephrine - 0.05) * 0.18)     # 静息 0
boost(item) = phys_factor if item 有 known 印记 else 0
final_score = lexical_score + boost(item)     # 仅对 lexical_score>=3 的候选
```
证据驱动、有界、类别无关；强情绪不会把无关记忆推过准入阈值；状态过期→0。

## 5. S4 印记读取链

distill → sidecar known/unknown（写入）→ `context_for_lane` 读取 → known 才追加
「历史印记」提示进入聊天上下文。unknown 不产生情绪描述；历史印记不覆盖当前状态；
不因重复召回强化；不增加 U2 置信度；不新增模型调用。

## 6. 用户手动遗忘 vs 自动归档

- continuity `status`：active / archived / forgotten。召回走 list_active（仅 active）。
- cognitive：memory_tombstones。
- U2：`labels.state='user_suppressed'`（suppress 接口），正文不再返回；再次整理
  同义提议被 `apply_proposal` 的 PermissionError 拦截，不复活。
- 归档 ≠ 删除；用户忘记优先级最高。本轮未改这些语义。

## 7. 测试

后端（相同环境、相同命令、`--import-mode=importlib`）：
- 新增验收集合：`test_s45_e2e_acceptance.py`（8 场景 + hook 组合，9 通过）；
  `test_s45_old_window_thresholds.py`（6/40 边界，9 通过）；
  `memory/test_s45_external_history_shared_budget.py`（共享上限，5 通过）。
- 定向：test_s45_u2_samebatch(7) / test_s45_understanding_api(4) /
  test_s4_emotional_imprint / S3 / memory / companion 全通过。
- **全量 `pytest tests`（本轮最终）：18 failed / 1314 passed / 18 skipped。**
  剩余 18 个失败全部 PRE-EXISTING 且与 S4.5 无关：campus ×2、turn_router_shadow
  ×8、branding / cli / config / distribution ×2 / install_script / installer /
  repository_surface。基线 `dff89780` 全量为 24 failed / 1263 passed；上一冻结
  `d22e7daf` 为 23 failed / 1298 passed；本轮修复 5 个 `understanding_v2` 陈旧
  测试（2 个 `compose_user_api_content` 签名 → 3 参契约、3 个期望废止的独立
  U2 producer 调用 → 同批 `u2_calls==0`），降至 18 failed / 1314 passed，
  **新增回归 0**。详见 `S4_5_FINAL_ACCEPTANCE.md` §8 与 §2b.4。

前端：
- `npm run typecheck` 通过。
- `npm run build` 通过（Round 2 补齐记忆详情/时间轨迹后重新生成 react_dist，新产物已随 cded7b39 提交）。
- `vitest run`：94 passed（含 UnderstandingPage.test.tsx）。

真实模型调用 0；token 0；费用 0。真实浏览器验收见 §4（最终验收报告）。

## 8. 模型调用 / token 成本

| 项目 | ffb36b0f | 本轮 | 变化 |
|---|---|---|---|
| 普通聊天主模型 | 每轮按路由 | 每轮按路由 | 无变化 |
| MemoryDistiller | 每批 1 次 | 每批 1 次 | 无变化 |
| U2 二次 LLM | 0 | 0 | 无变化（仍为 0） |
| 图谱打开 | — | 纯 SQLite 查询 | 不调用模型 |
| 外来历史 physiology | 有 | **移除** | 略降 |
| 新增长期记忆读写 | — | 图谱只读查询 | 可忽略 |

## 9. 验收完成项（原 PARTIAL 已关闭）

1. **全量端到端网关验收（8 场景）**：隔离临时 home/DB + fake extractor，跑通
   Gateway→Distiller→Continuity→U2→API，8/8 PASS（含真实 hook 组合）。
2. **真实浏览器交互验收**：真实浏览器访问隔离服务器上的真实 SPA + 真实 API，
   渲染/筛选/平移缩放重置/详情/印记/忘记标签/解除关联/刷新持久化/空态/错误态
   全部 PASS，控制台无错误。
3. **旧窗口 6/40**：只读核对无静默丢失，新增 9 个边界测试，未改 20/6/40。
4. **外来历史共享硬上限**：来源无关检索器天然共享 3 条 / 900 字符，上下文
   3 / 700；Study 无自动聊天检索入口（如实记录，未伪造接入）。
5. **历史失败归因**：上一冻结 23 个失败全部 PRE-EXISTING（基线同源），新增回归 0。
6. **Round 2 证据/状态同步**：解除关联 / 来源撤回 / 反证变化 / 用户遗忘后重算
   grade/state；孤儿证据修剪；`user_suppressed` 不复活；`label_versions` 缺表
   容错。回归 `test_s45_evidence_state_recompute` 通过。
7. **Round 2 图谱交互**：记忆节点详情 + 相关标签 + 独立时间轨迹；forget 遮罩
   正文与版本快照。真实浏览器复验通过（见验收报告 §2b.6）。
8. **Round 2 陈旧测试修复**：5 个 `understanding_v2` 旧测试更新为现行契约
   （未删除/跳过），全量从 23 failed 降至 18，新增回归 0。

未解决项（均在 S4.5 范围之外，不涉及遗忘/权限/U2 二次调用/待续/预算）：见
`S4_5_FINAL_ACCEPTANCE.md` §14。

## 10. 回滚

```
git revert <freeze-commit>
git revert cfd8e100      # 图谱 API + 页面
git revert 90b3370c      # 安全 / A C D E
git checkout feat/s4-longterm-memory-emotional-imprint   # 回到 S4
```

## 11. Git

```
9731fc11  docs(s4.5): round 2 acceptance update and refreeze
cded7b39  fix(s4.5): recompute label state on evidence/source change; complete graph interactions
d22e7daf  docs(s4.5): record freeze commit hashes
86a8110a  docs(s4.5): final acceptance report and DONE/FROZEN freeze
093b656f  fix(s4.5): forward async U2 producer through emotion hook
          (+ isolated 8-scenario e2e, 6/40 thresholds, shared cap tests)
11081124  docs(s4.5): freeze graph page, API and memory-safety fixes
cfd8e100  feat(s4.5): user-understanding graph page + graph API
90b3370c  fix(s4.5): apply_proposal U2 writes; pure external history;
          evidence-based physiology; imprint into recall context
ffb36b0f  docs(s4.5): freeze full backend delivery
```

- 工作树：clean
- push / merge / deploy：未执行

## 12. 数据兼容 / 迁移

无 schema 变更。理解库沿用 understanding_v2.db；continuity 沿用既有表 + S4
sidecar（CREATE IF NOT EXISTS）。U2 写入改为 apply_proposal，向后兼容既有 labels
与 evidence；旧数据无需迁移。`label_versions`（标签版本时间轨迹）在首次重算时
以 `CREATE TABLE IF NOT EXISTS` 懒创建，读侧对缺表降级为空时间轨迹，故 S4.5
之前升级的存量库无需迁移、详情接口不会 500。

## 13. 后续建议（非阻塞）

1. ~~清理/改写 `understanding_v2` 中反映旧 U2 producer 设计的陈旧测试~~ —— 本轮已完成（见验收报告 §2b.4）。
2. ~~为图谱补「记忆节点点击」与独立「时间轨迹」控件~~ —— 本轮已完成（见验收报告 §2b.3）。
3. ~~修复 `test_transports` 的 `compose_user_api_content()` 签名漂移~~ —— 本轮已完成（见验收报告 §2b.4）。
4. （未来）若产品需要把合法 U2 标签注入聊天上下文，须单独的产品 + 安全授权：
   准确性边界、token 预算、用户可见性与开关；当前保持 fail-closed（见验收报告 §2b.2）。
5. （未来）若需要 Study 资料自动进入聊天检索，同样须单独授权并复用来源无关
   检索器的共享硬上限；当前 Study 仅显式引用阅读（见验收报告 §2b.5）。
