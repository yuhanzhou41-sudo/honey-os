# HoneyOS 2026-11-19 集成发布

正式版本为 `720b01b`。独立发布目录为 `/home/zyh20/projects/honeyos-releases/study-skill-720b01b.ctzB7P`。E 盘 `HoneyOS-development` 的 `feature/honeyos-integration` 保存 Study 与工作模式的合并历史；旧 WSL 开发树和其他工作目录的未提交改动保留原位。

## 已上线

- **设置 → 复习笔记 Skill**。工作模式可提交 `name`、`purpose`、`heading` 三字段候选。提交使用现有一次性审批，服务内固定格式器先以合成样本运行无网络验证，然后登记为待审核。设置页显示来源任务、版本、摘要和检查项目。用户另行确认启用，可停用或切回旧版。手动输入的复习内容经本机处理，结果返回浏览器。
- **设置 → 主动联系**。显示工作模式暂停状态、最近评估时间及从该版本开始的最近 20 条成功发送时间。记录只保存时间，不复制消息正文。
- **学习工具 → 校园**。纳入此前已提交的校园门户地址、过期票据清理、工作模式与权限只读面板。资料库存储入口和设置中的读取记录沿用现有页面。

发布验证覆盖前端构建、Study/工作模式/Skill/事件与主动联系后端回归、授权与未授权接口响应、WSL 健康检查和脚本 SHA-256、Windows 设置页和静态资源。另有 101 项模型路由、提醒与日记隔离回归通过。未提交真实候选到生产配置。

从聊天进入工作模式后，可以说「请提交一个把我手动输入的内容整理为复习笔记的 Study Skill，标题用『今日复习』」。同意提交后，在设置页刷新候选，查看测试并单独确认启用。

## 回滚

将 `/home/zyh20/.honeyos/release-backups/study-skill.abdngz/gateway-original.conf` 还原到 `~/.config/systemd/user/honeyos-gateway.service.d/20-verified-study-release.conf`，执行 `systemctl --user daemon-reload` 与 `systemctl --user restart honeyos-gateway.service`。旧版本快照为 `study-textbook-faa7ea9`，发布标识 `5cb527c`。新功能使用独立的 Skill 数据库，并在既有主动联系数据库内增加消息时间表。

## 验收边界和后续

- H3 的首批功能限于固定复习笔记格式器。通用脚本候选测试、能力目录与缺口观察、Feature 补丁交付和未决澄清任务的恢复仍待完成。复习笔记候选需要用真实聊天交互验收工作模式发起审批的表现。
- H2.2 的同会话按键语音、H4 的 Edge 选区分享及教务考试/校历待开发。教材设备健壮性和重复提问零采集仍待验收。
- H5 与 Life Context v1 共享手机数据来源。分别跟踪移动伴侣的手动分享与独立 Life Context 的授权采集。LC-0 已完成桌面初审。本机尚未识别到 P60 Pro。B 站和浏览器真实内容级样本、依赖和许可证的固定提交复核，以及手机和电脑的离线传输测试仍待执行。
- H6–H8 的桌宠、创作、生活服务与虚拟社交仍处于路线图。原陪伴路线继续使用现有人格、记忆和反馈实现；旧 DeepSeek 审核卡保持历史归档。
