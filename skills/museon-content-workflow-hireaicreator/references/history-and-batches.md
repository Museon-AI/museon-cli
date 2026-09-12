# 历史生成素材与批次查询

用于复用某个参考 Hook 的历史视频、检查一次生成批次的进度。先读取实际 command schema；这些入口只读，不会提交生成、取消或重试任务。

## 资源与选择

- Hook 是参考素材；item 是一条生成结果，有自己的 `id`、`hook_id`、`batch_id` 和状态。不要将 item ID 当作 HireAICreator video ID。
- batch 是一次生成任务的集合。当前公开批次对象没有名称；按工作区列出批次，结合 `id`、`created_at`、`status`、数量选择，再用 ID 查询。
- batch 的汇总计数不能替代每个 item 的结果检查。`completed` 状态也不能证明内容适合当前脚本。

## 跨批次找历史素材

```bash
museoncli hireaicreator item +list --workspace-id "$WORKSPACE_ID" --hook-id "$HOOK_ID" --status completed --page 1 --page-size 100
museoncli hireaicreator item +get --id "$ITEM_ID"
```

列表支持工作区、Hook ID、状态、Actor、Persona 和分页。先用 `hook +list --search` 或 `--tag` 找到参考 Hook，再用返回的 ID 作为 `item +list --hook-id`，由服务端筛选跨批次历史结果。完成匹配结果的分页，不要只看第一页就断言不存在。这里没有名称或关键词搜索参数；Hook 关键词搜索与生成素材查询是两个步骤，不必经过 batch。

列表返回 `result_video_url`；详情返回 `result_video_media_id`，二者响应并不相同。需要按媒体身份回读时：

```bash
museoncli media +get --workspace-id "$WORKSPACE_ID" --id "$RESULT_VIDEO_MEDIA_ID"
```

保持 item ID、Hook ID、media ID 和实际文件的对应关系。结果媒体 ID 为空、URL 不可读取或状态失败时，报告缺失，不猜地址。下载后检查文件可读取、可解码；复用前确认画面确实支持所需内容。

## 查询批次

```bash
museoncli hireaicreator batch +list --workspace-id "$WORKSPACE_ID" --page 1 --page-size 100
museoncli hireaicreator batch +get --id "$BATCH_ID"
museoncli hireaicreator batch +items --id "$BATCH_ID" --hook-id "$HOOK_ID" --page 1 --page-size 100
```

- `batch +list` 可按 `--status` 筛选；没有批次名称或文本搜索参数。
- `batch +get` 返回批次状态、请求数量、排队/运行/完成/失败/取消数量及时间。
- `batch +items` 可按 `--status`、`--hook-id`、`--actor-id`、`--persona-id` 筛选，并分页。它返回 item 状态和结果媒体 ID；需要文件时用 `media +get` 读取。
- 详情及批次内列表按资源 ID 鉴权，不接受工作区覆盖参数。由实际服务端响应和访问控制确定对象，不能把权限拒绝解释为记录不存在。

## Ground truth 与恢复

检查实际输出中的 `has_more`、`page`、`total`，按 CLI 输出结构读取数据；如果输出被转存文件，先读取该结果文件。按 ID 去重，并保留请求筛选条件。并发生成时计数可能变化，固定明确 item ID 后再做依赖它的工作。

查进度时继续读取同一个 batch/item ID。保留失败条目的 `current_stage`、`error_code`、`error_message` 和 `retryable`，不从可重试标记推断本次已授权重试，更不因查询为空而另起生成。此 reference 不提供写入命令。
