# AI Hook 首版验收与覆盖口径

状态：已完成首轮验收、隔离草稿编辑，以及第二轮共享样本补验。已确认唯一 AI Hook Test 工作区及普通 API Key editor 权限；受控写入只使用新增中性测试素材和无账号、无排期的合成草稿，未执行发布、消息发送或公开分享。命令分母绑定本次 `contracts/command-catalog.json` 中全部40条 `hireaicreator.*` 注册项。未发布、未升级版本；隔离数据库 fixture 和打包 skill 均为合成数据。第二轮结果及其优先级见文末，线上与隔离证据不合并计数。

2026-09-12 后续新增了5条只读查询命令：`item +list/+get`与`batch +list/+get/+items`，当前HireAICreator公开面为45条。本文所有40条分母和比例均是新增前的场景验收快照，不含这5条；新增命令只完成本地参数契约、帮助与生成物检查，尚未经过真实API验收，因此不重算本文历史比例。

## 当前结果（含草稿编辑补测）

| 指标 | 分子 / 分母 | 结果与边界 |
| --- | --- | --- |
| 真实命令执行覆盖 | 28 / 40 | 70%；只计实际服务请求，未计dry-run或mock |
| 真实命令正向成功覆盖 | 26 / 40 | 65%；读命令只保证本次返回及注明的核验，空列表不证明场景完成 |
| 已执行命令通过率 | 26 / 28 | 92.86%；delivery preview修正后成功，保留首次失败作为纠偏记录 |
| 离线声明参数HTTP契约 | 272 / 272 | 100%；189个业务flag目标另有入口核验，不能推断真实参数语义100% |
| 真实逐字段参数生效覆盖 | 36 / 272 | 13.24%；逐项核对响应或持久状态，余236项未计真实生效覆盖；不把发送字段或2xx算生效 |
| 十场景完整覆盖 | 2 / 10 | 20%；另有部分5、失败1、阻塞2，完整项均为诊断/查询目标 |

26个命令的“成功”是至少一次有效服务响应及相应命令级核验，不代表所有筛选分支、所有数据规模或所有业务输出均成功。未执行的12个命令仍保留在分母中。media upload/get实际成功并用于场景6，但不加入AI Hook命令分子。

十场景分类以核心目标为准：已执行关键写入返回错误记失败；核心写入因缺少合法对象或会启动外部执行而未做记阻塞；完成有用读阶段但缺少完整样本/任务结果记部分。首轮证据不足以证明Agent已经全面优于原UI，更不足以据此要求改造后端架构。

## 覆盖率定义

不使用 pytest 用例数量表示业务覆盖率。以下指标分别给出分子、分母和未覆盖原因：

1. **真实命令执行覆盖**：在已确认的 AI Hook test workspace 实际调用的不同命令数 / 最终 AI Hook 注册命令数。dry-run、schema、MockTransport 和本地参数失败不计实际调用。
2. **真实命令成功覆盖**：真实调用且已验证相应返回/后置条件的不同命令数 / 同一最终注册数。负面请求返回预期 404/409 是错误契约验证，不替代该命令的正向成功。只返回 2xx、受理、空列表，不自动证明写后业务完成或筛选语义正确。
3. **已执行命令通过率**：上述成功命令数 / 实际执行命令数。必须与成功覆盖一起报，不能只筛选成功命令使通过率看似很高。
4. **声明参数 HTTP 契约覆盖**：从实际 parser/schema 自动枚举各命令输入，按 `命令 + 字段路径` 去重，已独立断言最终 HTTP 位置和值的输入项 / 全部声明输入项。嵌套对象/数组按叶子路径登记；header、path、workspace 都纳入。args-file、dry-run 等本地控制项另列行为覆盖；false/null/空数组/未传、多值和枚举分支属于值域案例，不伪装成多个参数。完整分母和已覆盖集合以实际测试数据产出为准。
5. **十场景覆盖**：每场景分别标记完整、部分、失败、阻塞、未执行。完整要求该场景目标的所有关键阶段完成，且后置条件成立；读了前置数据却未写入或未核验最终产物，不能算完整，按原因记部分、失败或阻塞。仅诊断场景的完整，不表示支持迁移等明确排除的动作。

离线验证与真实环境结果分表。离线全链测试能够验证输入、HTTP 序列、回执处理与实际 Bash 示例的断言；不能证明生产服务已应用所需版本、实际库存正确或模型编写的任意新脚本安全。

## 真实参数生效断言

对下列36个声明叶子字段执行了真实响应或写后持久状态断言。字段按“命令+路径”计数，与离线272项分母一致；相同字段多个值不重复加分。其余236项不计真实生效覆盖，不表示它们已失败。只验证本次值与对象，没有覆盖全部值域、模型输出或任意业务组合。

