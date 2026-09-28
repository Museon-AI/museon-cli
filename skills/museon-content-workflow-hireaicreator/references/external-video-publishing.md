# 外部生成视频：上传与排期发布

适用场景：视频（Hook、Demo 或任意成片）在 Museon 之外生成，需要上传到平台，并按账号排期发布。
成片不需要 POV、文字叠加、开头或 BGM，也不会再渲染；发布时直接使用上传的原片。
上传成片与账号类型无关：发布方式由账号决定，与其他视频一致。

整条流程固定为 8 步。生成前的素材读取固定 3 次调用，与账号数量无关。

| 步骤 | 命令 | 性质 |
| --- | --- | --- |
| 1 选账号 | `hireaicreator account +list` | 只读 |
| 2 取 Actor 参考图，建对照表 | `hireaicreator actor +resolve` | 只读 |
| 3 取产品资料与图片 | `hireaicreator product +list` | 只读 |
| 4 外部生成 | 平台外完成 | — |
| 5 上传成片 | `media +upload --media-type video` | 写 |
| 6 登记发布任务与排期 | `hireaicreator video +from-upload` | 写，会产生发布 |
| 7 回读核对 | `hireaicreator video +get` / `video +list` | 只读 |
| 8 改期、改文案或取消 | `video +update` / `video +bulk-schedule` / `video +cancel` | 写 |

## 授权边界

- 第 6 步会生成真实的发布任务：自动发布的账号到点会发帖。只有用户明确要求「发布」或「排期」时才执行；只要求上传或出下载链接时，停在第 5 步。
- 先解析一次工作区，此后每条接受 `--workspace-id` 的命令都显式传入，不依赖跨轮保留的选择。
- 开始前用 `museoncli workspace list` 确认目标工作区在列表里。上传走的是 CLI 凭证的授权范围：只授权了部分工作区的 API key，即使用户是目标工作区成员、前面的读取都能成功，上传也会被拒（`Workspace is not available to the current user`）。这时由用户调整 key 的授权或重新登录，不要换工作区凑合。
- 视频里的人必须是发布账号绑定的 Actor。平台不会检查成片里是谁，匹配完全由调用方保证，见第 2 步的对照表。
- 写操作先用 `--dry-run` 校验本地参数；dry-run 不访问服务端，不能证明服务端会接受。
- 每一步以服务端回读为准。收到回执、上传成功或 dry-run 通过，都不代表发布完成。

## 1. 选账号

```bash
museoncli hireaicreator account +list --workspace-id "$WS" \
  --platform tiktok --platform instagram --is-active --has-actor --page-size 100
```

- 翻完所有分页，再确定账号名单；第一页不是完整名单。
- 按用户给的账号名精确查找时，用 `--search-term <handle> --search-match exact`，重复传入多个 handle。
- 返回里的 `actor_id`、`persona_id`、`platform` 直接用于后续步骤，不要逐个账号再调用 `account +assets-get`。
- 账号类型（云手机或真机）不影响能否上传，只决定发布方式（第 8 步之后的结果）。
- 每条视频最多选 2 个账号，且每个平台最多 1 个；只支持 TikTok 和 Instagram。
- 一条视频的所有账号必须绑定同一个 Actor。不要按平台随手搭配 TikTok 和 Instagram 账号：大多数 Actor 只在一个平台上有账号。

## 2. 取 Actor 参考图

把第 1 步得到的 `actor_id` 去重，一次最多 200 个：

```bash
museoncli hireaicreator actor +resolve --workspace-id "$WS" \
  --actor-ids <actor_id_1> --actor-ids <actor_id_2>
```

- 每个 Actor 返回 `images[]`（主参考图）和 `profile_image`（头像），各带 `media_url`、`permanent_media_url`、`thumbnail_url`。长期保存用 `permanent_media_url`。
- 超过 200 个时按 200 分批，调用次数显式可数，不要按账号逐个读取。
- 没有 `actor_id` 的账号要在结果里单独列出，由用户决定是否先绑定 Actor（`account +actor-set`），不要猜测。
- Actor 和 Persona 是两个资源，不要互换 ID。

然后建一张以 Actor 为主键的对照表，后面的生成和登记都只从这张表取值：

