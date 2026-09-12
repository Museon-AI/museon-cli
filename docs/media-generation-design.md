# Media prompt生成与普通文件第一版

本地未发布候选；不升级0.5.25、不commit/push、不部署、不调用收费模型。AI Hook原40命令及真实测试工作区验收保留在`ai-hook-test-coverage.md`，不把新媒体离线测试混进原真实覆盖率。

## 对外接口与身份

| CLI | 接口 | 回读事实 |
| --- | --- | --- |
| `media +generate --type image|video --prompt ... --idempotency-key ...` | POST `/api/v1/media/generations` | 202仅接收；task_id/media_id/workspace_id |
| `media +status --task-id ...` | GET `/api/v1/media/generations/{task_id}?workspace_id=...` | effective request、provider/model、phase、error、media_ready |
| `media +get --id ...` | 已有GET `/agent-cli/assets/media/{media_id}` | 媒体状态、真实URL；不证明AI Hook的版本或交付 |
| `media +upload --media-type file --file ... --file-id ...` | POST `/api/v1/media/files` | kind=file、artifact_id、workspace_id、private、临时下载URL |
| `media +get --kind file --id ...` | 已有GET `/agent-artifacts/{artifact_id}?workspace_id=...` | 文件账本和重新签名下载URL；不是media表 |

普通APIKey走已有认证，写入要求workspace editor，读取要求workspace访问权；还必须属于工作区组织，非grant_all密钥必须具备agent-cli scope和该workspace授权。新入口拒绝Mel capability，既有artifact GET保持原capability边界，不改allowlist。所有文件仍使用已有GCS和artifact账本；没有给media类型check新增file，也没有恢复artifacts业务命令。

## 生成账本

复用tasks的非空workspace/user/type/scope/key唯一键和request_fingerprint，type为media_generation；media记录使用同值UUID（不同表）确定唯一产物身份，source_type=generated。不同资源仍由不同API读写，不能因UUID相等混用。

请求hash基于规范化的用户请求和执行默认值，不含随机ID和可变化的定价；模型字符串原样保留。首次请求先确定精确配置价格并做已有余额检查，再持久任务、media占位、投递。重放先取原账本，同键不同内容409；配置或余额变化不阻断原回执。

CAS绑定status/run_id/updated_at。执行先写submitting再调用provider：Kling立即持久job后只poll，绝不再次submit；AnyFast无法恢复的提交/存储窗口明确unknown。图片返回已确认生成后先记录provider事实，存储失败是OUTPUT_STORAGE_UNKNOWN，不谎称没有生成。产物先写media，再进入metering；严格幂等计量成功后才task completed。失败先持久failing检查点、media失败，再task终态，恢复不会漏掉第二张表。

媒体任务创建时设置`notified=true`，进度由CLI的`media +status`读取，不进入旧通用通知托盘。旧托盘“标记已通知”会修改`updated_at`；若混入媒体任务，会使正常worker在provider返回后丢失CAS更新资格。真实PostgREST回归验证普通任务仍能标记，媒体任务在按ID或全量标记时均不被修改，同幂等键重放也不改变执行版本。

Scheduler是pending推进者；worker未完成poll或可安全恢复的阶段释放pending后ACK。恢复前查询当前确定CloudTask，存在则让其继续；不存在才CAS持久下一代delivery_key并派发。旧投递的key与账本不符不能重新claim。submitting失联直接unknown，不因队列重试换键扣费。取消也保留未知/可恢复阶段证据。

通用1天超时覆盖和30天任务删除排除此type，以保留恢复与幂等事实。恢复查询在LIMIT之前约束type/status/deleted_at/updated_at，并由最小partial index保护；迁移为`20260911153000_media_generation_recovery_index`。不新增表、workflow引擎或provider路由框架。

## 模型与价格边界

图片默认gpt-image-2.5-flare、可选sunburst；1024×1024、medium、PNG。视频是Kling3 standard纯文本入口，默认5秒9:16，支持3–15秒与三种比例，无音频；固定negative prompt/shot_type/cfg也写入effective request。

`MEDIA_GENERATION_MODEL_CREDITS`是精确模型→正整数映射，图片单位credits/image，Kling单位credits/second；候选代码只为下述两个已定价模型提供默认值，环境配置可整体覆盖。映射中缺少的模型明确503，不套未知模型fallback，不把供应商美元成本当产品售价。使用已有dashboard.content-generation credit passthrough计量；沿用余额检查语义，并非资金预留。本次没有改线上Doppler。

