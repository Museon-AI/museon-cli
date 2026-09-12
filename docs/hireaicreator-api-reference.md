# AI Hook 首版 API 映射与核验边界

本地未发布候选；真实测试工作区的受控验收结果见 [验收与覆盖口径](hireaicreator-test-coverage.md)。基于 Museon API 源码工作树核对，普通 API Key 认证；不扩展短期 capability 授权。命令使用 `hireaicreator <resource> +<action>`；v1/v2 是 HTTP API 版本，不是两套 CLI 领域。字段仅以生成 schema 实际暴露的子集为准，不声明完整覆盖后端。

Q 表示 workspace_id 位于 query，B 表示位于 body，R 表示后端按资源身份鉴权、没有 workspace 参数。R 命令不接受假 workspace override，输出不贴默认工作区标签。JSON 与 flag 的枚举值统一使用 schema 声明的 kebab-case（例如 `real-device`、`fixed-count`），发送 HTTP 时转换为后端 snake_case；字段名保持 snake_case。不要直接复制后端枚举值。JSON 来源互斥，与显式 flag 同字段也报冲突；未知和嵌套未知字段在 dry-run 前拒绝。

| 命令资源/动作 | Method / path | 输入位置 / workspace | 返回与下一阶段 ground truth |
| --- | --- | --- | --- |
| account +list | GET v2 /pool-accounts/workspace-accounts | Q；分页、精确 search_terms/search_match、阶段/设备/Actor/Persona/测试组筛选 | 原始账号分页；不可把第一页当完整名单 |
| account +eligibility | POST v2 /ai-hook-test-groups/account-eligibility | B；明确账号ID集合、可选test_group_id | items[].eligible/code，逐账号保留原因 |
| actor +list / +get | GET v2 /actors / /actors/{id} | Q；列表分页/search/source_persona_id；get路径id | creative_actors 身份、source_persona_id，不等同Persona |
| persona +list / +get | GET v1 /personas / /personas/{id} | list Q；get R | personas 身份及资源；不得当Actor ID |
| format +list / +get | GET v2 /ai-hook-formats / /ai-hook-formats/{id} | Q；分页/search/status/tag | 真实Format ID、分析/处理状态 |
| format +import-urls | POST v2 /ai-hook-formats/from-urls | B；urls/tags/extract_bgm | 返回items；逐个format +get确认ready/failed，不把202当完成 |
| hook +list | GET v1 /ai-hooks | Q；分页/search/status/source/tag | 可复用Hook列表，与生成item ID分开 |
| recipe +list / +get | GET v2 /ai-hook-recipes / /ai-hook-recipes/{id} | Q；分页/search/category_tag_id | Recipe及步骤，不是slideshow Format |
| pov +list | GET v2 /ai-hook-povs | Q；分页/search/tag | POV ID/text |
| bgm +list | GET v2 /bgm-assets | Q；分页/search/tag/mood/publishable_only | BGM ID/媒体与可发布状态 |
| clip +list / +get | GET v2 /content-clips / /content-clips/{id} | list Q；get R | 原始Clip版本/账号/migration_state/媒体ID |
| clip +batch-create | POST v2 /content-clips/batch | B；items client_key/mapping_version/媒体/标签等 | 逐项登记结果→clip +get；初始needs_account，不能称库存已可用 |
| clip +assign-account | POST v2 /content-clips/batch-assign-account | R；items含clip_id/expected_version及目标账号 | 逐项资源→clip +get核对账号与版本；不发明batch-create账号字段 |
| video +list / +get | GET v2 /ai-hook-videos / /ai-hook-videos/{id} | list Q；get R；分页/状态/plan/账号/组/时间 | 当前版本、组件/渲染/发布状态与关联资源 |
| video +readiness | GET v2 /ai-hook-videos/{id}/readiness | R | 只能证明资格/阻塞，不能证明生成完成 |
| video +update | PATCH v2 /ai-hook-videos/{id} | R；expected_version及显式patch字段 | video +get核对目标字段/版本；新成片另看export revision |
| video +generate | POST v2 /ai-hook-videos/{id}/generate | R；expected_version/generation_directions；Idempotency-Key header | accepted→video +get；任务完成与成片分别核验 |
| video +bulk-schedule | POST v2 /ai-hook-videos/bulk-schedule | R；items含版本/账号/带偏移时间/时区 | succeeded/conflicted/failures，逐video +get核对；非测试组增量重排 |
| plan +preview / +capacity | POST v2 /ai-hook-video-plans/preview / /capacity | B；组合计划 / 账号日期时区 | preview分配与阻塞 / account-capacity，不写入 |
| plan +create | POST v2 /ai-hook-video-plans | B；计划组合，显式start_generation；Idempotency-Key header | plan ID→plan +get；默认不生成，video +list --plan-id再核验 |
| plan +get | GET v2 /ai-hook-video-plans/{id} | R | 持久计划及生成状态，不把记录存在当成片 |
| test-plan +ensure | GET v2 /ai-hook-test-plans | Q；**后端get_or_create有写入，归类write** | 返回持久plan ID供test-group列表；重复读取同工作区默认计划 |
| test-group +list / +get | GET v2 /ai-hook-test-groups / /ai-hook-test-groups/{id} | Q；list要求plan_id与分页 | 当前组/成员/排期状态，只诊断迁移阻碍 |
| test-group +preview | POST v2 /ai-hook-test-groups/preview | B；test_group_id、可选campaign_id | 持久组驱动的preview与缺口，不暴露已失效的旧请求排期字段 |
| warmup +list / +journeys | GET v2 /pool-account-warmup/strategies / /journeys | Q；分页/status，journeys可选strategy_id/current_only | 暖号策略与参与状态；不自动晋级/迁组 |
| dashboard +get | GET v2 /ai-hook-dashboard | Q；campaign_id/date_from/date_to/timezone及账号/组筛选 | 原始看板及数据新鲜度，未回收不等于零 |
| delivery +preview / +share | POST v2 /ai-hook-public-video-collections/preview / /share | B；collection_kind/id或video_filter | preview只有计数；share有副作用/预热，返回token→delivery +get |
| delivery +get | GET v2 /public/ai-hook-test-groups/{token} | R；token路径、page/page_size | total/items核验实际视频集合；不发明has_more |
| delivery +export | POST v2 /ai-hook-videos/{id}/exports | R；expected_version/hook_resolution；Idempotency-Key header | export ID→delivery +export-get |
| delivery +export-get | GET v2 /ai-hook-video-exports/{id} | R | status completed、video_id/video_version/render_revision及download_url |

## 首版输入与结果限制

- Plan 可以使用现有Format或Hook与Demo/Clip规则组合；具体组合约束由服务端preview最终核验。JSON schema的本地校验不是业务preview。
- Actor、Persona仅查询，不改表、绑定或身份。账号迁移不在首版写入范围。
- Clip batch幂等身份是workspace+client_key+mapping_version；批次参数不能因重试换身份。没有通用header幂等。
- 分享固定快照必须先完成video列表分页、显式提供video_ids；动态过滤集合会随时间变化。preview仅支持带scheduled_from/to的日期过滤，拒绝video_ids及test-group/warmup-plan类型；只有统计，不是ID集合。share无通用幂等，超时结果未知就停止依赖写入，不盲重试。
- 生成/导出用同一操作的Idempotency-Key，冲突不自动改版本重试。回执只证明受理，必须按资源ID回读，并对齐期望video_version/render_revision。
- 资源绑定接口不接workspace参数；只有Q/B接口才发送工作区。不得把一个workspace的默认选择误作资源权限证明。
- 公共集合GET虽服务端无需登录，首版沿用CLI普通APIKey客户端；token只用于指定集合读取，不写入报告或测试生产fixture。