| 命令 | 已核对字段 | 数量 | 实际证据 |
| --- | --- | --- | --- |
| account +list | page、page_size、search_terms、search_match、has_actor | 5 | page=1/page_size=100完整返回92项；exact名单返回集合与预期单例一致且排除不存在项；全量Actor绑定为空，与has_actor=true返回0一致 |
| account +eligibility | publishing_account_ids | 1 | 返回account_id集合与显式输入集合相等；每项eligible为布尔值并保留阻碍code |
| actor +get | id、workspace_id | 2 | 返回身份及工作区与已确认目标相等 |
| persona +get | id | 1 | 返回独立Persona身份与目标相等，不替代Actor |
| clip +batch-create | workspace_id；items[].client_key、mapping_version、name、source_video_media_id、reusable、usage_limit、description、text_overlay_enabled、duration_ms、width、height、tags[].key、tags[].value | 14 | GET逐字段比对本轮中性素材输入，包括false与usage_limit=1；稳定client_key/mapping_version按后端uuid5身份公式核对记录ID。登记仍为needs_account，不声称已分配 |
| clip +get | id | 1 | 返回本轮新Clip身份与目标相等 |
| video +get | id | 1 | 返回已有视频身份与目标相等 |
| video +readiness | id | 1 | 返回video_id与同一视频相等，阶段阻碍另列 |
| video +update | id、expected_version、caption | 3 | 新建隔离草稿版本1→2，receipt与get一致且caption等于输入；旧版本1再次PATCH返回409，get证实版本和caption均未变 |
| plan +get | id | 1 | 返回持久plan身份与视频关联plan相等 |
| test-plan +ensure | workspace_id | 1 | 两次ensure返回同一ID且工作区相符，不推断发生新建 |
| dashboard +get | workspace_id、campaign_id、date_from、date_to、timezone | 5 | 返回归属、窗口与时区逐项等于输入；空表现指标保留null |

这些36项不能用于声称所有已实际调用参数均生效。例如Clip分配返回500，expected_version虽已发送，仍不记为真实成功参数；准确错误契约也尚未通过。字段范围为本次验收的可复查脱敏记录，不包含私人ID、原始工作区payload或凭据。

## 十场景验收矩阵

| 场景 | 实际验收目标与阶段 | 完成所需 ground truth | 副作用与前置条件 | 当前真实结果 |
| --- | --- | --- | --- | --- |
| 1 素材查找复用 | 按确定条件查询并完整读取所选 Format/Hook/Recipe/POV/BGM | 真实 ID 集合、标签/资源关联、处理状态；对有区分度样本验证筛选 | 查询只读；URL 导入会下载/解析并可能调用付费服务，另列写入案例 | 部分：资源列表可读；Format/Recipe/POV为空，尚无完整可复用组合 |
| 2 组合生成 | 账号与独立 Actor/Persona核对→preview→create→明确generate→回读 | plan ID及预期视频集合；组件完成与真实 Hook item；如目标含成片，当前version/revision对应产物完成 | 必须有合格账号/身份/素材；先确认测试内容不会被后台发布；生成可能调用付费服务，不能仅凭test工作区名称假设隔离 | 阻塞：has_actor筛选为0，plan preview报Actor缺失400；未创建计划或生成 |
| 3 精确账号资格 | 精确名单与平台/设备条件查询→eligibility | 返回集合与输入确定性比较；逐账号eligible/code；不混入近似账号 | 只读；至少一组能区分匹配与排除的样本 | 完整：分页读取92账号；exact预期/实际均1，排除不存在项；逐ID资格0可用并保留原因 |
| 4 排期异常诊断 | 选定视频/组/计划→读取阶段与readiness→解释卡点 | materialization/组件/render/publish事实；未知明确保留；不能把readiness当完成 | 只读；需要已有已知状态或可控合成测试对象；不触发重发 | 完整：已有视频approved、组件completed、render succeeded；无排期/发布任务，readiness明确Actor与时间缺失 |
| 5 阶段与归组阻碍 | 查询阶段/组/暖号参与→目标资格 | 当前状态、历史参与与占用/资格原因可区分 | 只验证诊断，不进行活跃账号迁移、跨工作区搬移或warmup重置 | 部分：账号/暖号可读，test-group与warmup为空；没有源/目标组样本验证迁移诊断 |
| 6 导入并分配Clip | media upload/get→batch-create/get→assign/get→需要时复查容量 | 媒体ID/type/status/workspace；逐client_key结果；needs_account登记态；分配后真实账号/版本 | 使用合成视频和明确测试账号；登记/分配可能使现有排期获得可用素材，必须确认不会被后台认领推动发布 | 失败：upload/get与登记/get通过；正确版本分配仍500，回读保持needs_account/账号空/版本未变 |
| 7 容量缺口 | 读取相同账号/日期/组合→capacity与preview→核对已知差异 | 账号级容量、content_gaps、clip_coverage；timeout/unknown不能为0 | 只读；不足与充足样本应可区分；不为凑通过率改真实规则 | 部分：capacity成功；组合preview被Actor缺失阻塞，未验证补货前后缺口变化 |
| 8 真机交付 | 精确日期/时区/账号查询→固定video IDs→export/get；分享则share/get | 集合ID完全匹配；每份export完成并对应video_version/render_revision；分享分页实际成员一致 | export可触发渲染；share创建公开访问能力且可能预热；只分享合成内容，不操作真机发布/mark-published | 阻塞：日期preview成功；未创建公开分享或触发导出/预热，没有交付成品闭环 |
| 9 效果追溯 | 真实campaign ID与窗口→dashboard→相关视频/素材 | 返回指标、可获得的新鲜度与关联ID；未回收不当0 | 只读；空看板可证明接口访问，不能证明排序/归因任务完成 | 部分：工作区/campaign核实；看板0内容且指标null，无可比较归因样本 |
| 10 保留产物的局部编辑 | 固定视频→before→版本化PATCH或bulk-schedule→after；需要成片再export/get | 字段目标成立、Hook item未变、版本与回执相符；时间按同一瞬间比较；新成片绑定新版本 | PATCH可能改变后台待发布内容；bulk-schedule可使后台认领，须证明无未授权发布可能；不模拟整组增量重排 | 部分：独立Actor草稿caption修改与版本冲突409均经真实CLI回读；未验证已有生成Hook item的保留及修改后的新成片 |