用户为测试阶段确定`gpt-image-2.5-flare=10 credits/image`和`kling-3.0-standard=15 credits/second`作为候选代码默认值，并保留`MEDIA_GENERATION_MODEL_CREDITS`环境覆盖；`gpt-image-2.5-sunburst`没有依据，继续缺价失败。10与15也分别吻合仓库既有`token_costs.py`中的未知图片默认credits/image和未知视频默认credits/second，而不是从供应商美元成本换算。因此一张Flare图片记10 credits、三秒Kling视频记45 credits，本轮合计55 credits。该决策让测试阶段可以验收既有余额与幂等计量链路；没有改线上Doppler，也没有把供应商采购价写成产品售价。

AnyFast公开pricing页面使用官方只读`GET /api/pricing?square_only=true`返回`gpt-image-2.5-flare`的`billing_mode=token`：文本输入USD 5/M tokens、输出USD 30/M tokens、cache USD 1.25/M tokens、图片输入USD 8/M image tokens。官方OpenAPI确认该SKU走`/v1/images/generations`，但生成响应不返回usage；本实现固定`n=1`、1024×1024、medium、PNG。因此现有官方资料不能在调用前可靠换算固定USD/image，真实采购成本应在生成后以账号usage为准。

Fal公开模型页对精确端点`fal-ai/kling-video/v3/standard/text-to-video`标示无音频为USD 0.084/second；production账号的官方只读`GET /v1/models/pricing`却返回USD 0.14/second，且返回项没有audio、quality或折扣维度。官方`POST /v1/models/pricing/estimate`按3 seconds给出USD 0.42。两者保留为不同来源：USD 0.42只能称为账号价格API的三秒预估，不能称为无音频最终扣款；真实生成完成后应以对应usage line item为准，若无法可靠关联则继续报告预估和公开页差异。

## 普通文件

沿用AgentArtifactFileService，仅新增私有、create-only、强制对象存储分支。Markdown也按download存GCS。稳定file_id与文件指纹保护重放；不同内容不能覆盖，同ID并发内容的GCS路径含指纹，数据库仍INSERT。服务端流式检查既有大小上限，默认50MB。签名失败可能发生在账本已提交后，CLI保留ID和原HTTP原因，读同ID恢复；链接默认1小时，可重新get签名，不开启public分享。

## 验证口径

## 本地候选 API 接生产数据库的受控验收

2026-09-12 使用当前未发布 CLI 候选和本地 Docker API 做了一轮受控验收。API 只监听 loopback，运行配置从 Doppler production profile 下载后仅保留在启动进程内存和容器环境中；启动适配器在合并 override 前后都删除 `DOPPLER_TOKEN*`，再让仓库 canonical local guards 覆盖生产值。只强制重建 API 容器，frontend 沿用健康实例。重建后脱敏审计确认 `ENVIRONMENT=local`，Redis、Prefect 和告警关闭，Cloud Tasks、Pub/Sub、Scheduler 走 loopback bypass，Tasks、Agents、Render 外发 target 为空，`DOPPLER_TOKEN*` 变量数和非空数均为0。本方式不验证 GCP 持久队列、真实 delivery fencing 或 worker recovery，因此没有运行跨 workspace 的全局 media recovery。

GCS 客户端现有凭据路径有三类：显式 `GOOGLE_APPLICATION_CREDENTIALS` / `GCS_CREDENTIALS_PATH` 文件会按 service-account JSON 载入；无显式文件时使用 Application Default Credentials；生成 V4 URL 时，具备本地 signer 的 service-account/impersonated credentials 可直接签名，Cloud Run metadata credentials 则刷新后以 runtime service-account identity 调 IAM SignBlob。Doppler production profile 本轮只发现非空的 GCS bucket、project、过期时间等运行配置，以及 Cloud Tasks/Agents 的 OIDC service-account identity；未发现 `GOOGLE_APPLICATION_CREDENTIALS`、`GCS_CREDENTIALS_PATH`、service-account JSON 或独立 GCS signing identity。OIDC identity 不能当作 GCS 签名凭据。