```json
{
  "<actor_id>": {
    "actor_name": "Camila Vance",
    "reference_image": "<images[0].permanent_media_url>",
    "accounts": {
      "tiktok": {"id": "<pool_account_id>", "username": "<handle>"},
      "instagram": {"id": "<pool_account_id>", "username": "<handle>"}
    }
  }
}
```

- 只按 `actor_id` 关联：账号行里的 `actor_id` 对上 `actor +resolve` 返回的 `id`。不要按名字、列表顺序或长相关联。
- 某个 Actor 在某平台有多个账号时，由用户指定用哪一个，不要自动挑。
- 账号自己的头像（`creator.avatar_url`）是会过期的临时链接，只用于显示和人工核对，不能代替 Actor 参考图。

## 3. 取产品资料与图片

```bash
museoncli hireaicreator product +list --workspace-id "$WS" --page-size 100
```

- 一次返回产品的 `name`、`description`、`website_url`、`tags`、`selling_points`、`target_audiences`，以及 `brand_logos`、`product_images`、`website_screenshots`、`app_screenshots`（每项带 `media_url`）。
- 翻完所有分页。
- 需要知道某个账号绑定的是哪个产品时，才读 `account +assets-get` 的 `product_id`；多个账号的发布素材池用 `ai-slideshow publish +asset-pools-batch-get` 一次读取。

## 4. 外部生成

在平台外生成视频和发帖文案：每条视频用对照表里一个 Actor 的参考图生成，并且只发给这个 Actor 名下的账号。开始前建一份本地映射文件，贯穿后续每一步：

```json
[
  {
    "file": "out/tiktok-001.mp4",
    "actor_id": "<actor_id>",
    "reference_image": "<生成时用的参考图>",
    "publishing_account_ids": ["<该 Actor 名下的 tiktok 账号>"],
    "caption": "文案 #tag",
    "scheduled_at": "2026-10-02T09:30:00+08:00",
    "schedule_timezone": "Asia/Shanghai",
    "media_id": null,
    "video_ids": []
  }
]
```

成片要求：

- 视频文件，建议 MP4；单个文件不超过 500MB。
- 文案 1–2200 个字符。
- 如果本批要求必带话题或 @，文案里要包含它们，并在第 6 步通过 `required_hashtags` / `required_mentions` 声明（各最多 5 个）。

## 5. 上传成片

```bash
museoncli media +upload --workspace-id "$WS" --media-type video --file out/tiktok-001.mp4
museoncli media +get --workspace-id "$WS" --id <media_id>
```

- 每个文件上传一次，把返回的 `media_id` 写回映射文件。
- 用 `media +get` 确认状态为完成，再进入第 6 步。
- 上传没有幂等键。结果未知时可以重传：多出来的媒体记录不会被发布，登记只认映射文件里最终写入的那个 `media_id`。
- 同一个 `media_id` 同时只能有一组未取消的发布任务，重复登记会被拒绝。

## 6. 登记发布任务与排期

每批 1–50 条。提交前重新核对绑定，确认生成期间没有人改过账号的 Actor：

```bash
museoncli hireaicreator account +list --workspace-id "$WS" --actor-id <actor_id> --page-size 100
```

返回的账号必须包含映射文件里这条视频的每个账号；对不上就停下，回到第 2 步，不要照旧提交。

先 dry-run，再正式提交：

```bash
museoncli hireaicreator video +from-upload --workspace-id "$WS" \
  --idempotency-key "external-upload-<批次标识>" \
  --args-file batch.json --dry-run

museoncli hireaicreator video +from-upload --workspace-id "$WS" \
  --idempotency-key "external-upload-<批次标识>" \
  --args-file batch.json
```

`batch.json`：

```json
{
  "items": [
    {
      "media_id": "<media_id>",
      "publishing_account_ids": ["<tiktok_account_id>", "<instagram_account_id>"],
      "caption": "文案 #tag",
      "scheduled_at": "2026-10-02T09:30:00+08:00",
      "schedule_timezone": "Asia/Shanghai"
    }
  ],
  "required_hashtags": ["#tag"]
}
```