## 命令执行台账

执行方每个命令提供：环境已确认、请求类别、HTTP/业务结果、后置核验、阻塞原因。记录使用合成对象标签和聚合结果；不把凭据、公开访问token、原始工作区payload或个人账号写入此文。

| 命令 | 实际执行 | 成功/业务后置条件 | 备注 |
| --- | --- | --- | --- |
| hireaicreator.account-list | 已实际执行 | 接口成功；场景后置条件另列 | 精确名单/分页/至少一个主要筛选分别记录 |
| hireaicreator.account-eligibility | 已实际执行 | 接口成功；场景后置条件另列 | 需要真实目标组/账号样本 |
| hireaicreator.actor-list | 已实际执行 | 接口成功；场景后置条件另列 | Actor不等同Persona |
| hireaicreator.actor-get | 已实际执行 | 接口成功；场景后置条件另列 | 读取已确定Actor ID |
| hireaicreator.persona-list | 已实际执行 | 接口成功；场景后置条件另列 | v1 API |
| hireaicreator.persona-get | 已实际执行 | 接口成功；场景后置条件另列 | 按资源鉴权 |
| hireaicreator.format-list | 已实际执行 | 接口成功；场景后置条件另列 | 实际status枚举需契约对齐 |
| hireaicreator.format-get | 未执行 | 阻塞：工作区无Format对象 | 异步子资源状态 |
| hireaicreator.format-import-urls | 未执行 | 阻塞：未触发外部URL下载/解析任务 | 导入后get核验，不只202 |
| hireaicreator.hook-list | 已实际执行 | 接口成功；场景后置条件另列 | reference Hook身份 |
| hireaicreator.recipe-list | 已实际执行 | 接口成功；场景后置条件另列 | 查询样本 |
| hireaicreator.recipe-get | 未执行 | 阻塞：工作区无Recipe对象 | 步骤与资源事实 |
| hireaicreator.pov-list | 已实际执行 | 接口成功；场景后置条件另列 | 查询样本 |
| hireaicreator.bgm-list | 已实际执行 | 接口成功；场景后置条件另列 | 媒体及可用性 |
| hireaicreator.clip-list | 已实际执行 | 接口成功；场景后置条件另列 | 账号/状态筛选 |
| hireaicreator.clip-get | 已实际执行 | 接口成功；场景后置条件另列 | 版本与登记/归属事实 |
| hireaicreator.clip-batch-create | 已实际执行 | 1项成功/0错误；get证实源媒体及needs_account；后续分配失败 | client_key/mapping_version稳定 |
| hireaicreator.clip-assign-account | 已实际执行 | 失败500；错误/正确版本均未改变状态 | 分配后get |
| hireaicreator.video-list | 已实际执行 | 接口成功；场景后置条件另列 | 计划/账号/时间与分页 |
| hireaicreator.video-get | 已实际执行 | 接口成功；场景后置条件另列 | 组件/交付事实 |
| hireaicreator.video-readiness | 已实际执行 | 接口成功；场景后置条件另列 | 阶段资格，非完成 |
| hireaicreator.video-update | 已实际执行 | 新合成草稿caption目标成立，版本1→2；旧版本409且回读未变 | before→receipt→after；无生成/渲染/发布任务 |
| hireaicreator.video-generate | 未执行 | 阻塞：缺少合法新计划，且会启动外部生成 | 受理与最终组件完成分开 |
| hireaicreator.video-bulk-schedule | 未执行 | 阻塞：会产生可被后台认领的发布排期 | 需后台无外部副作用前置证明 |
| hireaicreator.plan-preview | 已实际执行 | 阻塞：账号未配置Actor | 真实组合与阻塞 |
| hireaicreator.plan-capacity | 已实际执行 | 接口成功；场景后置条件另列 | 有区分度样本 |
| hireaicreator.plan-create | 未执行 | 阻塞：目标账号均未绑定Actor，preview已拒绝 | get与video membership；start_generation显式 |
| hireaicreator.plan-get | 已实际执行 | 接口成功；场景后置条件另列 | 持久计划 |
| hireaicreator.test-plan-ensure | 已实际执行 | 两次同ID及目标workspace；不声称创建了新计划 | GET实际可能创建 |
| hireaicreator.test-group-list | 已实际执行 | 接口成功；场景后置条件另列 | 已知test plan ID |
| hireaicreator.test-group-get | 未执行 | 阻塞：工作区无Test Group对象 | 持久组 |
| hireaicreator.test-group-preview | 未执行 | 阻塞：工作区无Test Group对象 | 已有组驱动的预览 |
| hireaicreator.warmup-list | 已实际执行 | 接口成功；场景后置条件另列 | 只读策略 |
| hireaicreator.warmup-journeys | 已实际执行 | 接口成功；场景后置条件另列 | 参与与历史 |
| hireaicreator.dashboard-get | 已实际执行 | 接口成功；场景后置条件另列 | 有真实campaign ID |
| hireaicreator.delivery-preview | 已实际执行 | 接口成功；场景后置条件另列 | 只有统计 |
| hireaicreator.delivery-share | 未执行 | 阻塞：公开访问能力与预热副作用未执行 | 公开访问与预热副作用 |
| hireaicreator.delivery-get | 未执行 | 阻塞：未创建分享，无本轮可核验token | token读取，total/items分页 |
| hireaicreator.delivery-export | 未执行 | 阻塞：渲染/外部执行未启动 | 版本化导出 |
| hireaicreator.delivery-export-get | 未执行 | 阻塞：未创建导出，无本轮export ID | completed及产物链接 |

