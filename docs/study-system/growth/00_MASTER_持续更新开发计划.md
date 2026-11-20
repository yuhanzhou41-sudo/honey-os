# HoneyOS Study Growth & Learning Memory — 统一开发计划与进度台账

> **唯一入口 / Living Master Plan v1.0** ｜建立：2026-11-19 ｜最近更新：2026-11-20 ｜维护者：执行任务的 AI/Codex 与用户
> **当前阶段：A–J完成；下载入口与外部AI格式说明修正已发布，运行源码6808ea21。**
> **设计基线：`BC-DF-1.0`（B/C 设计已冻结；不等于代码实现、运行验收或生产可用）。**
> **本文件是唯一可修改的主进度台账**；`frozen/` 为规范依据，除正式变更决议外不可随意修改；`archive/` 仅作历史参考，不是当前指令。
> **范围：**计划生成 Skill / StudyPlan Markdown V1/V2 / 多计划时间容量 / 保底与机动 / 阳光和小花盆 / 番茄钟、题库、错题、闪卡 / 学习记忆 / 周评与结束归档 / Qwen 主动联系 / UI、测试和发布。

### 快速导航（只维护这一份主计划）

- **想看当前进度** → [第 1 节进度总览](#1-进度总览每次执行必须维护)；**想查看下一项开发任务** → [第 2 节任务清单](#2-实施路径与任务清单依赖优先于列表顺序)。
- **AI 执行完要记录什么** → [第 4 节进度更新协议](#4-进度更新协议每批必须执行)；**设计有冲突怎么办** → [第 5 节变更控制](#5-冻结规范冲突--变更控制必须审批)。
- **想看还需决定的奖励/通知参数** → [第 6 节决策清单](#6-决策清单不要因-ai-没问就擅自定为事实)；**想交给下一个 AI** → [第 8 节接手提示词](#8-下一个-ai-接手时的最短提示词可直接复制)。
- **单一更新原则**：`frozen/` 只做技术依据，`archive/` 只作历史参考；日常开发进度只更新**本文件**，无需反复改 13 份附件。

### 2026-11-19 用户最新执行决定

用户明确要求缺少冻结包不得阻断开发，审计清楚当前 Honey 状态即可正式实现。此决定覆盖本文所有“必须补齐 frozen/ 才能编码”的旧表述。实现以当前源码、用户目标和主计划明确语义为依据，合理的可逆实现选择由执行者完成并记录。缺失文件只作为历史资料缺口。发布、删除数据及尚未确定的奖励数值仍遵循用户具体授权。

### 2026-11-20 当前有效执行决定

用户明确选择“继续完成 D–J，待定参数采用计划推荐值”，并要求验收提交和计划收尾。本决定覆盖下文历史模板中“D–J未批准”“数值待确认”和缺冻结包前置要求。已按推荐实现，J包括本地运行包部署与可回滚验收；不推送远端、不替用户开启成长或主动监督。历史执行记录保持原样。

## 0. 从这里开始：给接手 AI 的任务说明

**用户目标：**在既有 canonical Study System 基础上，恢复考虑拖延的保底任务与机动机制、阳光和植物奖励；让多个学习计划独立获得奖励与记录，但能综合评估；按计划汇总每日任务/番茄钟/错题/闪卡/成长，进行周总结；计划结束生成且保留一句话最终总结，清理本计划之前的周总结正文；由用户授权的已有主动联系机制与本地 Qwen 进行受限学习监督。同时，Honey 自身制定/修改计划的 Skill、StudyPlan MD 模板、供其它 AI 的编写指南和 Planning Request Builder **必须同步更新**，且所有入口遵守同一契约。

**绝对执行规则（优先于本文件中的任何参考代码和顺序）：**

1. **先读用户目标，核对实际源码，然后再编码。** 本包中的路径、类名、接口、SQL、伪代码和历史提交都只是候选或历史证据，不保证与当前 Windows/WSL、Git 分支或运行版一致。不得盲目照抄：实际方案若无法满足用户目标，先指出错误、给出基于真实代码的最小修订和测试；涉及冻结规则变化时先获得用户确认。
2. **保留现有事实源：**计划定义和修改只能通过实际 canonical `StudyService`；不得重启 legacy `/api/companion/study/*`、旧 Companion Study DB，也不得引入双写。Markdown 只是交换格式，不能自己写数据库。
3. **设计与实现分离：**`BC-DF-1.0` 冻结的是 B/C 的可观察行为，不表示当前 Honey 已支持 V2；V2 codec、模型、持久化、前后端、真实预览/导入验收完成前不得替换正式 V1 模板或对用户承诺 V2 可导入。
4. **统一入口：**Honey Skill、外部 AI 生成的 MD、手动编辑、聊天修改都要走同一语义验证、冲突核查、预览、用户确认、StudyService；无确认不得产生计划/奖励/权限副作用。遵守现有 Phase 5.3 “预览原文→确认同一原文”的真实契约。
5. **权限与事实分离：**外部 AI 只能制定计划，不能发阳光、改植物、声明已学习、配置主动消息授权或写个人记忆；学习事实来自真实事件。计划级写入需绑定可信 `plan_id`，跨计划只读综合、去重。
6. **保护现有数据：**先验明脏工作区和运行/开发版本，迁移前备份并验证恢复，测试用隔离数据；保留已完成任务、番茄钟、错题/闪卡历史，周报清理不等于删除学习历史。
7. **复用而非重造：**番茄钟用原 scheduler/server timestamps；通知和主动联系用原通道；本地小 Qwen 只处理简单结构化评价和短句，复杂计划决策由主模型/用户确认。
8. **Git 安全：**禁止 `git add .`、`git reset --hard`、`git clean -fd`、批量覆盖脏文件、误提交无关改动；尤其要谨慎修改共享 Gateway 文件。每次提交只暂存本任务相关路径或 hunk，审查 staged diff。
9. **分阶段授权：**本文件整理的是完整路线图，**不是一次性运行 D–J、生产部署、删除文件或合并 PR 的授权**。先执行用户指定阶段；遇到关键设计/安全分歧、不可恢复备份缺失、测试失败，暂停并记录。需要进一步写入/发布时明确请求用户批准。
10. **执行后必须维护本台账**：更新首页“当前阶段”、下方进度表、对应任务 checkbox、当批证据与提交日志、最后更新日期、下一步、阻塞事项；**有测试证据才写 `VERIFIED`**，不因生成文件、跑通静态检查或提交代码就声称生产功能完成。

### 文件地图：哪里是权威

| 路径 | 用途 | 后续 AI 能否修改 |
|---|---|---|
| `00_MASTER_持续更新开发计划.md`（本文） | **唯一任务/进度入口、阶段依赖、代码参考入口、验收、提交记录** | **可以；每批必须更新** |
| [`frozen/01_B_计划数据契约_冻结规范.md`](frozen/01_B_计划数据契约_冻结规范.md) | B 的最终域语义、V1 兼容、plan_id、多计划容量 | 冻结，变更需审批 |
| [`frozen/02_StudyPlan_V2_Markdown_格式规范.md`](frozen/02_StudyPlan_V2_Markdown_格式规范.md) | V2 纯文件语法、字段、版本能力、校验和导出 | 冻结，变更需审批 |
| [`frozen/03_C_Honey_Skill_与计划生成链路_冻结规范.md`](frozen/03_C_Honey_Skill_与计划生成链路_冻结规范.md) | C 的四入口、Skill、Builder、编辑链路 | 冻结，变更需审批 |
| [`frozen/04_study-plan-template-v2.DESIGN-FROZEN.md`](frozen/04_study-plan-template-v2.DESIGN-FROZEN.md) | **纯 V2 设计样例**，不是当前生产模板 | 冻结，仅测试样本 |
| [`frozen/05_AI_AUTHORING_GUIDE_V2.md`](frozen/05_AI_AUTHORING_GUIDE_V2.md) | 给其他 AI 阅读的生成指南，**不能导入** | 冻结 |
| [`frozen/06_planning_request_for_external_AI_v2.md`](frozen/06_planning_request_for_external_AI_v2.md) | Planning Request Builder 导出结构，**不能导入** | 冻结 |
| [`frozen/07_Honey_Study_Planning_Skill_增量指令.md`](frozen/07_Honey_Study_Planning_Skill_增量指令.md) | 供实际 Skill **增量融合**，禁止替换整个 system prompt | 冻结 |
| [`frozen/08_BC_验收矩阵与源码审计门禁.md`](frozen/08_BC_验收矩阵与源码审计门禁.md) | B-01～B-19、C-01～C-14 的测试、阻塞条件 | 冻结 |
| [`frozen/09_study-plan-template-v1.LEGACY-FIXTURE.md`](frozen/09_study-plan-template-v1.LEGACY-FIXTURE.md) | V1 黄金兼容样本 | 冻结 |
| [`frozen/00_README_冻结清单与阅读顺序.md`](frozen/00_README_冻结清单与阅读顺序.md)、[`frozen/10_草案差异与修订决策.md`](frozen/10_草案差异与修订决策.md)、[`frozen/11_冻结包静态核验记录.md`](frozen/11_冻结包静态核验记录.md) | 冻结背景、决策及仅文档静态验收记录 | 冻结 |
| [`archive/12_跨模块开发主路线图_BC设计冻结引用版.md`](archive/12_跨模块开发主路线图_BC设计冻结引用版.md) | D–J 详细候选表/伪代码（**历史草案，不高于本文与冻结规范**） | 不维护，历史参考 |

**冲突裁决顺序：**用户最近明确需求与真实安全/数据事实 → 已批准的设计变更 → `frozen/01~03`、`frozen/02` 的具体格式规则 → 本主计划 → `archive/` 候选。若无法既满足用户目标又保持冻结规则，**不私改冻结文档**，记录 RFC 并请求确认。

## 1. 进度总览（每次执行必须维护）

**状态枚举：**`NOT_STARTED` 未开始；`AUDITING` 审计中；`IN_PROGRESS` 实现中；`BLOCKED` 有阻塞；`IMPLEMENTED` 代码/文档已改但未完成实测；`VERIFIED` 已在规定环境通过验收；`RELEASED` 已获授权正式部署且复验；`N/A` 经用户确认不需要。**`DESIGN_FROZEN` 是独立的设计属性，不代表实现状态。**

| 批次/模块 | 核心目标 | 当前实现状态 | 设计状态 | 阻塞/依赖 | 最近证据或提交 | 下一动作 |
|---|---|---|---|---|---|---|
| A / BC-0 | 真实源码、部署/Skill/模板/数据库只读审计 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 源码、生产与恢复副本均已核对 | 已完成，见最终验收报告 |
| B / BC-1~2 | StudyPlan V1/V2 版本化契约、持久化与验证 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 3e2598bc；V1/V2与容量回归 | 已完成，见最终验收报告 |
| C / BC-3~5 | Honey Skill + Builder + 模板 + 四入口兼容 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 3e2598bc；四入口与真实Qwen验收 | 已完成，见最终验收报告 |
| D | 保底/机动/拖延恢复 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 机动CAS/撤销、保底、最多3项恢复 | 已完成，见最终验收报告 |
| E | 奖励流水、阳光、花盆、势能 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 独立流水、冲正、无历史补发 | 已完成，见最终验收报告 |
| F | 关联现有番茄钟、错题、闪卡的学习事件 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 真实事件单归属及教材清理后的事实保留 | 已完成，见最终验收报告 |
| G | 每日 Study Learning Memory / 计划隔离 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 独立日投影、迟到重算、DST与上下文边界 | 已完成，见最终验收报告 |
| H | 周报、跨计划只读评价、一句话归档、清周报 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 独立周报、综合只读、事务结束归档 | 已完成，见最终验收报告 |
| I | Qwen 评估 + 现有主动联系 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | 默认关闭、25类模型校验、消息库幂等 | 已完成，见最终验收报告 |
| J | 渐进式 UI + 端到端验收与部署 | `RELEASED` | 用户已批准实施及推荐参数 | 无 | d443b234；214后端/79前端；Windows和WSL复验200 | 已完成，见最终验收报告 |

**已知历史基线，非本轮检查结果：**2026-11-17 文档记载有运行版 `8fbf718`，已开发 Study 计划、番茄钟、题库、错题、闪卡、Qwen 及提醒；另有多检出目录和历史工作分支。**不得假设上述是本机当前 HEAD，也不能从 GitHub 默认分支找不到文件就断言本机没有相关功能。**

### 本轮目标、范围和实际进度

- **本轮任务**：完成用户授权的A–J开发、验收、本地提交和本机发布。
- **已完成**：B/C版本化与四入口，D–I保底/机动/奖励/学习事件/记忆/周报/归档/主动监督，J界面与发布。
- **验收**：后端214项、前端79项，tsc及Vite构建通过；真实本地Qwen合成案例与Windows Edge隔离页面通过。
- **运行**：`/home/zyh20/projects/honeyos-releases/study-growth-d443b234`；进程PYTHONPATH核实一致，Windows/WSL健康和学习页面200。原2计划/78任务不变，完整性及外键检查通过。
- **交付**：B/C提交3e2598bc，D–J提交d443b234，最后另作台账归档提交；无远端push。
- **下一动作**：本计划无剩余开发任务。成长和主动监督均需用户在界面明确开启。

## 2. 实施路径与任务清单（依赖优先于列表顺序）

状态改写规则：每项任务只有在“验收证据”真实存在时才能从 `[ ]` 改为 `[x]`。如部分完成，仍 `[ ]`，在任务记录中写 `IN_PROGRESS` + 已完成部分；不要凭口头描述勾选。

### Batch 0 — A / BC-0：只读源码审计

**目的**：确认 Honey 当前真实开发/运行位置和已有能力，避免按历史方案覆盖新代码。**不得修改文件、提交、迁移或重启服务。**

- [x] **A-01** 定位真实源码根、WSL 服务实际 ExecStart、运行版/开发版/分支、干净或脏改动、关联前端 bundle、现存备份；记录证据 `path:line` 和 commit。
- [x] **A-02** 审计 StudyPlan/StudyTask/StudyService/StudyRepository、V1 codec/validator、数据库表和 migration；确认已冻结/新增字段。
- [x] **A-03** 审计 Honey 计划 Skill 和 prompt/tool 路由、Markdown 模板下载、Planning Request Builder、手动编辑、预览/确认、聊天修改链路。
- [x] **A-04** 审计其它计划容量查询、番茄钟/错题/闪卡的 plan_id 归属、现有 scheduler 与 proactive/学习记忆读取边界。
- [x] **A-05** 做只读能力矩阵：`已存在 / 待补 / 与冻结规范冲突 / 暂无法证实`；列出 V1 兼容测试基线、拟改文件、风险和需要用户确认的设计变更。

**候选只读命令（先核对实际工作目录、再按需运行）：**

```bash
pwd
 git rev-parse --show-toplevel
 git branch --show-current
 git rev-parse --short HEAD
 git status --short
 rg -n 'study_plan_version|parse_study_plan_markdown|validate_study_plan|planning_request|study-plan-template' .
 rg -n 'StudyService|StudyTask|pomodoro|wrong_answer|flashcard|proactive|study.*skill' .
```

**门禁 A-GATE**：真实代码路径、model/schema、导入/导出/预览、Skill 入口、工作区风险与历史行为有可复查证据；否则不得进入 B 编码。详细核对列表见 [`frozen/08_...`](frozen/08_BC_验收矩阵与源码审计门禁.md)。

### Batch 1 — B/C：版本契约与计划生产端（已实现、验收并发布）

**B：数据契约（先做）**

- [x] **B-01** 从 V1 golden fixture + 运行库脱敏样本建立现有格式测试；确认未知字段拒绝、历史 `review/status/source_type` 语义不变。
- [x] **B-02** 实施 V2 typed domain：`priority=must|standard|optional`、`minimum_required`（只能在 must）、`kind=study|review|quiz|flashcard`，以及**独立 `flex_slots`**（不能作为任务）；空任务日不可判完成。新增字段必须覆盖 model、validator、persistence 和 export。
- [x] **B-03** 为 Markdown V1/V2 建统一版本分流、严格 unknown-key/日期/任务顺序/时长校验；纯 V2 文件 parse/export/parse 语义无损，V2→V1 有损时明确拒绝或警告确认；外部 `done`/阳光/主动授权不能变为真事实。
- [x] **B-04** 规划可恢复的增量迁移；在隔离库执行升级/回退实验，不回填伪造奖励/保底；旧真实学习记录完整保留。
- [x] **B-05** 校验多计划可用容量：其它活跃计划任务分钟+机动分钟、本计划候选、真实总上限；修改 A 时以候选 A **替代旧 A** 计算，避免重复；无可信容量则显示“未核实”。
- [x] **B-06** 运行 `B-01～B-19` 验收矩阵、V1/V2 兼容与并发/权限验证；记录真实命令/输出与缺陷，实测通过后才认为 B `VERIFIED`。

**C：Skill、模板与四入口（在 B 的 schema 稳定后）**

- [x] **C-01** 核实并增量修改 Honey 内部 Study Planning Skill：读取真实资料与其它活跃计划占用，合理分 must/standard/optional、低状态保底、review/quiz/flashcard、独立机动容量；不允许模型直接写 SQLite、奖励或权限设置。
- [x] **C-02** 确立可信的 `supported_schema_version`（来自真实运行能力而非文档），模板下载/生成 Skill/Planning Request Builder 同源读取；只有真实 B/C 运行验收通过后向用户开放 V2；此前继续 V1。
- [x] **C-03** 更新 `study-plan-template.md` 的实际下载链路：V1 保留；目标 V2 只包含以 `---` 开始的 YAML+Goals+Schedule，纯文件不混代码围栏、提示词或尾注；notes 独立。
- [x] **C-04** 更新外部 AI 生成指南和 `planning_request.md` 导出：只发必要个人资料、真实容量快照与经核实的模板版本；`study_plan.md` 与 `planning_notes.md` 分离。
- [x] **C-05** 手动编辑、Honey 新建、MD 导入、聊天修改全部采用同一 canonical validate→容量检查→preview→确认→StudyService；修改现有计划走按 ID 的 diff/patch，不覆盖已完成事件。
- [x] **C-06** 运行 `C-01～C-14` 验收矩阵；双计划、过期预览、用户取消/并发、非法字段、prompt injection、下载模板实际导入全部通过后，才将 C 标记 `VERIFIED`。

**门禁 BC-GATE**：B/C 均 `VERIFIED`；V1 仍可实际导入，V2 真实 preview/import/export 成功，Skill/Builder/外部/手动语义一致；**不得把 B/C `DESIGN_FROZEN` 误当成 `VERIFIED`**。任何设计冲突走“第 5 节变更单”。完成后提供 `BC_验收报告.md` 并请求用户批准下一批 D/F/E。

**重要参考路径（全部需用 `rg` 核实）：**`honeyos/study/models.py`、`honeyos/study/markdown.py`、`honeyos/study/validation.py`、`honeyos/study/service.py`、实际 repository/store、`honeyos/gateway/platforms/api_server.py`、`frontend/src/features/study/StudyPage.tsx`、`frontend/src/api/study.ts`、Skill/prompt 下载接口。**这不是固定改动文件列表。**

### Batch 2 — D + F + E：执行逻辑、行为事件与奖励（已批准并完成）

- [x] **D-01** 实现任务类型/优先级展示、日完成等级（最高等级 full→standard→minimum→incomplete，空日 no_tasks）与用户开启的保底模式；不自动改旧计划。
- [x] **D-02** 实现机动槽定义→可用容量→消耗/撤销的服务层；保留 task_id/计划 ID、原日期及修改历史，**不把机动当未完成任务**。
- [x] **D-03** 只生成延期恢复 proposal（优先少量关键任务），用户确认后才变更，不能把所有拖延任务强制堆到下一天或挤占其它计划。
- [x] **F-01** 审计并复用现有真实 Pomodoro/Review/Flashcards 事件，不重写原状态机；明确每次真实事件的来源键、时间和归属。
- [x] **F-02** 支持未分配事件、计划切换归属和跨入口去重；不得通过模型猜题目“掌握”或用一次专注为两个计划同时记时。
- [x] **E-01** 用户确认奖励数值/植物成长/里程碑策略后建立**每计划独立** reward ledger（来源唯一+冲正）、小花盆阶段、学习势能；旧分值仅候选，防重试/双击刷分。
- [x] **E-02** 成长视图显示真实积分和阶段，未达标不处罚性枯萎；真实练习/复习奖励仅由 F 的有效事件驱动。
- [x] **DFE-TEST** 用两计划、3 天拖延、取消改期、重复回调、任务撤销、跨日与共享错题/闪卡做验收；通过后更新主台账。

**门禁 DFE-GATE**：跨计划写入完全隔离、奖励可追溯且可重算、现有 Pomodoro/Review 回归通过；否则不进入学习记忆。

### Batch 3 — G：独立 Study Learning Memory（已批准并完成）

- [x] **G-01** 先审计现有 Study/MemoryManager，设计独立学习记忆的物理/逻辑边界；必要时另建存放可重建投影的数据库，不做同一学习事实的跨库双写。
- [x] **G-02** 实现以 `(plan_id, local_date, projection_version)`（概念键）为粒度的日快照：任务、有效专注、错题、闪卡、机动、奖励和植物；所有数值后端计算，Qwen 不造数。
- [x] **G-03** 复用 scheduler，按用户时区定时更新（23:00 仅候选）；支持迟到数据重算、DST/重启补跑、幂等、失败重试和 23:30 日记共存。
- [x] **G-04** 构建 Context Adapter：学习话题/显式提问/已授权主动监督时才查询，提供来源与限额；普通聊天/人格/个人记忆不得吞入学习流水账。
- [x] **G-TEST** 双计划日快照隔离、无数据日不编造、跨天/补录/重试一致、来源和遗忘边界可审计。

### Batch 4 — H：每周评估与最终一句话归档（已批准并完成）

- [x] **H-01** 规则式计算每计划周完成率、专注、错题/闪卡趋势、机动使用与奖励变化；多计划只读综合，避免重复计时/奖励。
- [x] **H-02** Qwen 可仅基于汇总生成短说明，数字以规则结果为准，模型离线时可静态生成；周报默认各计划独立（待用户最终确认）。
- [x] **H-03** 区分计划真正 `completed`、用户 `stopped` 与到期待确认；用户确认结束后先存最终结构化统计和**仅一句话**总结，再清理该计划过往周报正文、生成缓存及索引。
- [x] **H-04** 审计周报是否有普通聊天副本；不得擅自删除用户聊天历史或其它计划周报；保留每日快照、练习记录和最终一句话。
- [x] **H-TEST** 计划 A 结束，B 继续；中途失败重试只清 A 周报且最终数据存在，重复关闭不重复删除，来源可追溯。

### Batch 5 — I：Qwen + 现有主动联系（已批准并完成）

- [x] **I-01** 基于真实规则识别当天未启动、剩余时长过载、积压、完成目标、周报可读等触发，不由 Qwen 自己推算事实或决定写入。
- [x] **I-02** 给本地 Qwen3-4B 紧凑 JSON 输入、严格 JSON 输出和 80 字级短消息上限；校验/回退，20～30 个模拟案例无虚构数字。
- [x] **I-03** 使用现有 proactive/scheduler/消息事件通道；用户授权开关、安静时段、每天上限、跨计划提醒合并、发送幂等和 SSE 同步。
- [x] **I-TEST** Qwen 离线、主动联系关闭、正在番茄钟、重启补发、消息回执延迟、两计划同一触发时间的验收；不重复发、不改计划。

### Batch 6 — J：UI 整合、总回归、发布（已批准并完成）

- [x] **J-01** 渐进式更新 Study UI：计划切换及独立花盆、任务优先级/保底、机动抽屉、学习记忆抽屉、周评/一句话归档、监督设置；Library/Review/Pomodoro 保持次级入口。
- [x] **J-02** 回归 3/7/17/30 天计划、纯机动日、无任务日、双计划、旧 V1、V2、模板下载、资料/答疑、聊天/日记/提醒；处理空态/错误/离线。
- [x] **J-03** 检查迁移恢复、备份、权限、实际本地 Qwen、Windows/WSL 冷启动；确认 staging/发布入口及部署策略后经用户授权发布，记录 commit、运行包、健康检查与回滚路径。

**门禁 RELEASE-GATE**：所有关键测试证据可复核、原用户数据可恢复、用户授权部署、运行版与所记录 SHA 一致；否则不声称发布完成。

## 3. 任务依赖图和最小实施单元

```text
[当前设计冻结 BC-DF-1.0]
             ↓
   [A/BC-0 只读源码审计]
             ↓
   [B-01…B-06 数据契约]
             ↓
   [C-01…C-06 Skill/模板/各入口]
             ↓   ← BC-GATE 用户验收
      ┌──────┴────────┐
   [D 机动与拖延]  [F 学习事件适配]
      └──────┬────────┘
           [E 奖励]
             ↓
        [G 学习记忆]
             ↓
        [H 周评/结束]
             ↓
        [I 主动监督]
             ↓
      [J 总回归/发布]
```

**说明：**J 的 UI 适配可以在各批对应功能验收时渐进实施；J 的最终端到端回归与正式发布依赖所有模块完成。不可为赶进度先实现 UI placeholder 并宣称后端完成。

### 建议 Git 提交切分（必须以真实代码和审批范围调整）

| 建议提交组 | 涉及任务 | Commit message 示例（不是已存在提交） |
|---|---|---|
| 审计/文档（可单独提交） | A | `docs(study): audit current planning contract` |
| 数据契约 | B-01～B-04 | `feat(study): add versioned plan definition` |
| 容量校验 | B-05～B-06 | `feat(study): validate parallel plan capacity` |
| Skill 与生成指南 | C-01～C-04 | `feat(study): align planning skill and markdown exports` |
| 四入口兼容 | C-05～C-06 | `fix(study): unify plan confirmation flow` |
| 恢复与活动归属 | D/F | `feat(study): support flex slots and activity attribution` |
| 奖励 | E | `feat(study): add plan-scoped growth rewards` |
| 学习记忆 | G | `feat(study): add daily study memory projection` |
| 周报与结束 | H | `feat(study): archive final plan outcomes` |
| 主动监督 | I | `feat(study): connect study signals to proactive messages` |
| UI/回归 | J | `test(study): verify growth and multi-plan workflows` |

提交不得代替验收；一个 stage 可以多个小提交，需记录全部 SHA。若修改共享 Gateway 文件，使用精确 hunk staging，避免提交无关脏改动。

## 4. 进度更新协议（**每批必须执行**）

### 4.1 AI 每完成一个任务/提交后，按顺序操作

1. **确认当前真实 HEAD、分支、运行版本、dirty status**；本次若没有本机访问，则明确“未核验”。
2. 更新第 1 节进度总览：阶段状态、阻塞/依赖、证据 SHA、下一动作；不要把“已写文档”“已编代码”和“已运行验证”混为一谈。
3. 在第 2 节中，只有满足该项测试及交付条件才将对应 `- [ ]` 改 `- [x]`；部分完成仍保持 `[ ]`。
4. 在第 4.3 节**新增一行事件日志**（只追加），并在第 4.4 节新增最近一次阶段执行记录（按模板复制填写真实事实），不得删除先前记录。
5. 如需要改变冻结 B/C 设计，先写第 5 节的变更请求，并标记 `BLOCKED` 等用户审批；**绝不先改 `frozen/` 再宣称符合规范**。
6. 检查 `git diff`、staged scope、测试输出；仅在授权时将源码改动与**本主计划更新**一同提交。记录提交 SHA 和是否推送；未提交时写明是本地工作树，不能假称已 GitHub 保存。
7. 更新文档顶部 `最近更新`、`当前阶段`，并告知用户本次已做事项、测试、阻塞、下一阶段、是否需要确认。交接给下一个 AI 时只需传此主计划及同目录 `frozen/`。

### 4.2 阶段结果标记的判定

| 标记 | 最低要求 | 不允许写成 |
|---|---|---|
| `AUDITING` | 已进入只读核对并记录初步证据 | 已开发 |
| `IN_PROGRESS` | 实际开发中、有文件差异且范围受控 | 已通过 |
| `IMPLEMENTED` | 源码/文档已完成目标修改，但未做全部必需测试 | 已验收、已上线 |
| `VERIFIED` | 有真实测试命令/输出、边界用例、用户可观察验收 | 仅静态 parse/单个 happy path |
| `RELEASED` | 已获授权发布，commit/运行 SHA/回归/恢复点可核实 | 仅 `git push` |
| `BLOCKED` | 确切阻塞、证据和待决策项写入台账 | 直接改冻结规范绕开阻塞 |

### 4.3 不可删除的执行事件日志（在下方追加）

| 日期时间与时区 | 任务 ID | 动作（审计/代码/测试/提交/发布） | 真实结果 | 证据路径/命令/commit | 执行者/下步 |
|---|---|---|---|---|---|
| 2026-11-19（文档日期） | PLAN-INIT | 组织 BC-DF-1.0 冻结包和跨模块候选路线，建立统一可更新台账 | 文档整合完成；本机代码未审计；未改 Honey | 本计划；`frozen/`；`archive/` | AI；下一步 A-01 |
| 2026-11-19 22:54（北京时间） | A-01 | 只读审计 | 已定位运行版、源码、前端和备份位置 | `systemctl --user show`；`git worktree list`；`b67daa00`；见 4.4 | Codex；补齐冻结包后继续 A-02～A-05 |

| 2026-11-19（北京时间） | A-02/A-04、C-05部分 | 审计/代码/测试 | 只读核对生产schema；聊天保存收口并阻止生成内容新增完成事实；112 passed | WSL b67daa00 本地5文件改动；见本次记录 | Codex；补齐规范和端到端门禁 |

| 2026-11-19 23:15（北京时间） | B-02～B-04部分、C-05部分 | 正式开发/测试 | V2模型、机动槽、Markdown、事务持久化和预览展示实现 | 后端124 passed；前端8 passed；存储快照追加21 passed；详见记录 | Codex；继续容量与生成链路 |

| 2026-11-19 23:35（北京时间） | BUILD-FIX、B-05 | 代码/测试/构建 | 59条TS错误消除；容量配置、事务校验、预览和profile隔离完成 | 后端138 passed，前端71 passed，tsc与Vite构建通过 | Codex；能力协商及模板/Skill/Builder |

| 2026-11-19 23:54（北京时间） | C-01～C-04、C-05/C-06部分 | 代码/测试/构建 | 版本同源、V1/V2下载导入、选材请求导出及过期预览保护 | 后端146 passed；前端75 passed；tsc与构建通过 | Codex；完整四入口与实际模型验收 |

| 2026-11-20 01:14（北京时间） | D–J、RELEASE-GATE | 代码/验收/本地提交/发布 | A–J完成；214/79通过；正式运行和恢复点可核查 | 3e2598bc、d443b234；DJ_验收报告.md；release-verification.json | Codex；本计划无剩余开发项 |

### 4.4 单次任务执行记录模板（以后**复制新增**，不要覆盖旧记录）

```markdown
#### YYYY-MM-DD HH:MM（TZ）— <任务ID> — <阶段>
- 目标与用户预期：
- 实际运行版 / 源码路径 / Git 分支及起始 SHA（未核验则写明）：
- 事实证据（路径:行号、数据库 schema 或服务输出；脱敏）：
- 发现与原设计的差异：
- 修改文件及理由（或只读，无改动）：
- 迁移/备份/回滚准备：
- 测试命令及真实结果（passed/failed/skipped）：
- Git staged diff 核对、commit SHA、push/PR 状态（无则写未提交）：
- 阶段状态：NOT_STARTED/AUDITING/IN_PROGRESS/BLOCKED/IMPLEMENTED/VERIFIED/RELEASED
- 未解决风险/是否需用户决策：
- 下一动作与下一任务 ID：
```

#### 2026-11-19 22:54（北京时间）— A-01 — 只读审计

- WSL Ubuntu-24.04 的用户服务 `honeyos-gateway.service` 为 active。审计时 PID 6919，ExecStart 为 `/home/zyh20/projects/honey-os/.venv/bin/python -m honeyos.runtime.main gateway run`，工作目录为 `/home/zyh20/.honeyos`。
- 服务 drop-in `20-verified-study-release.conf:2` 与运行进程环境均指向 `/home/zyh20/projects/honeyos-releases/campus-b67daa00`。该发布目录的 `honeyos/companion/react_dist/index.html:8–9` 引用 `index-BV7eUj2L.js` 和 `index-D-tWEM7c.css`。
- WSL 源码根 `/home/zyh20/projects/honey-os`，分支 `feature/chat-message-batching`，HEAD `b67daa0066e58020114e951ba0b298a7b136b995`。`git --no-optional-locks status --short` 无输出。Windows `HoneyOS-development` 为 `feature/honeyos-integration`、`408e8a9`，有 28 条状态记录。
- 发现现存 release-backups 目录。与当前发布同名的 `campus-campus-b67daa00` 仅列出 `gateway-original.conf`，这次未核验数据库备份或恢复能力。
- 初步定位 `honeyos/study/service.py:44`、`repository.py:20`、`validation.py:14`、`markdown.py:57` 及 `honeyos/companion/companion_skills/study-planning/SKILL.md:17`。V1 行为与各入口完整链路仍待后续验收。
- 仅执行 systemctl、进程发布路径、Git 和文件只读检查。只更新本台账，未运行功能测试、修改源码或数据库、提交、推送或部署。
- A-01 已完成，A-GATE 待审计。主计划同目录缺少 `frozen/`，在补齐 01、02、03、08 和 V1 黄金样本后继续 A-02～A-05。

### 4.5 每次执行结束时发给用户的摘要格式

```text
本次范围：<任务 ID / 预期目标>
完成：<真实已实现/已验证>
测试：<命令+结果；未运行写明>
源码与分支：<路径/HEAD；若无法访问写明>
提交：<SHA/是否 push；未提交写明>
阻塞：<具体问题或无>
下一步：<任务 ID、所需用户决策>
计划已更新：00_MASTER_持续更新开发计划.md
```

## 5. 冻结规范冲突 / 变更控制（必须审批）

如果真实源码发现 `BC-DF-1.0` 无法直接实现，建立一条 `RFC-BC-<序号>`，**先记录后实施**：

```markdown
### RFC-BC-001 — <标题> — 状态：PROPOSED / APPROVED / REJECTED
- 发现日期、任务 ID、实际源码证据与用户可观察影响：
- 与 `frozen/01~03` 哪一条冲突：
- 方案 A（最小变更）及风险：
- 方案 B（必要时，最多两个方案）及风险：
- 对 V1/运行数据库/Skill/导出模板/其它计划的影响：
- 必须新增的回归测试：
- 用户明确决定与日期（未批准不能实施冲突变更）：
- 修改冻结文档版本号和引用的计划：
```

**当前待批准 RFC：无。** 发现非冻结小错误也要记录修正依据；用户目标永远高于伪代码，但不能忽视实际系统稳定性和数据安全。

## 6. 决策清单（不要因 AI 没问就擅自定为事实）

| 决策 ID | 问题 | 当前状态 | 推荐默认（**仅建议**） | 影响模块 |
|---|---|---|---|---|
| DEC-01 | 阳光点算法和旧奖励数值 | `APPROVED_AND_VERIFIED` | 沿用旧分值但服务端防刷、按 plan 配置 | E |
| DEC-02 | 小花盆成长推动因素 | `APPROVED_AND_VERIFIED` | 有效标准学习日/里程碑，保底不倒退 | E |
| DEC-03 | 两份活跃计划周评储存/汇总方式 | `APPROVED_AND_VERIFIED` | 各自周报、综合只读视图 | H |
| DEC-04 | 每日快照时区与时间 | `APPROVED_AND_VERIFIED` | 用户当地时区 23:00，避开现有日记时段 | G |
| DEC-05 | 主动学习监督授权与频次 | `APPROVED_AND_VERIFIED` | 首次明确 opt-in，每日状态提醒最多一次 | I |
| DEC-06 | 可用时间属于硬上限还是软偏好 | `APPROVED_AND_VERIFIED` | 有证据的硬约束阻断，软约束需确认警告 | B/C |
| DEC-07 | 支持的计划 schema 版本 | `APPROVED_AND_VERIFIED` | V2 尚未实测前仅宣称 V1 | B/C |

决策记录（2026-11-20）：用户已明确选择推荐值，E/H/I数值和频次依此实施。已决定的 B/C 字段语义以 `frozen/01~03` 为准，无需重复询问。

## 7. Git 与文件交付约定

- **本地候选 repo**：`~/projects/honey-os`，但用户有过多个工作目录/运行发布目录，必须通过审计确认。`~/.honeyos` 是候选数据根，不能据此直接备份/写入。
- **用户历史文件传输目录**：Windows `D:\HoneyOS-Transfer` ↔ WSL `/mnt/d/HoneyOS-Transfer`；这是用户下载后自行放置的约定目录，不是对工具访问用户电脑的授权。
- **建议放入已核对 repo 的 `docs/study-system/growth/`**，如现有目录另有规范则以实际审计为准。保留本包文件相对目录结构，Markdown 内部链接才能正确解析。
- **严禁范围**：不在任务授权范围内删除用户文件、重置脏工作区、擅自操作/推送远端分支、重启生产网关或自动升级用户数据库。

建议但需在真实 repo 中校验的 Git 流程：

```bash
# 先只读，记录实际情况
 git status --short
 git diff --stat
 git branch --show-current

# 只暂存本阶段已核实、与任务相关的路径或单个 hunk
 git add -p -- <verified-path>          # 示例：路径须实地确认
 git add -- <verified-plan-file>         # 进度台账与相关规范链接

# 每个 commit 前检查：绝不使用 git add .
 git diff --cached --stat
 git diff --cached --name-status
 git diff --cached

# 仅在已经授权提交的情况下，用真实任务号写信息
 git commit -m "docs(study): update execution plan for A-01"
```

**不要把上面的命令作为未经审计可整段执行的脚本。** push、PR、部署都不是默认授权；如用户未要求提交远端，只在交付中写明待提交。

## 8. 下一个 AI 接手时的最短提示词（当前）

```text
HoneyOS Study Growth本计划A–J已完成。用户要求缺冻结包不阻断，并明确授权D–J及推荐参数。
先核验主计划最新事件记录、实际Git HEAD、生产PYTHONPATH与dirty状态，再处理用户新的请求。
当前功能源码d443b234，运行包study-growth-d443b234，B/C提交3e2598bc；最终文档提交可能更新HEAD而不改变功能源码。
主计划为E:\ChatGPT工作区\00_MASTER_持续更新开发计划.md；repo docs内为同步快照。
测试214后端/79前端；保留用户计划和学习事实，不回填奖励；成长和监督必须显式开启。
本轮无远端push。新任务不要重做已完成开发，不要依历史日志中的旧阻塞停在只读。
```

---

## 9. 历史交接摘要（2026-11-19，已由最新执行记录更新）

- **成果：**统一了此前 13 份 B/C 冻结包文件与跨模块历史路线图，形成一份持续维护的主计划；冻结文档原样保留、旧路线归档，减少对多份重复方案同时维护的需要。
- **没有做：**未访问或修改用户本机 HoneyOS 工作区/数据库，未运行实际 Study parser 或 Gateway，未提交 GitHub 或发布；不存在本轮新增的源码/测试 SHA。
- **立即可做：**用户授权执行 A-01 后，接手 AI 按第 2 节从只读审计开始并在每次结束后更新本文件。
- **用户可以怎样看进度：**打开本文件的第 1 节查看总表、第 2 节看任务勾选、第 4.3 节看历史、第 6 节看待决策问题。无需逐个打开专项文档。

#### 2026-11-19 — A-02～A-05 — 源码核对与基线测试（部分完成）

- 当前源码仍为 WSL /home/zyh20/projects/honey-os，HEAD b67daa0066e58020114e951ba0b298a7b136b995，开始时工作树干净。
- models.py 的 StudyPlan 仅允许 schema_version=1。StudyTask 无 priority、minimum_required、kind；StudyPlan 无 flex_slots。validation.py:14 重新验证对象，模型 extra=forbid。
- markdown.py:57 仅支持 V1；任务未知 metadata 拒绝，但顶层 front matter 按白名单取值，因此未知顶层键被忽略；勾选任务被解析为 completed。该行为需在 B 阶段明确兼容策略，不能当作 V2 安全能力。
- service.py:83/93 实现预览和导入，强制 markdown_import 来源并拒绝已有 ID。planning.py:37 提供 V1 模板，:66 加载实际 Skill；:85 修改保留完成任务和未提及任务，:114 用 updated_at 并发检查。聊天保存直接调用 repository.save_plan/save_new_plan，尚未统一收口到 StudyService。旧任务可以通过生成内容转为 completed，需后续按真实事件约束修订。
- session_store.py:124 通过任务表 plan_id 查询番茄钟，复用 scheduler_job_id 和 expected_end_at。review.py 已有题目、答题、卡片、回忆和测验表及 daily_summary；本次检索未发现 plan_id，计划归属仍需追踪完整调用链。
- 在 Study 后端与 Study 前端范围搜索 capacity、flex_slots、minimum_required、planning_request、supported_schema_version、sunlight，无匹配。该结果限于本次搜索范围。
- 运行既有 test_models.py、test_markdown.py、test_validation.py、test_planning.py、test_phase5_3_markdown_import.py，命令使用 PYTHONDONTWRITEBYTECODE=1 和 pytest -q -p no:cacheprovider。结果 24 passed in 8.89s。
- 尚未完成运行库只读 schema、恢复演练、主动联系/记忆完整边界和四入口端到端验证，A-02～A-05 保持未勾选。冻结包缺失仍影响规范逐条对照，但不阻断独立源码审计。未修改源码，未提交或部署。
- 下一步继续运行库 schema、Review 归属、scheduler/proactive/学习记忆边界审计，形成 A-GATE 证据。
#### 2026-11-19 — B-01 部分实施 — V1 未知字段校验

- 用户要求继续开发。本次提前实施主计划已明确的局部校验修复；A-GATE 尚未完成，B-01 保持未勾选，B/C 整体未验收。
- 修改 WSL /home/zyh20/projects/honey-os/honeyos/study/markdown.py，显式拒绝未知 YAML 顶层字段，防止奖励、V2 或拼错字段被静默丢弃。合法 V1 字段保持可用。
- 修改 tests/honeyos/study/test_markdown.py，覆盖 minimum_required、sunlight、unexpected 顶层字段拒绝。
- 运行 pytest -q -p no:cacheprovider test_markdown.py、test_planning.py、test_phase5_3_markdown_import.py（完整路径位于 tests/honeyos/study/），20 passed in 8.80s。git diff --stat 为两文件新增21行。
- 额外审计确认 review.py 的题目、答题、卡片、回忆和测验表没有 plan_id；daily_summary 混合非归档计划任务及全局练习，不能直接用于每计划独立奖励或记忆。
- 本地未提交、未部署。兼容影响：曾被忽略的未知 YAML 顶层字段现在报错。冻结包仍缺，V2 具体格式实现待规范依据补齐。
#### 2026-11-19 — A-02/A-04、C-05 部分 — 服务收口与真实完成状态

- 修改 honeyos/study/service.py，增加 save_chat_plan，承接重新验证、updated_at 并发校验、仓储保存和提醒同步。planning.py 保留原 save_chat_plan 调用入口，委托 StudyService，已有调用者保持兼容。
- planning.py 的生成新计划将任务统一归为 planned；生成修改保留旧任务原状态，新任务不接受 completed。已有完成任务仍保留，未提及任务继续保留。V1 文件导入原有 status/review/source_type 语义未改动。
- 新增 tests/honeyos/study/test_planning.py 两项回归，覆盖新建伪造完成及修改旧任务的完成事实保护。连同上一批 markdown 修复，工作树共5文件变更，无提交或部署。
- 重点回归36 passed in 9.21s；完整命令 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/honeyos/study，112 passed in 27.53s。git diff --check 通过。
- 生产 /home/zyh20/.honeyos/study/study.db 使用 sqlite3 mode=ro 仅读 sqlite_master 和 PRAGMA table_info。确认 study_tasks 有 plan_id，study_sessions 以 task_id 关联；review attempts/cards/recalls/quizzes 无 plan_id，生产结构与源码相符，未查询用户学习正文。
- api_server.py:5886/5907 在 study_planning 模式排除普通 memory 工具并设置 skip_memory。该证据只证明计划生成边界，日记/主动监督完整边界仍待验收。
- 本批为明确需求的局部修复，先于完整 A-GATE 实施。B/C 仍 IN_PROGRESS，checkbox保持未完成，不能标记整体 VERIFIED。仍缺 BC-DF-1.0 原始规范，V2及四入口端到端、恢复能力尚未验收。
#### 2026-11-19 23:15（北京时间）— B/C 正式开发 — V2 契约与可见预览

- 用户已明确取消冻结包前置要求，当前正式依据为实际源码和主计划语义。先前日志中的“冻结包阻断”结论被本次决定覆盖。
- WSL 源码 /home/zyh20/projects/honey-os，起始 HEAD b67daa0066e58020114e951ba0b298a7b136b995。包含前几批未提交改动，继续使用同一工作树，未覆盖无关文件。
- models.py 新增 V2 priority=must|standard|optional、minimum_required（仅must允许）、kind=study|review|quiz|flashcard。独立 StudyFlexSlot 含 id、scheduled_date、planned_minutes，验证日期范围、正时长、重复ID。V1默认值兼容，携带实际V2语义降为V1会明确拒绝。
- 本次确定的交换格式：V2沿用 YAML+Goals+Schedule；任务缩进 metadata增加 priority、minimum_required、kind；独立机动槽放 YAML顶层 flex_slots 列表，每项含 id（可省略自动生成）、scheduled_date、planned_minutes。Markdown导入导出与重新解析语义无损。正式模板下载和生成Skill尚沿用现有V1能力，后续随生成链路一起更新。
- repository.py 新增 canonical study_plan_definitions 表，单独存V2定义，不复制任务完成/专注事实。与计划任务写入同一事务，读取采用同一读事务快照，避免并发混合版本。旧行无定义时使用默认属性，不改写旧学习记录。
- service.py 接受V2新建及任务属性更新。V2文件预览/导入规范化为draft/planned，避免外部声明完成；V1原有状态导入保持兼容。聊天修改传递V2属性和机动槽，并拒绝降级丢失信息。
- 前端 study.ts 同步类型，StudyPage 和聊天确认卡展示优先级/保底/任务类型及独立机动时间。机动容量不计为待完成任务。未实现机动消耗或奖励逻辑。
- 新增 test_v2_contract.py 覆盖V2往返、持久化、非法优先级/任务类型/机动日期时长/未知字段、V1降级拒绝、服务预览导入及编辑、外部完成状态保护。隔离旧库升级与SQLite backup恢复实验保留完成任务和session，未操作生产数据库迁移。
- 完整后端 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/honeyos/study：124 passed in 28.25s。新增读快照后运行 test_v2_contract.py 和 test_repository.py：21 passed in 0.72s。前端StudyPage.test.tsx：8 passed，覆盖V2实际日视图。
- 前端全局tsc有59条既有诊断，集中在ChatPage/SettingsPage等既有源码。临时切回HEAD原study.ts检查后恢复，诊断完全一致；加入展示后仍为59条，修改组件无新增诊断。全局前端构建尚不通过，后续发布需处理此实际问题。
- git diff --check通过。代码未提交、未推送、未部署。B/C模块仍IN_PROGRESS，未完成多计划容量、版本能力协商、完整生成入口和端到端确认验收。
- 下一步：开发B-05容量快照和校验，并使模板、Skill及Builder读取实际能力；继续根据真实代码推进，不再等待冻结包。
#### 2026-11-19 23:35（北京时间）— BUILD-FIX、B-05 — 前端构建修复及多计划容量

- 源码仍为WSL /home/zyh20/projects/honey-os，分支feature/chat-message-batching，HEAD b67daa0066e58020114e951ba0b298a7b136b995，继续在前几批未提交工作树上开发。
- ChatPage.tsx 清除重复模型选择hooks和处理器，保留支持session.modelProvider的较新逻辑；修复发送时未定义combinedText变量。根据历史f4fc3193已迁移到本机文档引用的事实，清除失效上传UI和未定义类型/API，图片附件继续可用，资料使用现有「引用本机文档」入口。
- SettingsPage.tsx 清除第二份模型配置hooks和处理器，保留条件return之前的唯一状态，避免hooks顺序错误。原59条TypeScript诊断已消除。
- repository.py 新增canonical study_daily_capacity表，用户可按日期配置0～1440整数分钟或清除；不接受外部Markdown配置个人容量。没有可信上限时返回verified=false、limit_minutes=null，展示未核实。
- B-05容量快照汇总候选计划任务分钟+独立机动分钟，以及其他active计划的任务+机动。修改A时排除数据库旧A，使用候选A替换，避免重复计量。暂停/结束/归档的其他计划不占用active容量。
- 保存事务BEGIN IMMEDIATE内重新检查容量，覆盖手动新建、任务修改、Markdown导入和聊天确认。配置上限后新增超额负载被拒绝并回滚；下调上限后允许已有计划记录完成或减少负载、暂停/归档，避免用户无法修复超载。重新激活计划会重新检查。新建草案也会检查候选总量。
- service.py提供plan_capacity/set_daily_capacity；planning_http.py新增受现有认证保护的GET /api/study/capacity、PUT /api/study/capacity/{local_date}；聊天和Markdown预览响应均附容量快照。共享api_server.py仅改动Markdown预览的小段，已审查diff。
- StudyCapacityPanel展示本计划/其他计划/合计/上限和超限提示，在学习日视图显式设置当天「每日学习上限」。CapacitySummary同时用于文件导入和聊天预览；确认保存重新校验最新配置和其他活跃计划，预览不产生计划写入。
- 修复默认StudyRepository使用现有get_honeyos_home()单一数据根，尊重profile context override与HONEYOS_HOME，显式home调用保持兼容。隔离测试证明两个profile容量和计划互不可见。
- 新增14项容量后端回归，包含并发双保存防超订、候选替换、机动分钟、未知/零/非法上限、过期预览、回滚及profile隔离。真实aiohttp客户端验证401、配置上限、超额preview提示、import返回400且无新增计划、清除上限后import返回201。
- 新增前端容量交互测试，验证未核实提示、设置上限和非整数拒绝。
- 最终完整后端命令PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/honeyos/study：138 passed in 29.31s。前端vitest run：19 files / 71 tests passed。WSL Node v22.23.2执行tsc -b --pretty false --force通过，Vite build通过，输出到/tmp/honeyos-study-v2-build，JS index-BcdyQgt-.js / CSS index-DwP7KxaQ.css。存在大于500kB分包提示，构建成功。
- git diff --check通过，无commit/push/部署。生产仍使用原发布包，未对生产库实施新schema升级。
- 本批实现选择：显式命名「每日学习上限」的用户配置作为硬约束；无配置时不推测容量。已有超载负载允许等量状态记录和减量修复。B-05已满足本批源码和测试验收，B/C整体仍IN_PROGRESS。
- 下一步继续C-02～C-04能力协商、模板、Skill、Planning Request Builder同步，随后补齐完整四入口验收。
#### 2026-11-19 23:54（北京时间）— C 计划生产端 — 能力、模板、Skill与外部请求

- 开发树仍为WSL /home/zyh20/projects/honey-os，HEAD b67daa0066e58020114e951ba0b298a7b136b995；沿用此前本地改动，无commit/push/部署。
- models.py定义单一SUPPORTED_STUDY_PLAN_VERSIONS与CURRENT_STUDY_PLAN_VERSION，模型、codec、模板、编写指南、Skill运行注入及Builder同源读取。新增认证GET /api/study/planning/capabilities，返回本进程真实代码能力。当前开发进程为V2，旧发布包尚未替换。
- template_markdown默认V2；GET /api/study/plans/template?version=1保留V1，未知版本400。模板通过canonical exporter的include_ids=False生成，直接以---开始，去除计划、任务与机动槽ID，不混提示词或代码围栏。真实HTTP下载→preview→import的V1/V2两条链均通过。C-03本批完成。
- 增量修改现有Honey study-planning Skill，沿用原问卷、公开搜索、资料引用、预览确认和提醒规则，改为使用本轮注入的真实版本及字段指南，补充must保底、任务类型、独立flex_slots和事实/权限边界。planning_instructions同时注入未来30天实际容量，带范围与UTC captured_at；超出范围提示重新核实。调整现有唯一活跃计划时排除旧计划占用。
- 新增共享authoring_guide与认证下载GET /api/study/planning/guide，说明study_plan.md与planning_notes.md分别输出、纯文件语法、合法字段、未知容量、保留历史及确认流程。
- 新增PlanningRequest严格输入与认证POST /api/study/planning/request，只包含用户填写的目标/约束、明确选择的资料和实际容量快照；支持按可信plan_id导出调整请求和原计划。资料限8份、每份正文最多2000字，标记truncated/content_available；输出不带资料本机路径或未选资料内容。快照列出有占用/已配置上限的日期，其他日期显式标为上限未核实，不展开无限日期列表。
- 前端计划管理新增「交给其他AI制定计划」，按需读取能力和资料列表，用户填目标/日期/限制，勾选资料后先预览，再手动下载planning_request.md。表单修改清除旧结果，生成中禁止编辑，输出包含片段的事实在UI明确提示。请求仅生成本地文档，不创建计划。C-04本批完成。
- 额外修复确认边界：聊天草案正文/revision变化会清除预览，旧异步响应不能恢复旧确认；文件选择先捕获input并清空，再await读取，避免React currentTarget失效；sequence守卫防止旧文件读取/预览覆盖新文件，错误可重选重试。
- 新增test_planning_exports.py验证能力同源、真实V1/V2模板下载导入、请求误导入拒绝、真实隔离资料最小选材/截断、原计划替换容量和无计划写入。新增Builder交互测试、2项聊天过期预览测试，以及文件迟到预览回归。原聊天历史测试改为按task_id定位被移动任务，避免多任务排序改变后的索引假设。
- 后端完整命令PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/honeyos/study：146 passed in 29.62s。前端最终vitest run：21 files / 75 tests passed。tsc -b --pretty false --force通过。Vite build通过，隔离输出/tmp/honeyos-study-v2-build，JS index-C_rQ4WKa.js，CSS index-DwP7KxaQ.css，保留既有大分包提示。
- git diff --check通过。实际主模型/Qwen对话生成质量、所有四入口的完整确认/diff语义及发布环境验收尚待完成，B/C整体仍IN_PROGRESS；没有因模板生成或构建通过而标记整体VERIFIED/RELEASED。
- 下一动作：补齐手动编辑、MD导入、Honey新建和聊天调整的确认一致性及真实模型验收，形成可复查B/C验收报告，再推进日完成等级和机动消耗。

#### 2026-11-20 00:05（北京时间）— B/C验收提交准备与D–J授权

- 用户明确要求完成验收提交，并选择继续完成D–J，待定参数采用计划推荐值。后续无需再次请求同一开发授权。
- 已补齐手动编辑预览→确认→StudyService→容量及版本CAS；取消无写入、过期确认拒绝。旧直接更新入口保持兼容。
- 完整Study后端147 passed in 29.47s；全部前端77 passed；tsc和Vite构建通过。本地Qwen真实调用返回结构化短评。
- B/C在隔离开发环境验收完成，生产部署和真实用户对话体验仍在J阶段。即将精确暂存本轮文件并提交。
- D盘历史honeyos_study_mvp_7day.zip已只读核实每日10/20/30阳光、阶段60/120、成长1/3/5/7标准日阈值。采用用户授权的推荐策略，主动监督仍通过显式开关启用。

#### 2026-11-20 01:10（北京时间）— D–J — 功能验收完成、发布准备

- 授权：继续完成D–J，待定参数采用推荐值。当前基线714986ef，保留并行完成的校园成绩功能；B/C提交3e2598bc。
- 已实现D/F/E保底、机动事务消耗撤销、恢复提案、真实练习/番茄钟单归属、独立奖励冲正；G/H日记忆、迟到补跑、周报、只读综合和结束事务归档；I复用主动通道、模型严格校验、每日一次与消息落库幂等；J前端整合。
- 最终后端214 passed in 43.68s，前端79 passed，tsc和Vite构建通过；实际本地Qwen三种合成事实输入通过，不发送真实消息。隔离副本经Windows Edge冷页面加载，显示成长、学习记忆、机动和关闭的监督设置；点击记忆后返回真实0/0空日，无错误。
- SQLite备份及恢复升级通过，备份 /home/zyh20/.honeyos/release-backups/study-growth-20261120-010153。原2计划、78任务、0专注/答题/回忆记录完整保留。
- 默认每日10/20/30、阶段60/120、植物标准日1/3/5/7来自D盘旧实现；新增真实练习每次1、每完整25分钟专注5为本次适配默认，非旧版原值。时区Asia/Shanghai，日投影23:00及迟到重算，监督18点后、22–08安静、每日最多一次，必须单独opt-in。
- 不回填历史奖励。结束只清本计划周报正文，保留原始事件与日快照。迁移和发布复验仍待最终记录，J-03暂不勾选。
- 完整证据见DJ_验收报告.md。本轮本地精确提交，不推送远端。

#### 2026-11-20 01:14（北京时间）— J-03 / RELEASE-GATE — RELEASED

- D–J源码提交d443b234df9a5238352574741254dd0c7257f53c，31个精确暂存文件；git diff --cached --check通过。提交前后无无关工作树修改，未push。保留714986ef的校园成绩合并。
- 从git archive制作不可变候选`/home/zyh20/projects/honeyos-releases/study-growth-d443b234`，替换候选内前端并记录SHA256 manifest；冷启动隔离副本的V2能力、所有新接口及页面200。
- 正式切换前再次SQLite backup，文件pre-switch-study.db与pre-switch-state.db保存在既有备份目录；确认无运行或暂停专注，仅替换既有drop-in的PYTHONPATH，校园浏览器及项目配置保留。
- 正式服务active，PID16057，进程环境指向上述包；`/health`、`/study`、`/api/study/planning/capabilities`、`/api/study/growth/supervision`、`/api/study/plans`、`/diary`、`/settings`及`/`均200；JS index-ypv7hVJj.js与CSS index-CcE5e64u.css资源200。Windows独立HTTP复验health/study均200且新JS存在。
- 生产原2计划/78任务/0专注/0答题/0回忆计数完全一致，integrity_check=ok、foreign_key_check为空；成长启用计划0，监督enabled=false，没有自动替用户开启。新学习模块未见启动错误。
- 恢复点：`/home/zyh20/.honeyos/release-backups/study-growth-20261120-010153`，包括原gateway-release.conf、SQLite备份、恢复演练manifest及release-verification.json。需回滚代码时恢复原drop-in并重启；恢复数据库前先保留发布后的新增数据。
- 隔离验收服务已停止，正式服务保留。发布完成，所有任务已勾选。后续无需重复索要本轮授权，无剩余本计划开发工作。

#### 2026-11-20 09:08（北京时间）— 后续修正：下载入口与外部AI格式说明

- 用户反馈V2页面仍有V1模板、指南、请求与当前计划多处下载，外部AI照模板仍生成错误格式。
- 移除V1与独立指南下载链接，只保留“新计划模板（V2，内附AI格式规则）”和“当前计划（含ID与状态）”。规划请求改为预览+复制，不再下载另一份易混文件。
- 模板和当前计划在YAML内附完整注释规则，保持同一文件可解析；明确新建/调整、source_type等枚举、完整字段白名单、八行任务格式、日期顺序、整数分钟、ID/事实保留、机动容量与单独notes。合法旧V1导入能力保留，UI不再提供旧模板入口。
- 新模板修正source_type为markdown_import，机动40分钟可覆盖示例任务；请求显式标注起止日期和new/revise模式。
- 后端35项格式/导出/规划回归通过，前端11项页面与复制交互通过，tsc及Vite构建通过。准备以本地提交的独立包更新正式页面，发布证据随后追加。

#### 2026-11-20 09:17（北京时间）— 下载入口修正发布复验 — RELEASED

- 功能提交6808ea212f3a8e9465a71f20660e440f1bdf6924；独立运行包`/home/zyh20/projects/honeyos-releases/study-downloads-6808ea21`，服务active。前端JS index-BlMZG8X0.js，CSS index-CcE5e64u.css。
- Windows Edge刷新实际页面后确认只有“新计划模板（V2，内附AI格式规则）”及“当前计划（含ID与状态）”两个下载口，附新建/调整用途说明。
- 正式HTTP下载模板并通过真实V2解析，文件内含完整规则；当前2个计划下载后ID、任务ID与完成状态逐项一致，发布前后原始计数不变。未创建、导入、删除或修改用户计划。
- 恢复点`/home/zyh20/.honeyos/release-backups/study-downloads-20261120-090925`包含旧发布配置、学习库backup、发布前计数及release-verification.json。无需恢复数据即可切回旧代码；不盲目覆盖新增事实。
- 后端35项、前端11项相关回归通过，tsc及Vite构建通过。保持V1历史导入兼容但移除旧模板UI入口；未push。

#### 2026-11-20 11:56（北京时间）— 刷新持久化与学习花园 — 功能验收

- 用户要求刷新后保留导入计划、确认提醒与记忆联动部署、网页查看学习记忆，并新增随计划生长、完成后留存、可查看周月年总结的花园。
- 问题根因是页面selectedPlanId只在内存且加载空数组会重置，实际导入数据未丢失。改为按profile持久记住选择，加载过程中不清除；计划已删除时安全回退。恢复日期在计划范围内默认今天。
- Study与记忆页均新增学习花园入口，植物实时投影原有任务/专注/练习/闪卡/奖励数据，开启页面每30秒刷新，任务操作后立即失效重读；完成归档同事务保留纪念植物与每日统计，周/月/自然年日历汇总不恢复已清理周报正文。完成后的植物与统计在原计划删除后仍保留，不为旧事实补发奖励。
- 提醒与学习聊天上下文原已在d443b234提交并部署：复用existing poller、StudyLearningMemory/StudyGrowth事实与现有消息/SSE通道，主动监督仍显式授权，默认不代开。
- 整体后端220项通过（含5项花园），最终再补第6项迟到投影覆盖保护测试；前端全套84项通过，tsc与Vite构建通过。覆盖慢加载刷新、已删除选择回退、profile隔离、空期/闰年/跨年、关闭失败回滚与删除后留存。
- 其他会话校园源码及react_dist存在未提交改动，保留原样；共享api_server.py的33行修改未纳入本次提交。下一步从精确源码提交制作独立包、隔离UI验收、备份及正式复验。
