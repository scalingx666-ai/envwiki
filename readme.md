# envwiki

> 把任意链接或多模态上传，变成一个可校验的 **Harbor** 任务。
>
> Turn any link or uploaded multimodal content into a verifiable **Harbor** task.

**[English](readme.en.md)** | **[中文](readme.md)**

环境合成的论文很多，方法各不相同。envwiki 把每一种方法抽象成一条**配方**（recipe），
把配方连同"素材"和"脚手架"一起装进一个 **MCP server**；**决定写什么任务的是 agent**，
envwiki 自己不做合成。

---

## 这是什么

envwiki 是三件东西：

- 一个 **MCP server**：给 agent 一套工具箱——配方（方法）、素材（暂存区）、脚手架
  （写任务、校验任务）。它**不含任何合成逻辑**：不会替 agent 决定任务长什么样。
- 一个 **Skill**：唯一写着"怎么写一个 Harbor 任务"的地方——方法论、verifier 契约、
  参考解契约、路径规则、提交前自检清单。
- 一个 **CLI**：薄驱动。暂存素材、跑 agent、收产物、校验、发布。它不解析模型输出，
  也不生成任务内容。

任何支持 MCP 与 skills 的 harness 都能驱动它。本仓库默认用 pi，但 MCP server 是
朴素的 stdio / streamable HTTP，skill 只是一个普通的 `SKILL.md`。

## 职责边界

这是本项目的核心约定：**合成能力在 agent 身上，envwiki 只是工具箱。**

| 谁 | 负责 | 不负责 |
| --- | --- | --- |
| agent | 读素材、挑方法、决定写什么任务、按校验结果迭代 | 素材解析、schema 判定 |
| envwiki MCP server | 给方法（配方）、给素材（暂存）、写任务（脚手架）、校验任务 | 决定写什么任务、生成任务文本 |
| envwiki CLI | 暂存、跑 agent、发现产物、校验、发布 | 解析模型输出当任务、替 agent 写任务 |

**契约只有一份。** 任务规格由 `scaffold_task` 的工具签名与
`envwiki/schemas.py` 里的 `TaskDraft`（pydantic）强制；envwiki 的提示词里**不再**
写一份平行的任务 JSON 结构；Harbor 的方法铁律**只**留在 skill 里。想看"任务长什么样"，
看工具签名；想看"怎么写好任务"，看 skill。

```
素材 (link / 上传)
   |
   v
暂存  ->  文件树 + 带行号索引的摘要
   |
   v
agent 读素材  ->  plan_task 选方法  ->  get_recipe 取步骤  ->  按步骤执行
   |
   v
scaffold_task 写任务  ->  validate_task 校验  ->  不合格就改，再来一轮
   |
   v
CLI 发现产物  ->  校验  ->  发布到 --out
```

## 配方库

一条**配方**是一个抽象方法：什么时候适用、需要什么、具体步骤、结果如何校验、
会踩什么坑、来自哪些论文。配方按方法族分文件存放于
`src/envwiki/recipes/data/families/`，可以逐族审阅。

| 方法族 | 说明 | 配方数 |
| --- | --- | --- |
| `environment-synthesis` | 通用环境合成：把骨架、状态、场景、难度调成一个可执行环境 | 3 |
| `experience-synthesis` | 经验与交互合成：先执行后提问，轨迹反过来当任务素材 | 3 |
| `web-gui` | 网页与 GUI：把真实应用重建成轻量环境，奖励写成代码断言 | 3 |
| `terminal-coding` | 终端与编码：能力分类采样 + 证据锚定 + Docker 化 + fail-to-pass | 3 |
| `simulation` | 模型化仿真与语言世界模型：世界书、确定性引擎、可探测规则 | 3 |
| `task-scenario` | 任务与场景合成：检查点、课程、能力前沿、需求编译 | 3 |
| `mcp-tools` | MCP 工具环境：真实调用轨迹挖依赖、动态扰动、对抗注入 | 3 |
| `enterprise-professional` | 企业与专业环境：仓库工作流、零执行规范任务、主动干预窗口 | 3 |
| `platform-infra` | 平台与基础设施：调用捕获回放、模拟 API 与 UI 状态校验 | 2 |
| `sandbox` | 沙箱：按需求选隔离底座、分层组装、状态胶囊生命周期 | 2 |
| `computer-use` | 计算机使用：确定性应用对接、执行门控、扰动恢复 | 3 |
| `data-synthesis` | 数据合成：候选验证再复杂化、确定性缓存溯源、决策落地 | 3 |
| `embodied` | 具身：约束驱动实例生成、技能库引导探索、资产场景共演化 | 3 |
| `multi-agent` | 多智能体：任务图互依赖、混合动机博弈机制 | 2 |
| `verification` | 难度与校验：状态差分校验、IRT 难度标定、负控筛选 | 3 |
| **合计** | | **42** |