## 已有独立离线证据

- 独立执行 `uv run pytest -q tests/test_ai_hook_parameter_contract.py tests/test_ai_hook_skill_workflow.py tests/test_docs_sync.py`：190 passed。新skill再次通过skill-creator基础校验。190是检查结果，不是覆盖率。
- 当前40条命令的独立HTTP fixture覆盖JSON、args-file及flag入口，共120条实际parser→dispatch→HTTP MockTransport路径；期望method/path/query/body/header保存在独立fixture中，不从生产route builder反推。
- 按实际schema递归计数，嵌套叶子字段与原始值数组字段为272项，全部在独立请求中出现并核验最终HTTP值：**272/272（100%）声明参数传递覆盖**。这是已声明子集及所测值的覆盖，不是全部后端字段或所有值域组合覆盖。
- parser声明189个业务flag目标与90个本地控制目标。业务flag包含独立的非null `collection_id` share请求；null fixture不替代显式flag测试。本地控制包含40个args-json、40个args-file、10个dry-run；分别验证正常载入、来源互斥、dry-run不请求网络与先校验嵌套字段。
- 实际 `update-video-bgm.sh` 使用真实CLI parser/command_payload，在合成CLI响应上执行五种序列：正常修改、已满足、错误回读、版本漂移、写冲突。前两种成功且明确未验证新成片；后三种非零；写冲突后没有进入依赖阶段。这不是test workspace验证。
- 第一轮API映射审阅发现的Format status枚举、nullable enum公开schema与运行期不一致、integer maximum本地校验遗漏均已修正并复核。另纠正语义字段共用UUID导致的fixture盲点、Clip正常案例usage_limit=0不合法、AIHook字符串账号ID被旧全局UUID校验误拒、资源绑定接口错误贴默认workspace。零值仍有独立HTTP422案例证明未吞参数。

真实验收已发现delivery preview共用share输入schema过宽；已收窄为必需日期范围的video-filter，移除collection_id、rotate、video_ids，并真实重试成功。275个叶子参数因此减为272个；固定ID集合的设计要求仍是share后get核对，本轮未执行该分享链。

已有三个漏传mutation均被真实HTTP断言检出：丢失false筛选字段、丢失嵌套expected_version、丢失Idempotency-Key header。撤销mutation后正常检查通过。

## 真实失败与保留缺口

- `plan-preview`：服务返回400，当前所有工作区账号未绑定Actor。旧视频曾有完成产物，不代表其账号当前仍满足生成前置条件。没有跳过preview直接创建计划。
- `clip-assign-account`：新Clip的错误expected_version返回500（而不是预期冲突）；先GET确认未变，随后独立读取当前版本提交正确分配仍500，再GET确认账号为空、migration_state为needs_account、version未变。没有自动改版本重试、没有声称库存已可用。生产日志已定位为查询不存在的pool_accounts.expires_at（42703），发生在CAS前；本地修复与验证见下节，尚未部署或证明线上分配成功。
- 真实写入链还暴露了验收脚本误取上传receipt ID的问题。脚本停止后只读恢复唯一中性测试媒体ID，没有重复上传；skill现已明确upload的 `.data.asset.media_id` 与get的 `.data.asset.id` 不同。该问题不算产品CLI失败，也不隐藏恢复依赖了额外只读诊断。
- 已新增一份中性1秒测试视频媒体、一个仍needs_account的Clip及一条Actor模式隔离草稿；默认Test Plan的ensure可能复用了已有记录，未声称新建。没有配置Actor、迁组或构造可自动发布的状态。测试对象以本轮本地记录追踪，本文不包含私人ID或公开访问token。
- 未验证真实生成完成、版本化导出成品、公开集合成员回读、修改视频后的成品，以及活跃账号迁移/整组重排。后两项本来就不属于首版写入能力。

首轮执行方另报告全套498 tests、Ruff、文档/contract、wheel/archive/publicartifact和干净安装91命令检查通过；独立审阅直接复跑的范围与结果见上文。真实失败不能被这些离线检查抵消。后续需交付Clip查询修复，并用隔离本地账号绑定fixture推进计划与容量验证；真实生成与交付仍需相应外部执行条件。不必为此先引入新的工作流引擎或重写后端模型。


## 隔离草稿编辑补测

通过已有 `POST /api/v2/ai-hook-videos` 的Actor模式准备唯一合成fixture；这个创建动作不属于被测CLI命令，也不扩充40条命令分母。先分别读取Actor、Persona和ready Hook并核对工作区。创建只提供Actor/Persona/reference Hook、`composition_source=hook_only`、中性caption/POV、`include_bgm=false`，不提供账号、排期、计划或已生成Hook item。

