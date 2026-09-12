# Media 原子能力

## Mental model

`media`提供文件输入、prompt 生成和事实回读。所有命令使用所选 workspace；跨工作区操作显式传`--workspace-id`。图片/视频/音频上传仍使用原媒体接口；普通文件使用已有 artifact 账本，不是 media 表。业务视频版本、发布和交付仍由 HireAICreator 回读。

新`+generate`、`+status`和普通文件上传是本地未发布候选：后端尚未部署，新模型 credits 尚未配置；旧服务器可能返回404，生成可能返回`MEDIA_GENERATION_PRICING_UNAVAILABLE`。不能把本地测试视为真实模型完成。

## Shortcuts

| 目的 | 命令 |
| --- | --- |
| 上传本地视频 | `museoncli media +upload --file ./clip.mp4 --media-type video` |
| 上传私有普通文件（含Markdown） | `museoncli media +upload --file ./report.pdf --media-type file --file-id <stable_uuid>` |
| 导入图片 URL | `museoncli media +import --url https://example.com/image.jpg` |
| 读媒体记录 | `museoncli media +get --id <media_id>` |
| 读普通文件及重新签名链接 | `museoncli media +get --kind file --id <artifact_id>` |
| 生成图片 | `museoncli media +generate --type image --prompt 'A blue cup' --idempotency-key draft-image-01` |
| 生成文字描述的视频 | `museoncli media +generate --type video --prompt 'A cup rotating slowly' --duration-seconds 5 --aspect-ratio 9:16 --idempotency-key draft-video-01` |
| 查生成任务 | `museoncli media +status --task-id <task_id>` |

图片默认`gpt-image-2.5-flare`，可选`gpt-image-2.5-sunburst`；固定1024×1024、medium、PNG。视频固定`kling-3.0-standard`文字生成，默认5秒9:16，支持3–15秒和9:16/16:9/1:1；无音频。模型字符串原样传递，不做连字符转下划线。实际固定参数也落在任务`request`，以回读为准。

生成必须保存原始请求和幂等键。同工作区、同用户、相同键与请求返回同一任务；换prompt/model仍用同键会409。余额检查沿用现有语义，不是资金预留；已完成生成使用固定task ID幂等计量。未明确结果前不能自动换键重试。

Ground truth顺序：保存提交`data.task_id/media_id` → `+status`核对workspace/request/模型、`status=completed`且`media_ready=true` → `+get`核对`data.asset.id`、类型、`status=completed`、可用URL。`queued/submitting/polling/materializing/metering`都不是完成；`unknown`说明可能已向provider提交，停止新写入并保留任务ID诊断。CLI不会等待模型完成或自动生成Bash循环。

图片/视频/音频upload和图片import回执ID在`data.asset.media_id`；get为`data.asset.id`。普通file回执为`data.artifact_id`与`kind=file`，get走artifact接口（返回`data.id`），不可当作media ID传给clip或content-analysis。普通文件按服务端大小上限（默认50MB）上传GCS，不启用公开分享；download URL默认1小时有效，可再次get重新签名。未传file-id时CLI会生成，失败消息保留恢复ID；明确工作流建议先生成并保存稳定UUID。

`gs://`地址不是浏览器URL；选用下游明确接受的URL。媒体/文件写入回执丢失都不能据此判断“没有上传”。file可用同ID读回或同ID相同文件重试；相同ID不同内容不允许覆盖。

示例脚本：`bash skills/museon-content-workflow-base/scripts/generate-media-once.sh WORKSPACE image PROMPT STABLE_KEY NEW_DIRECTORY`。需要bash、jq和已配置的CLI；它只查询一次，pending输出不会推进media下游，unknown或矛盾回读会非零退出。目录必须是新的，以保留每次证据。

## DON'T

- **DON'T**把视频/audio URL送进仅支持图片的`+import`。
- **DON'T**把普通文件的artifact_id、媒体media_id、生成task_id混用。
- **DON'T**把dry-run、202、`media_id`存在或provider request ID当成产物完成。
- **DON'T**对unknown生成换键重提，或把缺失定价的拒绝绕成旧generation命令。
- **DON'T**将签名下载URL当作永久公开链接，也不要为分享而自动开启public。

## Relationships

Research和content-analysis消费可用媒体URL/ID；普通PDF/CSV等文件只提供通用存储与下载。HireAICreator视频的修改后成片仍通过video/export核验version/revision。媒体生成不创建Actor、Persona、账号或发布计划。
