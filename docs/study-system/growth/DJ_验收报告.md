# D–J 验收报告

2026-11-20。按用户要求完成D–J及推荐参数，实现基于714986ef并保留校园成绩功能。B/C已提交3e2598bc。本文记录本轮验收证据，主进度以用户00_MASTER台账为准。

## 实现与边界

| 范围 | 可观察行为与证据 |
|---|---|
| D | full/standard/minimum/incomplete/no_tasks，今日保底显式开启；机动预览、确认、幂等、版本CAS及撤销同事务；延期恢复最多3项且待确认 |
| E | 每计划独立可追溯阳光流水，唯一来源、冲正、启用基线防历史补发；成长高水位不处罚性退化 |
| F | 复用服务器专注、答题、复述事实；单事件单归属、可改未分配；教材衍生题清理前保留最小真实事件，联合视图去重 |
| G | 同canonical库独立投影表，plan/date/version日快照及来源；23点、dirty修订、重启补跑和DST守恒；学习话题才提供限额上下文 |
| H | 每计划周报、上周对比、跨计划只读汇总；结束预览绑定计划版本及事实hash，最终一句话和结构化统计先写，再同事务清本计划周报 |
| I | 既有poller/adapter/消息库/SSE；默认关闭，静音、工作状态、正在专注屏蔽；Qwen严格JSON及80字限制、静态回退、发送键幂等 |
| J | StudyGrowthPanel替代占位成长展示，保底/机动/日记忆/周评/奖励明细/归属/结束/监督设置；V1显式预览升级，V2新建能力协商 |

## 实际验证

- 后端命令：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/honeyos/study tests/honeyos/test_web_initiative.py tests/honeyos/test_companion_profile_store.py tests/honeyos/test_proactive_initiative_runtime.py`，**214 passed in 43.68s**。
- 前端Node v22.23.2，`node node_modules/vitest/vitest.mjs run`，**79 passed**；`node node_modules/typescript/bin/tsc -b --pretty false --force`通过；Vite build通过，输出`/tmp/honeyos-study-growth-build`，JS `index-ypv7hVJj.js`，CSS `index-CcE5e64u.css`。保留构建的大分包提示。
- 覆盖双计划、3/7/17/30天、空日/纯机动、V1/V2、容量并发、关闭失败回滚/重试、迟到数据、DST专注守恒、历史事实不补发奖励、共享复习来源清理及消息并发重试。真实HTTP覆盖401、启用、机动预览不写/确认/重试/撤销、记忆、周报、结束A不影响B。
- Qwen本机三次真实合成案例调用返回合法JSON，完成数/专注数由后端提供；25类伪造数字回归拒绝并回退。未向真实会话发送验收消息。
- Windows Edge使用`http://127.0.0.1:18642/study`加载新构建与备份恢复副本。副本仅有无效占位模型配置，未复制真实凭据。展开成长抽屉、读取每日记忆返回0/0/0空日；监督复选框未选中、18点、22至8点及每日最多一次正确显示。
- 本轮未宣称整个HoneyOS所有模块全量回归，聊天/日记/校园等共享通道保留原有功能，相关主动联系测试及前端总测试通过。

## 采用参数

每日保底/标准/全部完成10/20/30；3标准日阶段60，5标准日且第7日达标阶段120；植物1/3/5/7标准日；有效练习或复述每次1、完整25分钟专注5。后两项为本次适配默认，其余旧值核实自D盘MVP。单计划成长需启用，历史不补发。监督需另行明确开启，Asia/Shanghai、18点后、22–08安静、跨计划合并每日最多一次。

## 恢复与发布

- 备份`/home/zyh20/.honeyos/release-backups/study-growth-20261120-010153`，study/state使用SQLite backup并校验完整性；恢复副本实施新schema后foreign_key_check为空，所有原始计数一致。
- 原运行包`/home/zyh20/projects/honeyos-releases/campus-714986ef`，服务发布drop-in备份在上述目录`gateway-release.conf`。
- 发布流程：本地提交→独立git archive包+已验收前端→复核共享运行版本→仅切换既有PYTHONPATH drop-in→重启→HTTP及数据计数复验。失败切回原代码，数据恢复须先备份发布后的新增事实，不盲目覆盖。
- 发布后补充实际源码SHA、运行包、健康检查与计数。未push、未合并远端PR。