执行前核对现有创建服务只持久化草稿；计划恢复要求生成请求，materialization要求planned与到期时间，render/publish候选要求scheduled或publishing及排期，生成恢复要求generating状态。该草稿始终pending且无上述触发条件，不会进入这些后台认领路径。

真实CLI执行 `video +get → video +update → video +get → video +readiness`：caption精确等于请求，expected_version=1成功后版本为2，receipt版本与readback相等。Actor、Persona、reference Hook、POV及其他核对字段不变；账号、排期、plan、render job、publish task均为空，Hook generation为not_started。另以旧expected_version=1提交不同caption得到HTTP409，随后GET证明仍为版本2且caption未改。

本次新增一个命令及三个参数生效断言。场景10仍记部分：ai_hook_item_id在修改前后均为空，不能把“空值未变”称为保留已有生成产物；未请求export，未验证新成片。脱敏阶段事实保存在本地验收记录，打包skill不含测试对象或工作区私有数据。

## Clip 500根因与本地修复证据

生产诊断证实错误为`42703 pool_accounts.expires_at does not exist`，发生在资格检查、分配CAS之前。expiry属于`workspace_ref_social_accounts_pool`：最小修复将单账号查询的expiry条件移到成员关系表，同时给批量资格查询补相同条件。此问题不是缺少数据库migration，修复没有改变Clip业务分配规则。

独立复核了仓库diff及`apps/api/tests/integration/test_content_clip_account_scope.py`。直接复跑为1 passed、1 skipped：真实Supabase SDK→PostgREST请求对schema快照列契约通过；本轮独立复跑未配置一次性数据库，因此跳过真实数据库分支。实现方和主线程另外验证了真实PostgreSQL16/PostgREST：成员关系未过期/已过期、跨工作区、账号/成员/Actor删除状态，以及两Clip错误版本时整体回滚、正确版本时均ready且version=2。其数据库fixture省略无关父表外键和trigger，证明范围为资格查询与分配事务，不冒充完整部署后的API验收。

修复尚未部署，表中`clip-assign-account`继续保留真实500与场景6失败。即使交付此修复，当前测试账号仍缺Actor绑定，应被业务资格拒绝，不能将本地合成账号分配成功计入真实工作区覆盖。

## 后续可执行的最小验证

- **账号、计划与容量**：在一次性本地PostgreSQL/PostgREST使用两账号（一合法、一缺Actor）及独立工作区隔离对照，建立真实账号成员关系、全局Actor绑定、工作区Persona绑定和可用Hook/Clip。通过现有路由、服务及repository验证preview、`start_generation=false`的单视频plan create、plan/video回读、充足/不足库存差异；外部派发端口被调用即失败。工作区已有Actor和Persona对象不能替代账号上的两个独立绑定，也不应为测试修改现有账号。
- **资源及交付读回**：使用本地合成Format/Recipe/TestGroup、固定video集合和已完成render事实验证读取、分页、版本与集合关联。此结果单列本地集成覆盖，不作为真实导入、分享预热或export完成。新建或调度真实发布账号仍不可作为测试捷径。
- **真实外部执行**：生成、URL解析导入、export/预热、公开分享及bulk-schedule分别需要对应前置条件；bulk-schedule可能触发后台发布。当前没有执行这些步骤，不能用dry-run、空列表或本地产物fixture替代真实成功证据。


## 本地计划与发布容量补测

本轮使用一次性PostgreSQL16/PostgREST12.2.3，实际链路为CLI parser/dispatch → HTTP ASGI transport → 现有API路由 → 真实service/repository → 数据库。4条不同命令（`plan-preview`、`plan-create`、`plan-get`、`plan-capacity`）执行14个HTTP请求；本次局部集成覆盖为4/40（10%），不是全部离线验证覆盖率，也不加入上方真实工作区28/40、26/40和36/272的分子。

| 阶段 | 合成输入与独立事实 | 本地结果 |
| --- | --- | --- |
| 账号与预览 | A有有效工作区成员关系、Actor绑定及独立Persona绑定；B缺Actor；C只属于另一个工作区 | A分配恰好1项，账号/Actor/Persona/Hook均精确匹配；B/C的preview及create分别HTTP400，数据库plan/video数量仍为0 |
| 调用者工作区边界 | 注入的Access依赖拒绝其他工作区 | 路由返回403且无写；这只验证错误映射，调用者认证与Access依赖已注入，不能算真实API Key权限验证 |
| 创建及回读 | 新幂等键、hook_only、fixed_count=1、start_generation=false、无排期 | 创建201，GET与SQL证实唯一plan及1个child，工作区/身份/Hook一致，pending、version=1；无生成请求/派发时间、materialize、Hook item、render或publish task |
| 幂等与恢复候选 | 重放完全相同请求；同key更改name；读取后台候选 | 重放仍为同plan且1个child；更改name返回409且无新增；计划生成恢复、stale generating及due planned候选均为空 |
| 发布容量 | 每账号每日上限2；无排期创建前后；随后仅本地增加2个pending且有未来排期的占位记录 | 无排期创建前后容量完全相等，总余量4；占位后A占用2/余0，B余2，总余2；exclude其中一个video后总余3 |

容量验证调用当前schema快照中的`fn_ai_hook_video_capacity`，衡量每日发布槽，不衡量Actor资格或Clip库存。pending但有排期也会计入容量；本地没有运行scheduler或worker。该脚本没有Clip组合，因此不证明Clip分配或库存不足分支。Clip组合的create即使start_generation=false也会分配Clip slots，不能从本次hook_only结果推断无库存写入。