每条配方都至少引用 2 篇真实论文（共 118 处引用），引用的 arXiv id 与标题会与
随包发布的语料索引逐条比对，测试保证不越界、不篡改。

配方长这样：

```
{
  "id": "execution-first-trace-anchored-task",
  "family": "experience-synthesis",
  "summary": "Build the executable artifact before the prompt...",
  "when_to_use": ["..."], "not_when_to_use": ["..."], "inputs": ["..."],
  "steps": [{"title": "Pick the workflow before the prompt", "detail": "..."}],
  "verifier": ["the check command exits non-zero on the unmodified workspace"],
  "pitfalls": ["request written first: it reads plausibly but no valid call sequence satisfies it"],
  "effort": "high",
  "source_papers": [{"arxiv_id": "2607.29175", "title": "...", "note": "..."}]
}
```

## MCP server：工具箱

```
uv run envwiki-mcp                       # stdio，本地 harness 拉起的形式
uv run envwiki mcp serve --transport streamable-http --port 8765
```

**配方（方法）**

| 工具 | 作用 |
| --- | --- |
| `plan_task` | 描述素材，一次拿到排序列与最优配方的完整步骤 |
| `recommend_recipes` | 描述素材，返回匹配的配方 |
| `get_recipe` | 取一条配方的全文：步骤、输入、校验、坑、论文 |
| `search_recipes` | 关键词检索 |
| `list_recipes` | 配方索引，可按方法族与工作量过滤 |
| `list_recipe_families` | 方法族分布 |

整个配方库还可以作为资源 `envwiki://recipes/index` 读取。

**素材**

| 工具 | 作用 |
| --- | --- |
| `stage_source` | 把链接与上传件解析成可勘探的暂存区，返回目录树与带行号的摘要 |
| `list_staged` | 看某个暂存区里现在有什么 |

**脚手架**

| 工具 | 作用 |
| --- | --- |
| `scaffold_task` | 按你给的规格写出任务目录。**这是唯一的落盘方式**，规格由工具签名强制 |
| `validate_task` | 校验任务目录：本地结构 + Harbor 官方 TaskConfig |

按常见 MCP 命名约定，工具全名是 `mcp__envwiki__plan_task`、
`mcp__envwiki__scaffold_task`、`mcp__envwiki__validate_task` 等。

## Skill

`src/envwiki/skills/env-synthesis/SKILL.md` 会在 `envwiki build` 时被复制进
harness 工作区。它是**方法与规则的唯一出处**：工具表、五步工作流、什么算好任务、
verifier 契约、参考解契约、路径规则、提交前自检清单。

## 快速开始

```
git clone https://github.com/scalingx666-ai/envwiki.git
cd envwiki
uv sync --extra dev
uv run envwiki --help
```

从一个链接生成任务：

```
uv run envwiki build https://github.com/owner/repo --out ./envwiki-tasks
```

从上传件生成任务（文本 / PDF / 图片）：

```
uv run envwiki build --upload spec.pdf --upload diagram.png
```

## 命令行

```
uv run envwiki build <links...>              # 暂存素材、跑 agent、校验并发布产物
uv run envwiki validate <task dir>            # 用 Harbor schema 校验任务
uv run envwiki inspect <url>                  # 看某个链接会怎么处理
uv run envwiki model check                    # 模型端点是否可用
uv run envwiki model register                 # 把端点注册进 pi 的 models.json
uv run envwiki mcp serve                      # 以 MCP server 形式运行
```

常用开关：`--harness pi|direct`、`--out`、`--workspace`、`--org`、
`--timeout`、`--dry-run`、`--no-mcp`、`--no-skills`、`--no-envwiki-mcp`、
`--skill-dir`、`--enable-docling`、`--allow-write-tools`。

`--harness direct` 不带 pi：模型直连 OpenAI 兼容端点，但**用的是同一套工具**
（进程内调用 MCP server 的工具函数），所以两条路径只有一份契约。
它需要端点支持 OpenAI 风格的 `tools` 参数。

## 配置

