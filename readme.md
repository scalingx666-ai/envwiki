# envwiki

> 把任意链接或多模态上传，解析成初版 **Harbor** 任务。
>
> Turn any link or uploaded multimodal content into an initial **Harbor** task.

**[English](readme.en.md)** | **[中文](readme.md)**

环境合成的论文很多，方法各不相同。envwiki 把每一种方法抽象成一条**配方**（recipe），把配方装进一个 **MCP server** 和一个 **Skill**，然后交给任意 agent harness 调用。

There are many ways to synthesise an environment. envwiki abstracts each of them into a **recipe**, serves the recipes through an **MCP server** and a **Skill**, and lets any agent harness call them.

---

## 这是什么

envwiki 有两张面孔：

- 一个 **MCP server**：对外提供环境与任务合成**配方库**。每条配方都是从描述该方法的论文里提炼出来的抽象方法。
- 一个 **Skill**：教 agent harness 怎么为手上的素材挑一条配方、然后把它执行成一个可确定性校验的 Harbor 任务。

任何支持 MCP 与 skills 的 harness 都能驱动它。本仓库默认用 pi，但 MCP server 是朴素的 stdio / streamable HTTP，skill 只是一个普通的 `SKILL.md`。

```
素材 (link / 上传)
   |
   v
分类  ->  GitHub 浅 clone / 普通 URL 走 reader / 上传件抽取文本
   |
   v
暂存  ->  文件树 + 带行号索引的摘要
   |
   v
harness 读素材  ->  问 MCP: 哪个配方合适?  ->  按配方执行  ->  任务 JSON
   |
   v
构建  ->  Harbor 任务目录
   |
   v
校验  ->  Harbor 官方 TaskConfig
```

## 配方库

一条**配方**是一个抽象方法：什么时候适用、需要什么、具体步骤、结果如何校验、会踩什么坑、来自哪些论文。配方按方法族分文件存放于 `src/envwiki/recipes/data/families/`，可以逐族审阅。

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

每条配方都至少引用 2 篇真实论文（共 118 处引用），引用的 arXiv id 与标题会与随包发布的语料索引逐条比对，测试保证不越界、不篡改。

配方长这样：

```json
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

## MCP server

```bash
uv run envwiki-mcp                       # stdio，本地 harness 拉起的形式
uv run envwiki mcp serve --transport streamable-http --port 8765
```

| 工具 | 作用 |
| --- | --- |
| `plan_task` | 描述素材，一次拿到排序列与最优配方的完整步骤 |
| `recommend_recipes` | 描述素材，返回匹配的配方 |
| `get_recipe` | 取一条配方的全文：步骤、输入、校验、坑、论文 |
| `search_recipes` | 关键词检索 |
| `list_recipes` | 配方索引，可按方法族与工作量过滤 |
| `list_recipe_families` | 方法族分布 |

整个配方库还可以作为资源 `envwiki://recipes/index` 读取。

按常见 MCP 命名约定，工具全名为 `mcp__envwiki__plan_task`、`mcp__envwiki__recommend_recipes`、`mcp__envwiki__get_recipe`、`mcp__envwiki__search_recipes`、`mcp__envwiki__list_recipes`、`mcp__envwiki__list_recipe_families`。

## Skill

`src/envwiki/skills/env-synthesis/SKILL.md` 会在 `envwiki build` 时被复制进 harness 工作区。它要求模型：先写一段素材画像 -> 调 `mcp__envwiki__plan_task` -> 调 `mcp__envwiki__get_recipe` -> 按步骤执行；同时写死 Harbor 的铁律：reward 文件、fail-to-pass、离线执行、路径一致。

## 快速开始

```bash
git clone https://github.com/scalingx666-ai/envwiki.git
cd envwiki
uv sync --extra dev
uv run envwiki --help
```

从一个链接生成任务：

```bash
uv run envwiki build https://github.com/owner/repo --out ./envwiki-tasks
```

从上传件生成任务（文本 / PDF / 图片）：

```bash
uv run envwiki build --upload spec.pdf --upload diagram.png
```

## 命令行

```bash
uv run envwiki build <links...>              # 解析素材并合成任务
uv run envwiki validate <task dir>            # 用 Harbor schema 校验任务
uv run envwiki inspect <url>                  # 看某个链接会怎么处理
uv run envwiki model check                    # 模型端点是否可用
uv run envwiki model register                 # 把端点注册进 pi 的 models.json
uv run envwiki mcp serve                      # 以 MCP server 形式运行
```

常用开关：`--harness pi|direct`、`--out`、`--workspace`、`--timeout`、`--dry-run`、`--no-mcp`、`--no-skills`、`--no-envwiki-mcp`、`--skill-dir`、`--enable-docling`、`--allow-write-tools`。

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

API key 不落盘：pi 的 `models.json` 里写的是 `"$ENVWIKI_API_KEY"`，真实值在运行时由环境注入。

## 安全

素材不可信，harness 又跑在你自己的机器上，所以默认收得很紧：

- harness 启动即禁用会改动宿主机的工具（`bash`、`edit`、`write`），只靠只读工具勘探。对信任的素材可用 `--allow-write-tools` 放开。
- 暂存前会删掉克隆物里的 `.pi` 与 `.agents` 目录，克隆的仓库没法给自己注册扩展、MCP server 或 skill。
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

- `[task].name` 必须是 `org/name` 形式（envwiki 用 `envwiki/<task-name>`）。
- `environment/Dockerfile` 的构建上下文是 `environment/`。
- `copy_from_staging` 里列的文件会落到工作目录根部、只保留文件名，`repos/x/readme.md` 变成 `/app/readme.md`；instruction、verifier、solution 必须用同一个路径。

## 校验

```bash
$ uv run envwiki validate ./envwiki-tasks/my-task
./envwiki-tasks/my-task: ok, 0 warning(s), schema source: harbor
```

`envwiki validate` 先做本地结构检查，再在 Harbor 可导入时用 Harbor 自己的 `TaskConfig` 校验 `task.toml`。优先用已安装的 Harbor；否则探测到 Harbor 源码目录（`HARBOR_SRC` 或同级的 `harbor/`），补上缺失的包元数据后从源码导入。报告会写明走的是哪条路径。

## 论文语料与引用校验

`src/envwiki/recipes/data/corpus.json` 随包发布，记录了配方所依据的 574 篇论文（arXiv id、标题、所属方法族）。测试会断言：

- 每个配方的引用 id 都在语料内；
- 引用标题与 arXiv 权威标题逐字相符（归一化后）。

所以任何人都能独立复核：一条配方说的是不是那篇论文。

## 开发

```bash
uv sync --extra dev
uv run pytest          # 50 项测试
uv run ruff check src tests
```

## 限制

- 生成的是**初版**任务：结构完整、schema 合法，但难度校准与校验严格程度取决于模型，发布进 benchmark 前请人工过一遍。
- 解题 agent 与 verifier 都没有网络，任务若需要联网取数据会失败。
- 只支持 `linux` 与 `windows` 目标环境，与 Harbor 自身的枚举一致。
- 只读 harness 没法执行它要评的代码；需要运行时事实（堆栈、计算结果）的任务会偏弱，用 `--allow-write-tools` 会好一些。
- 配方匹配是关键词加权的，能把你带到正确的邻域，最终选哪条仍由模型决定。

## License

MIT，见 [LICENSE](LICENSE)。