- 每个账号生成一条发布任务，返回的 `items[].id` 写回映射文件。
- 幂等键在提交前生成并写进映射文件；结果未知时用同一个键、同一份 `batch.json` 重试，会拿回同一批任务。换键或改内容重试会重复排期或报 `IDEMPOTENCY_KEY_REUSED`。
- `scheduled_at` 必须带时区偏移，并且在未来。平台在临近发布时间（约提前 1 小时）开始准备发布，给足余量。
- 不填 `scheduled_at` 时任务只登记不发布，之后必须先排期（第 8 步）才会发布，人工确认发布也要求先排期。
- 可选 `campaign_id` 把任务归入某个 Campaign，便于在看板统计。

常见拒绝：

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| `UPLOADED_SCHEDULE_PAST` | 排期时间不在未来 | 换一个未来时间 |
| `UPLOADED_ACCOUNT_UNAVAILABLE` | 账号不在该工作区或未启用 | 回到第 1 步重新选 |
| `UPLOADED_PLATFORM_LIMIT` | 同平台选了多个账号，或账号超过 2 个 | 每个平台只留 1 个 |
| `UPLOADED_PLATFORM_UNSUPPORTED` | 账号不是 TikTok / Instagram | 换账号 |
| `UPLOADED_MEDIA_NOT_FOUND` / `UPLOADED_MEDIA_NOT_READY` | 媒体不存在、不是视频或未完成 | 回到第 5 步核对 |
| `UPLOADED_MEDIA_DUPLICATED` | 同一批里同一媒体出现两次 | 去重 |
| `UPLOADED_MEDIA_ALREADY_ASSIGNED` | 该媒体已有未取消的发布任务 | 用已有任务，不要重复登记 |
| `publishing_account_daily_capacity_reached` | 账号当天发布数已满 | 换时间或换账号 |
| `IDEMPOTENCY_KEY_REUSED` | 同一个键配了不同内容 | 核对是否已有同批任务；确属新批次才换新键 |

整批要么全部登记成功，要么全部不登记；被拒后修正再提交，不会留下半批任务。

## 7. 回读核对

```bash
museoncli hireaicreator video +get --id <video_id>
museoncli hireaicreator video +list --workspace-id "$WS" \
  --publishing-account-id <account_id> --scheduled-from <开始> --scheduled-to <结束>
```

逐条核对 `composition_kind` 为 `uploaded`、`status` 为 `scheduled`（未排期为 `approved`）、`scheduled_at`、`caption`、`publishing_account_id` 与映射文件一致。

## 8. 改期、改文案或取消

- 改单条：`video +update --id <video_id> --expected-version <version>`，只允许改 `caption`、`scheduled_at`、`schedule_timezone`。
- 批量改期：`video +bulk-schedule`，每项带 `video_id`、`expected_version`、原账号 `publishing_account_id`、新 `scheduled_at` 与时区。上传成片不能换账号；要换账号就先取消这个媒体的全部任务，再用同一个 `media_id` 和新的幂等键重新登记。
- 取消：`video +cancel --id <video_id> --expected-version <version> --yes`。
- 版本号取自最近一次回读。版本冲突时重新读取再决定，不要自动覆盖。
- 发布开始前修改文案或时间，原有的待发布任务作废，按新内容重新排；开始发布或已发布后不能再改。

## 发布结果

- 自动发布的账号：到排期时间自动发布，状态依次为 `scheduled` → `publishing` → `published`，`published_content_id` 为发出的帖子。排期时间过后长期未能发布会变为 `missed`，并带失败原因。
- 真机账号：用 `delivery +share --collection-kind video-filter` 生成分享链接（`video_filter.video_ids` 填这批任务），交给手机操作员下载原片、复制文案、发布，并在分享页标记已发布；系统随后匹配同步到的帖子，变为 `published`。
- 发布后的表现数据用 `dashboard +get` 按 Campaign 和日期读取。

## DON'T

- 不要在用户只要求上传时登记发布任务。
- 不要为结果未知的写操作换新幂等键重试，也不要重复上传同一个文件来「重试」登记。
- 不要逐个账号读取 Actor 或产品；按本文的批量命令读取。
- 不要把回执、dry-run 或 `video +get` 里的 `scheduled` 当成已发布；以 `published` 和帖子 ID 为准。