外部边界采用调用即失败的替身：路由生成依赖，以及生成batch、文案batch和CloudTasks派发；渲染/其他未使用依赖同样不可调用。最终记录外部调用为0。独立审阅还通过只读SQL和PostgREST确认最终1个无生成意图的plan、1个plan child及1个容量占位clone；两视频均pending/not_started且无render/publish任务，plan与child工作区一致，容量RPC的A占用2/余0与记录相符。

本轮fixture沿用当前表的完整列/default/CHECK、相关unique索引及图内外键，省略外部父表外键与非本路径trigger。它不是完整数据库部署回放，也没有真实API Key握手、生成、渲染、发布或计费验证。脚本和脱敏结果保存在本地验收记录；没有新增测试框架、CLI命令或线上测试账号。真实十场景分类保持完整2、部分5、失败1、阻塞2。

## 第二轮共享样本补验（2026-09-12）

本节记录执行单要求的剩余场景，并覆盖上文“后续可执行的最小验证”的旧状态。线上候选使用普通API Key经本地候选API读取生产数据库；隔离集成使用一次性PostgreSQL16/PostgREST12.2.3。两层结果始终分开，隔离成功不增加真实工作区的28/40命令、26/40正向成功、36/272参数或2/10完整场景分子。

### 真实工作区只读复核

通过普通CLI配置和本地候选API逐项读取素材库存：Hook 100项且100项ready，BGM 100项且100项ready，Format、Recipe、POV均为0项，warmup为0项。空集合只证明接口可访问；场景1仍缺可供筛选和逐项GET的Format/Recipe/POV组合，场景5仍缺源组、目标组及暖号参与样本。没有为了补覆盖修改既有账号绑定、operation stage、profile或组归属。

### 隔离数据库补验

| 场景 | 执行边界 | 结果 |
| --- | --- | --- |
| 2 组合生成 | 复用本地计划链：真实CLI路由、service、repository和PostgreSQL；A合法、B缺Actor、C跨工作区；`start_generation=false` | preview分配唯一资源；create仅产生唯一plan和1个child；重放同ID，同key改name返回409；B/C拒绝且无写。未显式generate，child无Hook item，故仍为部分 |
| 5 阶段与归组阻碍 | 真实PostgreSQL执行测试组窗口、运行快照、释放和时区冲突函数 | 3项选定集成检查通过：次日分配忽略当日已结束窗口且保留快照；删除成员不释放已运行占用、取消运行后释放；不同时区按真实瞬间识别相邻日冲突。证明组占用诊断内核，未经过CLI命令，仍为部分 |
| 6 Clip分配 | 真实PostgreSQL/PostgREST执行成员、Actor、expiry、跨工作区及CAS分配 | 合法两Clip原子分配为ready/version=2；错误版本整体不变；过期、inactive、deleted、缺Actor及跨工作区拒绝。生产候选修复未部署，真实工作区场景仍保留原500，隔离层为部分而非线上完成 |
| 7 容量缺口 | 真实CLI→API→service→repository→容量RPC；固定账号、日期、时区和exclude | 创建无排期plan前后容量不变；增加2个仅本地排期占位后A余0、B余2、总余2；exclude一个后总余3。发布槽容量闭环完成；未把它当作Clip库存证明 |
| 9 效果追溯 | 真实PostgreSQL应用当前dashboard迁移，建立有值和null表现样本，直接调用`fn_ai_hook_campaign_dashboard_v3`并经响应模型解析 | 1项集成检查通过；`views_desc`、`views_asc`均按独立排序且null始终最后，accounts/posts分区可读、指定content关联存在。线上看板仍为空，因此只算隔离读模型完成 |
| 10 局部编辑 | 复用隔离草稿及版本冲突证据 | caption版本1→2、回读一致、旧版本409且状态不变；修改前后Hook item为空，不能证明保留生成产物，仍为部分 |
| 8 真机交付 | 没有构造公开share或真实发布；独立媒体任务的PNG/MP4不替代AI Hook组合成片 | 未取得绑定目标video_version/render_revision的AI Hook export文件，仍阻塞 |

隔离环境第一阶段结果为：计划/容量脚本14个HTTP全部通过；Clip集成2项通过；测试组窗口3项通过；dashboard排序1项通过。它们分别验证相应业务契约，不把pytest数量换算为CLI覆盖。第一阶段隔离CLI为4/40，声明叶子25/272；后续已扩展为同一对象图的12/40和74/272，见文末“单一隔离CLI正向链补验”。

### 当前两层结论与剩余条件

真实工作区分类保持完整2、部分5、失败1、阻塞2：第二轮只读没有非空Format/Recipe/POV、测试组、暖号或表现样本，隔离结果不能改变该统计。隔离补验新增场景7容量完整、场景9读模型计算完整；场景2/5/6/10各完成核心数据库或版本分支但缺完整CLI正向链，场景1缺完整资源组合，场景8缺AI Hook export成品。