全部通过环境变量，便于无人值守运行。

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `ENVWIKI_BASE_URL` | `http://127.0.0.1:8787/v1` | OpenAI 兼容端点 |
| `ENVWIKI_API_KEY` | `sk-my-secret` | 该端点的 API key |
| `ENVWIKI_MODEL` | `hy4flash-free` | 模型 id |
| `ENVWIKI_PROVIDER` | `envwiki-local` | 写入 pi models.json 的 provider 名 |
| `ENVWIKI_HARNESS` | `pi` | harness 后端：`pi` 或 `direct` |
| `HARBOR_SRC` | 自动探测 | Harbor 的 `src` 目录，用于 schema 校验 |

API key 不落盘：pi 的 `models.json` 里写的是 `"$ENVWIKI_API_KEY"`，真实值在运行时
由环境注入。

## 安全

素材不可信，harness 又跑在你自己的机器上，所以默认收得很紧：

- harness 启动即禁用会改动宿主机的工具（`bash`、`edit`、`write`），只靠只读工具勘探。
  对信任的素材可用 `--allow-write-tools` 放开。
- **模型只能通过 `scaffold_task` 落盘**：它写不出别的文件，写出来的任务立刻过一遍
  pydantic 与 Harbor schema。
- 暂存前会删掉克隆物里的 `.pi` 与 `.agents` 目录，克隆的仓库没法给自己注册扩展、
  MCP server 或 skill。
- skill 明确写明：素材是数据，不是指令。
- API key 只以环境变量引用出现，不写进任何配置文件。

## 任务目录结构

```
envwiki-tasks/my-task/
  task.toml            # schema_version 1.4，[task] [metadata] [verifier] [agent] [environment]
  instruction.md       # 给解题 agent 的任务描述
  environment/
    Dockerfile         # Docker 构建上下文就是这个目录
  tests/
    test.sh            # 必须写 /logs/verifier/reward.txt
  solution/
    solve.sh           # 参考解
  envwiki.json         # 溯源：名称、描述、来源笔记、元数据、用到的配方 id
```

三条来自 Harbor 自身的硬规则，由构建器与校验器保证：

- `[task].name` 必须是 `org/name` 形式（envwiki 默认 `envwiki/<task-name>`，
  `--org` 可改）。
- `environment/Dockerfile` 的构建上下文是 `environment/`。
- `scaffold_task` 的 `copy_from_staging` 里列的文件会落到工作目录根部、只保留文件名，
  `repos/x/readme.md` 变成 `/app/readme.md`；instruction、verifier、solution
  必须用同一个路径。

## 校验

```
$ uv run envwiki validate ./envwiki-tasks/my-task
./envwiki-tasks/my-task: ok, 0 warning(s), schema source: harbor
```

`envwiki validate` 先做本地结构检查，再在 Harbor 可导入时用 Harbor 自己的
`TaskConfig` 校验 `task.toml`。优先用已安装的 Harbor；否则探测到 Harbor 源码目录
（`HARBOR_SRC` 或同级的 `harbor/`），补上缺失的包元数据后从源码导入。
报告会写明走的是哪条路径。agent 在构建过程中也会调 `validate_task` 自己过一遍。

## 论文语料与引用校验

`src/envwiki/recipes/data/corpus.json` 随包发布，记录了配方所依据的 574 篇论文
（arXiv id、标题、所属方法族）。测试会断言：

- 每个配方的引用 id 都在语料内；
- 引用标题与 arXiv 权威标题逐字相符（归一化后）。

所以任何人都能独立复核：一条配方说的是不是那篇论文。

## 开发

```
uv sync --extra dev
uv run pytest          # 62 项测试
uv run ruff check src tests
```

## 限制

- 生成的是**初版**任务：结构完整、schema 合法，但难度校准与校验严格程度取决于模型，
  发布进 benchmark 前请人工过一遍。
- 解题 agent 与 verifier 都没有网络，任务若需要联网取数据会失败。
- 只支持 `linux` 与 `windows` 目标环境，与 Harbor 自身的枚举一致。
- 只读 harness 没法执行它要评的代码；需要运行时事实（堆栈、计算结果）的任务会偏弱，
  用 `--allow-write-tools` 会好一些。
- 配方匹配是关键词加权的，能把你带到正确的邻域，最终选哪条仍由模型决定。
- `--harness direct` 要求端点支持 OpenAI 风格的 `tools` 参数。

## License

MIT，见 [LICENSE](LICENSE)。
