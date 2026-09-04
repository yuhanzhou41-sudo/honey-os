# HoneyOS iMessage 本地生活 Demo 验证指南

这份文档用于从功能分支安装 HoneyOS，用测试者自己的 Photon 项目和 Google Maps API Key，在 iMessage 里验证“同一个伴侣 + 同一份记忆 + 本地生活工具”的完整链路。

## 这个分支包含什么

- Photon 是正式独立的 iMessage 渠道，支持登录、项目复用、手机号允许列表、长连接、图片附件和可点击的 rich link。
- Google Maps 本地生活 Skill 会优先调用 Google Places API，返回评分、距离、地图链接和真实店铺图片。
- 可选把私有 CSV 放到本机索引目录；没有本地命中时仍会调用 Google Places，不依赖任何人的测试数据。
- Story 模式和主聊天共用 HoneyOS 伴侣身份与记忆，章节结束后由用户确认是否保存到“共同经历”。

## 1. 安装这个分支

需要 macOS 或 Linux、Git、Node.js 18+ 和可用的模型 API Key。

```bash
git clone --branch feat/imessage-local-life-demo https://github.com/springbrand-lab/honey-os.git
cd honey-os
HONEYOS_INSTALL_REF=feat/imessage-local-life-demo ./install.sh
```

安装完成后会启动本地前端。在 onboarding 中配置模型服务、API Key 和模型 ID。不要复用其他测试者的 `~/.honeyos`。

## 2. 连接 Photon iMessage

1. 准备一个 Photon 账号，并确保测试手机能正常发送蓝色 iMessage。
2. 运行 `honeyos photon setup --phone +15551234567`。
3. 浏览器会打开 Photon 设备授权页。授权后回到终端，等待它创建或找到项目、注册手机号、安装 sidecar，并打印分配的 iMessage 号码。
4. 如果已有项目，运行：

```bash
honeyos photon setup \
  --project-id YOUR_PHOTON_PROJECT_ID \
  --phone +15551234567
```

5. 检查状态并启动：

```bash
honeyos photon status
honeyos restart
```

测试者向终端显示的 Photon iMessage 号码发信息。只有 `PHOTON_ALLOWED_USERS` 里的手机号能进入这个 HoneyOS；每位产品测试者都应用自己的 Photon 账号、项目和允许列表。

## 3. 配置 Google Maps

在 Google Cloud 项目中启用 Places API (New)，并对 API Key 设置 API 限制和合理的用量上限。然后运行：

```bash
honeyos config set GOOGLE_MAPS_API_KEY YOUR_GOOGLE_MAPS_API_KEY
honeyos restart
```

如果要验证私有本地生活索引，把 CSV 放到 `~/.honeyos/data/local-life/`。不要把 CSV、API Key、Photon 凭据、手机号或 `~/.honeyos` 下的任何文件提交到 Git。

## 4. Demo 脚本

先在本地网页中告诉伴侣你的办公地点、偏好和称呼，再在 iMessage 中测试跨入口的记忆一致性。

### Case A：附近店铺

```text
我现在要理发了，帮我找办公室附近最合适的一家。
```

预期：

- 中间态先出现一句简短的“收到，我来看看”类进度，不会把思考、代码或 `/approve` 发进 iMessage。
- 必须调用 Google Places API，不用 Web Search、Overpass 或旧 Maps Skill 代替。
- 最终推荐包含评分、评论数、距离、可点击的 Google Maps 店铺卡片，并在 Google 返回图片时附带一张真实店铺图片。
- 没有图片时要明确说明，不得编造图片。

### Case B：同一个伴侣与记忆

```text
你还记得我刚才在网页里说的理发偏好和办公地点吗？
```

预期：回答来自同一个 `~/.honeyos` 中的伴侣身份、聊天历史与记忆；不会因为切换到 iMessage 就变成新人格。

### Case C：Story 共同经历

1. 在网页打开 Story，选一个故事和 HoneyOS 当前伴侣。
2. 完成一章并点击“结束这一章”。
3. 确认保存到“共同经历”。
4. 回到 iMessage 询问对方是否记得这段经历。

## 5. 故障检查

```bash
honeyos status
honeyos photon status
honeyos doctor
honeyos logs
```

- 没有回复：确认 HoneyOS 在运行、Photon sidecar 已连接，手机号在 allowlist 中。
- 回复要 `/approve`：表示路由没有命中原生 Google Maps 工具；检查 `GOOGLE_MAPS_API_KEY` 并重启。
- 只有文字没有图：查看 Google Places 返回的店铺是否有 photo resource，以及日志中是否有图片下载错误。
- 地图 URL 没有卡片：确认 `PHOTON_MARKDOWN=true`，并把 Maps URL 单独放在一行。

## 数据边界

代码仓库不包含任何真实用户的聊天历史、长期记忆、共同经历、伴侣人设、本地 CSV、API Key、Photon 凭据或手机号。这些数据只会在测试者运行安装和配置命令后，生成在其自己的 `~/.honeyos`。

实现入口：

- Photon 渠道：`honeyos/plugins/platforms/photon/`
- Google Maps Skill：`honeyos/companion/companion_skills/google-maps/SKILL.md`
- Google Places / 本地索引工具及 schema：`honeyos/tools/local_life_tool.py`
