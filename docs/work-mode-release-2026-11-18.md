# HoneyOS 工作模式首版验收

正式 Gateway 运行 3acf870，发布目录为 /home/zyh20/projects/honeyos-releases/work-mode-3acf8700。聊天页提供开始和结束工作按钮。进入工作后，Honey 可用待办、网页澄清和候选工作区工具。候选文本文件写入与 Python 测试分别匹配各自的一次性审批卡。

工作期间暂停新主动联系、聊天状态评估和该工作会话的后台记忆整理，定时日记延后。结束时依据工作总结排队一次状态评估。隔离 HTTP 验收使用模拟回复提供方，走通提问、用户回答、一次性审批、生成候选 SKILL.md 和结束后的单次评估。

开发副本位于 E 盘的 HoneyOS-h1-isolated，分支 feature/honeyos-work-mode。正式 Gateway 的 HONEYOS_PROJECTS_HOME 指向 /mnt/d/HoneyOS Projects。候选文件的 Windows 位置为 D:/HoneyOS Projects/HoneyOS Work/<work-id>。HoneyOS 运行数据、发布副本和 Ubuntu 安装的 bubblewrap 0.9.0 均在 D:/WSL/HoneyOS-Ubuntu/ext4.vhdx 内。

前端 55 项、后端 95 项和 2 项子测试通过，生产构建通过。Windows 从回环入口请求新版首页和脚本均返回 200。使用 D 盘真实候选目录验证 Python sandbox 可读取测试脚本，候选挂载为只读，沙箱内看不到 Windows 磁盘或宿主用户目录。

回滚配置为 /home/zyh20/.honeyos/release-backups/work-mode.lAMX9j/gateway-original.conf，目标为 a4f21a8。恢复到原同名 systemd drop-in 后重新加载并重启 Gateway。

工作模式首版的交付范围为候选 Skill 和代码文件、受限 Python 验证，以及可交互的工作流程。将候选接入已有项目、安装 Skill 或发布功能仍需独立接入与明确授权。