要完成6→2→10→8的线上正向链，最小缺失条件是一个专用合成发布账号，具有有效工作区成员关系、Actor及独立Persona绑定，并明确不会被后台发布流程认领；随后需用已修复候选API完成Clip合法分配，显式生成一个AI Hook item，编辑后核对Hook item与新version/revision，再导出并读取同版本文件。当前授权明确禁止改既有账号profile/绑定和真实发布，因此本轮没有用业务账号补造这个条件。场景1另需非空Format/Recipe/POV测试资源；场景5另需可控源组/目标组及暖号参与记录；场景9线上归因另需AI Hook Test工作区自然产生的非空表现事实。上述条件均不能由空列表、隔离fixture或独立Media生成任务替代。

## 单一隔离CLI正向链补验

在同一个一次性PostgreSQL16/PostgREST12.2.3数据库中建立工作区、合法账号A、缺Actor账号B、跨工作区账号C、独立Actor/Persona，以及同一批Format、Hook、Recipe、POV、Media和Clip关系。执行使用真实CLI parser/dispatch、ASGI路由、现有application service、Supabase/PostgREST repository和SQL事务；只有调用者认证、workspace access及campaign Product读取使用本地固定fixture，所有外部生成、Cloud Tasks、render和publish端口保持调用即失败。

本次实际执行23个HTTP请求，覆盖12/40条不同CLI命令、74/272个`命令+字段路径`声明叶子。资源链通过`format-list/get`、`pov-list`、`recipe-list/get`验证有区分度的search/status/tag筛选及精确ID回读；随后同一个Media记录经`clip-batch-create/get/assign-account/get`从needs_account/version=1变为ready/version=2，来源Media、账号A和标签保持一致。该Media是隔离数据库中的completed upload fixture，本进程没有再次执行媒体上传传输，因此不把upload步骤记为完整。

计划链使用上述同一账号A、Hook、POV和Clip。`plan-preview`返回唯一分配；`plan-create(start_generation=false)`和`plan-get`产生唯一plan及child；SQL回读证明child的Actor、Persona、Hook及POV文本一致，唯一Clip slot引用前述Clip与Media，claim_status为reserved。相同幂等键重放仍为同plan，同键改name返回409且无新增；B缺Actor、C跨工作区及调用者跨workspace分别拒绝且无写。脱敏证据位于`/tmp/aihook-local-plan-results.json`。

这条链将场景1的Format/Recipe/POV非空筛选、场景6的Clip注册/分配，以及场景2的非收费preview/create/get串到同一对象图中。场景1仍未在隔离层补BGM精确选择，场景6仍缺本进程的真实media upload传输，场景2仍缺显式generate及最终Hook item，因此三者仍按部分记录。

生成与版本化export不能直接接到当前隔离进程：`video-generate`依赖`get_ai_hook_video_generation_service`，真实服务生成后通过`CloudTasksClient.enqueue_handler_async`持续poll；当前8150容器绑定生产数据库，其loopback回调不能更新本隔离数据库。`delivery-export`要求已ready的AI Hook item，并通过`AiHookExportService`建立GCS目标后调用`RenderSubmissionService.submit`，最终完成依赖render worker回写同一数据库。把回调发往8150会跨到生产库；仅在隔离库伪造Hook item/render完成或替换这些端口不能证明真实生成和导出。为保持同一对象链和不改生产配置，本轮在收费与render阶段停止，没有把独立Media生成结果充当AI Hook export。

## 同一对象图的实际上传、生成与编辑续验（2026-09-12）

本节覆盖上文“Media 是 fixture”和“外部生成端口保持调用即失败”的旧状态。独立 API runtime 通过两条预检后才继续写入：SQLAlchemy 指向一次性 `hook_plan` PostgreSQL，Supabase/PostgREST 指向同库；两条通道均能读取唯一合成 workspace 和后续 Media。生产库只读核对该 workspace、plan、video 及新 Media 均为0条，未发现早期DSN优先级问题造成的生产写入。

真实 CLI `media +upload` 上传仓库内117803字节MP4，receipt的Media ID经 `media +get` 回读为completed、video及同一workspace；从GCS读取对象后的SHA-256与本地源文件完全相同。随后 `clip +batch-create → +get → +assign-account → +get` 在同一Media上创建新Clip，从needs_account/version=1变为目标账号/version=2，来源Media不变。新plan的 `plan +preview → +create(start_generation=false) → +get` 使用同一账号、Actor、Persona、POV、Hook和Clip；SQL证明唯一child slot引用同一Clip/Media且claim_status=reserved。该Clip被预留后再次preview准确返回HTTP409 `CLIP_UNAVAILABLE`和position=1，补足场景7的Clip库存不足分支；preview没有新增记录。

在双通道隔离门禁、任务回调指向同库且render目标为空后，真实CLI对该child执行 `video +generate`。初次恢复发现隔离fixture缺当前generation/copy表及后续列；补齐的均为仓库现有migration/schema契约，不是产品DDL。完整public ready Hook及其source/first-frame Media从生产只读并在内存复制到隔离库，video再经CLI版本化PATCH绑定该Hook；Actor和Persona使用本轮真实CLI上传PNG作为look-reference。最终生成进入真实AI Hook batch，生成完成一张864x1536 JPEG first frame并持久化为completed Media（121385字节，GCS完整读取，SHA-256为`9aad3a3a2709f204178fa797b1a94c847248a2db3e5e2bf90959f02c98f78e0f`），随后在视频阶段失败。安全错误为本机ADC没有可用于签名的service account identity；当前身份对目标service account没有`iam.serviceAccounts.signBlob`。失败发生在Kling request创建前，provider request ID和结果视频Media均为空。没有为此改IAM、创建key、公开对象或重复提交供应商视频。

