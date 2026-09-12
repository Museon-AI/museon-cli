# CLI 2.0 命令面迁移

状态：未发布的工作树变更；没有升级版本或自动修改线上任务。退役不改旧业务后端；新增prompt媒体生成及私有文件上传有最小后端候选，尚未部署。

保留 research、campaign-monitor、content-analysis、artifacts、social-account 的 13 个指定入口、routines、skills 和认证、workspace、schema、setup 等基础入口。新增 media 五个原子入口（upload/import/get/generate/status），普通文件通过upload/get的显式file类型分支。新增 hireaicreator 40 个业务命令；ai-slideshow 以素材7条、独立生成3条和旧 slideshow 发布22条承接明确保留能力；仍是未发布候选。

## 旧入口处理

旧顶层 asset、account-publish、account-operation、agentic-campaign（含兼容别名）、generation、product、evaluator 退出 CLI。social-account 仅保留 list/get、连接链接、账号绑定云手机、表现读取、资料编辑和头像生成共 13 条；原配置、版本和排期命令从 social-account 顶层退出，并按下文迁入 `ai-slideshow publish`。历史数据和后端 API 不受影响。仍调用旧顶层域的脚本会得到 unknown command，不能假装执行成功。

旧 asset 的媒体创建按来源迁移：本地文件使用 `media +upload --file ... --media-type image|video|audio`，图片 URL 使用 `media +import --url ...`，回读使用 `media +get --id ...`。原 URL 导入后端仅支持图片，不能用于视频/音频。旧 asset 的 slideshow 素材和旧 generation 的 slideshow 生成迁入 `ai-slideshow asset` 与 `ai-slideshow generation`；生成不再暴露账号或排期参数。旧 slideshow 指定产物发布迁入 `ai-slideshow publish`，账号和时间仅在发布阶段提供。旧 `account-operation` 与 evaluator 没有兼容转发；旧 account-publish 批量资产池/排期计划和 social-account 发布配置/版本/排期命令已迁入 `ai-slideshow publish`；报告校验、托管与分享继续使用 `artifacts`。HireAICreator 已由40个直接API命令承接，见HireAICreator设计与实际验收报告，不能改写成旧领域。

本地报告可由 Bash 写文件，并先用 `artifacts +validate` 校验，再按用户授权使用 `artifacts +upload` 托管；media 不承接报告分享，也不能用于证明业务产物已完成。每次写入应保留返回 ID，使用所属领域回读验证真实状态；超时且无可靠 ID 时停止依赖该结果的后续写入。

## 升级前核查

1. 在实际运行脚本、已启用 routines 的 instructions 和宿主提示词中搜索上述旧领域及对应 skill 名称。逐项选择迁移、保留旧运行环境或明确停用；本次不自动暂停或重写任务。
2. 在干净环境安装候选 wheel，使用 schema 确认所需命令和参数，再切换工作流。
3. 新 wheel/setup/skills archive 仅分发 base、research、hireaicreator、ai-slideshow、campaign-monitor 五个 skill；artifacts、social-account、routines、content-analysis 归 base references，Instagram Hook 调研归 research references。旧 assets、generation、account-publish、agentic-campaign、evaluator skill 与 experiment-brain 不再分发。
4. setup 不会自动删除宿主已安装的退役 skill。升级时先辨别这些目录是否由旧 CLI 安装、是否包含用户修改，再由用户明确执行迁移/移除；不要删除同名个人技能。本次没有操作真实宿主技能目录。
5. 发布时需同步 monorepo command catalog、安装指引及 runtime prompt/skill 引用，并验证轮子与运行时包。当前版本号未变，不得以现有已发布版本覆盖发布候选产物。