本机已有 ADC 是 `authorized_user`。验收时清空两个显式 GCS credential path，并将该 ADC 只读挂到容器默认 well-known path；这足以完成私有对象上传和 artifact 账本写入，但普通用户 ADC 不暴露 `service_account_email`，无法自行选择签名身份。对 `museon-api-prod@movora-469510.iam.gserviceaccount.com` 执行只读 `testIamPermissions` 后，`iam.serviceAccounts.signBlob` 与 `iam.serviceAccounts.getAccessToken` 均未授予；请求 impersonated access token 也明确返回 `IAM_PERMISSION_DENIED`。现有 SDK 的签名分支可直接使用调用者 access token 请求目标账号的 IAM SignBlob，因此如果只补本地 V4 URL 验收，最小管理员动作是在目标账号上给当前验收主体授予仅含 `iam.serviceAccounts.signBlob` 的自定义角色，不需要同时授予 `getAccessToken`。本轮没有自行施加该权限、没有改 IAM、没有生成或下载长期 service-account key，也没有再次上传已经落库的稳定 file ID。

证据单独归类为“本地候选 API + 生产 DB”，不计入已部署 API 覆盖。媒体生成正向链路已经分别完成一张 Flare 图片和一段三秒 Kling 视频：两者均以稳定幂等键创建 task，真实调用 provider，写回 `media` 与 GCS 对象，并在任务终态回读；图片是 1024×1024 PNG，视频是 720×1280 H.264、实际容器时长约3.04秒，两份对象均完整下载并解码。production Usage 底表按 task/business ID 独立核对，图片与视频各只有一条 raw event 和一条 metered event，分别记10和45 credits；计量重试没有重复扣量。Clip 成功分配与私有文件签名下载仍未完成，不能因媒体链路通过而合并报告为全部正向目标成功。

负向保护证据另列：无凭据请求返回401、认证后不存在任务返回404、跨 workspace 私有文件读取被拒绝；无 Actor 账号分配返回业务400且 Clip 未变化；旧配置下缺价 Flare 请求返回503且按该幂等键查询 generation row 为0；draft 旧版本写入返回409且未覆盖新 caption。Flare 与 Kling 现在已有候选代码默认价，缺价保护后续以仍未定价的 Sunburst 或显式空映射验证，不能继续把 Flare 503当作当前默认行为。

Flare 首次真实请求暴露了 AnyFast 契约差异：官方 OpenAPI 说明 PNG 会忽略 `output_compression`，实际 Flare 网关却以 HTTP 400 明确拒绝该参数。客户端现仅在 JPEG 输出时发送 `output_compression=90`，PNG 请求不再携带 JPEG 专属参数；修复后同一 Flare SKU、1024×1024、medium、PNG 正向生成成功。失败任务现在只持久化并返回有界的 `provider_http_status`、供应商机器错误码和预定义 `failure_reason`，不保存原始响应、prompt、API key 或其他凭据。旧失败 task 缺少这些字段，根因历史记录仍保持 unknown。

真实argv→builder→最终HTTP包括非默认model、视频时长/比例、Idempotency-Key、workspace覆盖、普通文件multipart/稳定ID/kind、错误回执。真实Bash脚本验证pending不推进、unknown停止、错误媒体回读失败、完整任务与媒体一致才成功。

API/service使用合成provider做并发、取消、失联、计量失败、媒体写回失败、终态provider失败、权限和价格缺失测试。独立PostgreSQL16+PostgREST12.2.3验证真实唯一键/CAS、强制终止子进程、旧owner fencing、通用清理保护。索引migration真实PG响应测试由同次变更提供。没有真实provider或新线上workspace端到端结果；未部署、未配置模型价格仍阻塞真实验收。

本轮最终检查：CLI完整pytest 519通过；API相关组合51通过（包含真实PostgreSQL/PostgREST 3项）；双仓catalog同步、Ruff、生成文档/schema检查、wheel公共产物检查、93命令干净安装和`delivery doctor --workflow deploy-api-prod`通过。doctor使用本地一次性数据库与替身边界，不代表执行生产部署。新命令没有真实线上provider执行覆盖；AI Hook既有线上验收的27/40执行、25/40成功和33/272真实参数事实仍单独记录。

继续验收时新增通知写入与执行租约的真实回归，修复前失败、修复后通过；该PostgreSQL/PostgREST文件现为4项全部通过，相关Ruff通过。上述51项是上一轮组合结果，不能将本轮增量复跑写成完整组合重跑；最新AI Hook真实覆盖以`ai-hook-test-coverage.md`为准。