同一video在生成失败后已有持久AI Hook item引用。真实CLI执行caption PATCH并回读：version 19→20，AI Hook item ID保持不变；用旧version 19再次PATCH返回409，最终version和caption保持20及首次输入。它完成场景10的“保留Hook item、局部编辑、旧版本拒绝”契约；由于没有result video，不能继续把export/get或成品解码记为通过。

这轮在前述同一对象图12/40、74/272基础上新增3条HireAICreator命令（`video-generate/get/update`）及7个首次覆盖的HireAICreator命令字段路径，因此隔离CLI累计为**15/40、81/272**。同一链另执行了独立`media`域的`upload/get`及4个字段；它们只作为场景6的跨域前置证据，不加入HireAICreator分子。这仍是隔离层实际HTTP覆盖，不增加真实工作区28/40、26/40和36/272的分子。

更新后的隔离场景结论：场景1的Format/Recipe/POV筛选与精确读取已完成但BGM组合未接入同一plan；场景2完成同对象preview/create/generate和真实first-frame产物，但结果视频受签名权限阻塞；场景6完成实际文件传输、Media回读/hash、Clip登记/分配/回读；场景7同时覆盖发布容量和Clip充足→预留后不足；场景10完成已有Hook item的版本化编辑和冲突保护；场景8因同一video没有结果视频，不能创建有意义的版本化export。解除2/8的最小外部条件是让隔离runtime具备对目标service account的`iam.serviceAccounts.signBlob`，或在已有可签名service-account runtime中执行同一隔离回调链。该权限需要管理员显式施加，本轮没有授权。

CLI发布门槛仍未满足：Media→Clip→plan→generation受理、真实first-frame生成和Hook item保留编辑已经跑通；AI Hook结果视频、对应video_version/render_revision的export、成品下载hash/解码尚未通过。候选还依赖尚未上线的后端Clip查询修复、媒体失败诊断及默认模型credits变更。发布前应在这些后端依赖可用且签名能力满足后完成同一video的生成终态与export/get，再运行双仓版本同步、构建/安装、契约检查和适用CI；不得把本节隔离部分结果当成已部署线上能力。

## 生成与版本化导出最终续验

本节覆盖上一节把`signBlob`列为当前2/8阻塞及“发布门槛尚未满足”的结论。产品GCS signed URL路径仍未验证或修复；本轮隔离验收改用已有Fal素材上传能力，把同一AI Hook item已完成的首帧以供应商可读取的Fal CDN输入恢复到`video_submit`。该适配没有新建video或AI Hook item，也没有重复图片生成。Kling任务真实完成，原item和batch均为completed，result video Media持久化到同一隔离数据库。随后用既有poll payload收敛同一video：四个生成组件均completed，状态approved，AI Hook item引用保持不变。

收敛后再次经真实CLI执行局部caption编辑：video version 24→25，AI Hook item不变；旧version 24写入返回409，回读证明caption和version未被覆盖。caption是发布字段而非render composition字段，因此render_revision按现有领域契约保持2；后续export准确绑定`video_version=25`与`render_revision=2`。

真实CLI仅提交一次`delivery +export`，export ID为确定性目标Media ID；独立render-service执行实际FFmpeg并经callback写回同一隔离库。render batch和job均succeeded，job attempt_count=1，export Media completed。`delivery +export-get`回读status=completed、video ID、video_version=25、render_revision=2及original Hook resolution均与请求一致。下载文件为2,156,918字节，SHA-256为`3c8cee9e510959d98b41f2876284973c8ab7ca9783d3a4433a31d7c96465df1a`；`ffprobe`确认H.264/AAC、720x1280、5.609667秒，`ffmpeg -f null`完整解码成功。

本机ADC仍不能生成产品signed URL。为验证CLI的完整get/download消费者链，隔离adapter只对该唯一export ID和精确GCS path返回localhost下载路由，并用现有ADC私有读取；没有改产品签名代码、IAM或GCS ACL，其他path仍走原签名逻辑。因此上述成品/render事实有效，但不能声称生产GCS signed URL路径已通过。

新增`delivery-export`和`delivery-export-get`后，同一隔离对象图累计为**17/40条不同HireAICreator命令、84/272个HireAICreator命令字段路径**；独立`media`域的2条命令和4个字段不计入该分子。场景2的组合生成及最终Hook item、场景6的upload→Media→Clip分配、场景7的容量与Clip库存差异、场景8的版本化export/get/下载成品、场景10的生成产物保留编辑在隔离层均完成。结合前述隔离读模型证据，场景9在隔离层完成但没有形成HireAICreator CLI命令覆盖；场景1和5为部分，场景3和4未在隔离层执行。最终隔离分类为完整6、部分2、未执行2。真实工作区统计仍保持28/40执行、26/40正向成功、36/272参数，以及2完整/5部分/1失败/2阻塞；隔离结果不得计入已部署线上分子。

CLI发布验收的目标链现已跑通，但发布仍依赖候选后端变更先按仓库流程交付：Clip资格查询修复、媒体供应商安全失败诊断、默认模型credits及Flare PNG参数修复。最终发布检查应包括双仓版本同步、CLI构建与干净安装、命令/参数契约、相关API测试和全部适用CI。生产GCS签名能力应作为独立上线验收项保留，不能用本地下载适配替代。
