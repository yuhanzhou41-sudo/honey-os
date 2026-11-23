# HoneyOS Phase S4.5 — 用户理解图谱与原生记忆召回整合

**冻结状态: PARTIAL（后端安全接线 + 图谱 API + 图谱页面已交付；旧窗口补偿与全量端到端网关验收未完成）**

本文件从 `ffb36b0f` 继续，记录本轮增量。

## 0. 元信息

| 项目 | 值 |
|---|---|
| 分支 | feat/s4-5-user-understanding-graph |
| 起始 HEAD | ffb36b0f |
| 本轮提交 | 90b3370c (安全+A/C/D/E) → cfd8e100 (图谱 API+页面) → 本次冻结 |
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

后端（相同环境、相同命令）：
- 定向：test_s45_u2_samebatch(7) / test_s45_understanding_api(4) / S3 / memory /
  companion / test_s4_emotional_imprint 全通过。
- 大范围：`pytest tests/honeyos/`（排除 aiohttp/study/understanding_v2 重依赖）
  → **899 passed / 18 failed / 18 skipped**。18 个失败均属预先存在集群
  （campus、turn_router_shadow、branding、cli、config、distribution、
  install_script/installer、repository_surface），与本轮改动无关；本轮未新增失败。

前端：
- `npm run typecheck` 通过。
- `npm run build` 通过（react_dist 重新生成）。
- `vitest run`：94 passed（含新增 UnderstandingPage.test.tsx）。

真实模型调用 0；token 0；费用 0。

## 8. 模型调用 / token 成本

| 项目 | ffb36b0f | 本轮 | 变化 |
|---|---|---|---|
| 普通聊天主模型 | 每轮按路由 | 每轮按路由 | 无变化 |
| MemoryDistiller | 每批 1 次 | 每批 1 次 | 无变化 |
| U2 二次 LLM | 0 | 0 | 无变化（仍为 0） |
| 图谱打开 | — | 纯 SQLite 查询 | 不调用模型 |
| 外来历史 physiology | 有 | **移除** | 略降 |
| 新增长期记忆读写 | — | 图谱只读查询 | 可忽略 |

## 9. 未完成 / PARTIAL 项

1. **全量端到端网关验收（8 个场景）**：已用临时 DB + 单测覆盖关键数据流
   （U2 解析/映射、apply_proposal、证据过滤、图谱 API、页面渲染），但未启动
   隔离 Gateway + 真模型跑完整 8 场景。属验收深度不足，非功能缺失。
2. **人工浏览器交互验收**：页面已 build + 组件测试，但未在真实浏览器点选回归。
3. **旧窗口 6 单位 / 40 条尾部门槛补偿（Task I）**：仅确认语义，未做只读专项核对
   与最小补丁。
4. **Study 资料接入图谱**：保持原边界，未接入。
5. **外来历史共享硬上限（3 条 / 900 字符）**：runtime_shadow 已有自身预算，
   未做 DeepSeek+Study 合并共享上限的专项改造与测试。

## 10. 回滚

```
git revert <freeze-commit>
git revert cfd8e100      # 图谱 API + 页面
git revert 90b3370c      # 安全 / A C D E
git checkout feat/s4-longterm-memory-emotional-imprint   # 回到 S4
```

## 11. Git

```
<freeze>  docs(s4.5): freeze graph page, API and memory-safety fixes
cfd8e100  feat(s4.5): user-understanding graph page + graph API
90b3370c  fix(s4.5): apply_proposal U2 writes; pure external history;
          evidence-based physiology; imprint into recall context
ffb36b0f  docs(s4.5): freeze full backend delivery
```

- 工作树：clean（除本冻结文档）
- push / merge / deploy：未执行

## 12. 数据兼容 / 迁移

无 schema 变更。理解库沿用 understanding_v2.db；continuity 沿用既有表 + S4
sidecar（CREATE IF NOT EXISTS）。U2 写入改为 apply_proposal，向后兼容既有 labels
与 evidence；旧数据无需迁移。

## 13. 后续建议

1. 隔离 Gateway + fake model 跑完 8 场景，补齐 Task I 旧窗口核对。
2. 浏览器真机点选验收图谱。
3. DeepSeek+Study 共享硬上限专项。
