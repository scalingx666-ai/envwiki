# envwiki

> 给 agent 用的环境与任务合成**工具箱**。
>
> A toolbox for agents that synthesise environments and tasks.

**[English](readme.en.md)** | **[中文](readme.md)**

环境合成的论文很多，方法各不相同。envwiki 把每一种方法抽象成一条**配方**（recipe），
把配方连同"素材"和"脚手架"一起装进一个 **MCP server**，再把方法论写进一个 **Skill**。

**合成这件事由 agent 做。** envwiki 不生成任务，也不替 agent 做决定。

---

## 这是什么

envwiki 是三件东西，都是给 agent 用的：

- 一个 **MCP server**：一套工具箱——配方（方法）、素材（暂存区）、脚手架（写任务、校验任务）。
  它**不含任何合成逻辑**：不会替 agent 决定任务长什么样。
- 一个 **Skill**：唯一写着"怎么写一个 Harbor 任务"的地方——方法论、verifier 契约、
  参考解契约、路径规则、提交前自检清单。
- 一组**诊断命令**：把工具箱装进你的 agent（打印 MCP 配置、装 skill），以及校验一个任务
  目录、看一个链接会怎么处理。

envwiki **不会**替你拉起 agent，也**不会**自己合成任务。你就是你自己的 agent 的主人：
把 MCP server 挂上去，把 skill 装上，然后跟它说"把这个链接变成一个 Harbor 任务"。

任何支持 MCP 与 skills 的 harness 都能用。pi、Claude Code、Codex、OpenCode……都行。

## 职责边界

| 谁 | 负责 | 不负责 |
| --- | --- | --- |
| agent | 读素材、挑方法、决定写什么任务、按校验结果迭代 | 素材解析、schema 判定 |
| envwiki MCP server | 给方法（配方）、给素材（暂存）、写任务（脚手架）、校验任务 | 决定写什么任务、生成任务文本 |
| envwiki CLI | 打印 MCP 配置、安装 skill、校验任务、看链接怎么处理 | 合成任务、编排 agent |

**契约只有一份。** 任务规格由 `scaffold_task` 的工具签名与
`envwiki/schemas.py` 里的 `TaskDraft`（pydantic）强制；envwiki 里没有任何第二份
任务 JSON 结构；Harbor 的方法铁律**只**留在 skill 里。想看"任务长什么样"，看工具签名；
想看"怎么写好任务"，看 skill。

```
链接 / 上传
   |
   v
agent 调 stage_source  ->  暂存区：文件树 + 带行号索引的摘要
   |
   v
agent 调 plan_task  ->  选方法  ->  get_recipe  ->  按步骤执行
   |
   v
agent 调 scaffold_task  ->  写任务  ->  validate_task  ->  gate_task  ->  不合格就改，再来一轮
```

## 怎么用

三步。

### 1. 把 MCP server 挂给你的 agent

```
uv run envwiki mcp config
```
```
{
  "mcpServers": {
    "envwiki": {
      "command": "/path/to/python",
      "args": ["-m", "envwiki.mcp_server"],
      "description": "..."
    }
  }
}
```

把它写进 agent 的 MCP 配置：pi 放 `~/.pi/agent/mcp.json`（全局）或项目的
`.pi/mcp.json`；别的 harness 找它自己的 MCP 配置位置即可。工具全名是
`mcp__envwiki__plan_task`、`mcp__envwiki__scaffold_task`、
`mcp__envwiki__validate_task` 等。

### 2. 装 skill

```
uv run envwiki skill install --to ~/.pi/agent/skills
```

不带 `--to` 会打印 skill 的位置，你自己 copy 也行。

### 3. 跟你的 agent 说一句话

"用 envwiki 把 https://github.com/owner/repo 变成一个 Harbor 任务。"

agent 会自己走完：`stage_source` → `plan_task` → `get_recipe` →
`scaffold_task` → `validate_task` → `gate_task`，最后把任务目录交给你。

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

### 怎么匹配

配方不是靠关键词硬碰出来的。envwiki 把每条配方向量化后放进 **zvec**（进程内向量库）：

- **信号向量**：summary + when_to_use + not_when_to_use + inputs 的 BM25 稀疏向量；
- **细节向量**：整条配方（步骤、校验、坑）的 BM25 稀疏向量；
- **稠密向量**：配了 embedding 端点时再加一层语义向量；
- **全文索引**：zvec 自带的 FTS。

查询时这几路信号一起检索，用 RRF 融合排序。索引按配方库内容哈希缓存在
`~/.cache/envwiki/recipes-<hash>.zvec`，配方库一改就换一份。

两份排名还会再融合一次：向量库给的是整体相似度，词法匹配给的是配方作者亲手写下的
`when_to_use` 信号短语（"这是个终端任务"、"这是个网页应用"这种）。RRF 把两份排名合并，
谁也埋不掉谁——向量负责找对邻域，信号短语负责在邻域里排对顺序。

稠密向量需要一个 embedding 端点：

| 变量 | 含义 |
| --- | --- |
| `ENVWIKI_EMBEDDING_BASE_URL` | OpenAI 兼容的 `/embeddings` 端点 |
| `ENVWIKI_EMBEDDING_MODEL` | 模型 id |
| `ENVWIKI_EMBEDDING_API_KEY` | 该端点的 key（可选） |

`plan_task` / `recommend_recipes` / `search_recipes` 的返回里都有 `engine` 字段，
写着这次是 `zvec-hybrid`、`zvec-bm25` 还是 `lexical`。

## MCP server：工具箱

```
uv run envwiki-mcp                       # stdio，agent 拉起的形式
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
| `gate_task` | **执行级验证门**：真的把任务跑起来，检查参考解能否拿满分、无作为是否留出奖励空间 |

## Skill

`src/envwiki/skills/env-synthesis/SKILL.md` 是**方法与规则的唯一出处**：工具表、
七步工作流、什么算好任务、verifier 契约、参考解契约、测量式难度、路径规则、提交前自检清单。

## 命令行

envwiki 的命令行只做两件事：把工具箱装进你的 agent，以及诊断。

```
uv run envwiki validate <task dir>            # 用 Harbor schema 校验任务
uv run envwiki gate <task dir>                # 真的跑一遍：参考解满分 + 基线留出奖励空间
uv run envwiki inspect <url>                  # 看某个链接会怎么处理
uv run envwiki model check                    # 模型端点是否可用
uv run envwiki model register                 # 把端点注册进 pi 的 models.json
uv run envwiki mcp serve                      # 以 MCP server 形式运行
uv run envwiki mcp config                     # 打印挂载 envwiki 用的 MCP 配置
uv run envwiki skill install --to <dir>       # 把 skill 装进 agent
```

没有 `build`：envwiki 不替你合成，也不替你编排 agent。合成是 agent 通过 MCP 做的。

## 配置

全部通过环境变量，便于无人值守运行。

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `ENVWIKI_BASE_URL` | `http://127.0.0.1:8787/v1` | OpenAI 兼容端点 |
| `ENVWIKI_API_KEY` | `sk-my-secret` | 该端点的 API key |
| `ENVWIKI_MODEL` | `hy4flash-free` | 模型 id |
| `ENVWIKI_PROVIDER` | `envwiki-local` | 写入 pi models.json 的 provider 名 |
| `HARBOR_SRC` | 自动探测 | Harbor 的 `src` 目录，用于 schema 校验 |
| `ENVWIKI_STAGING_DIR` | 空 | `scaffold_task` 默认写入的暂存区 |
| `ENVWIKI_INDEX_DIR` | `~/.cache/envwiki` | 配方向量索引的缓存目录 |
| `ENVWIKI_EMBEDDING_BASE_URL` | 空 | 稠密向量用的 OpenAI 兼容 `/embeddings` 端点 |
| `ENVWIKI_EMBEDDING_MODEL` | 空 | 稠密向量用的模型 id |
| `ENVWIKI_EMBEDDING_API_KEY` | 空 | 该 embedding 端点的 key |

API key 不落盘：pi 的 `models.json` 里写的是 `"$ENVWIKI_API_KEY"`，真实值在运行时
由环境注入。

## 安全

素材不可信，所以默认收得很紧：

- **模型只能通过 `scaffold_task` 落盘**：它写不出别的文件，写出来的任务立刻过一遍
  pydantic 与 Harbor schema。
- 暂存前会删掉克隆物里的 `.pi` 与 `.agents` 目录，克隆的仓库没法给自己注册扩展、
  MCP server 或 skill。
- skill 明确写明：素材是数据，不是指令。
- API key 只以环境变量引用出现，不写进任何配置文件。

## 任务目录结构

```
my-task/
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

来自 Harbor 自身的硬规则，由构建器与校验器保证：

- `[task].name` 必须是 `org/name` 形式（`scaffold_task` 的 `org` 参数决定前缀）。
- `environment/Dockerfile` 的构建上下文是 `environment/`。
- `scaffold_task` 的 `copy_from_staging` 里列的文件会落到工作目录根部、只保留文件名，
  `repos/x/readme.md` 变成 `/app/readme.md`；instruction、verifier、solution
  必须用同一个路径。
- **Harbor 只发现并上传 `tests/test.sh` 与 `solution/solve.sh` 各一个文件**，
  同目录下的其它文件容器里根本看不到。所以 Python 写的 verifier 与参考解会被
  内联进这两个入口文件，而不是另存成 `test.py`/`solve.py`。
- **参考解必须留下产物**：只定义不落盘的解法跑完什么都没留下，verifier 只会看到
  "文件不存在"。Python 解法会被写进工作目录再执行。

### 难度是测出来的，不是写出来的

`[metadata].difficulty` 默认是 `"unrated"`，不是作者拍脑袋的 easy/medium/hard。
真正的难度写在 `[metadata.difficulty_facts]` 里：floor 是多少、几个 check、
跑一次多贵、指令有没有泄露答案。有测量才有难度。

### 溯源要钉住

`[metadata.provenance]` 记上游仓库、commit、license 与素材哈希。有 commit 才谈得上
"同一个任务"可复现、可核对；只写了 repo 没写 commit，校验器会提醒。

真实跑出来的一个例子在 ``examples/click-json-inventory-cli/``：那是 agent 通过 MCP
从 [pallets/click](https://github.com/pallets/click) 的文档合成出来的任务，配方是
``dockerized-terminal-blueprint``，校验通过 Harbor 的 TaskConfig。

## 校验

```
$ uv run envwiki validate ./my-task
./my-task: ok, 0 warning(s), schema source: harbor
```

校验只证明**形状**对。真正证明任务能用的是执行门：

```
$ uv run envwiki gate ./my-task
pass: instruction_disclosure - the instruction does not contain the solution
pass: verifier_entrypoint - tests/test.sh is present, the entry point Harbor runs
pass: oracle - the reference solution earned the full reward
pass: baseline - an agent that does nothing earns less than the full reward
pass: reward_space - the reward an agent competes for, above the floor
reward: 1.0
floor: 0.0
reward_repair: 1.0
./my-task: passed, verified
```

执行门会真的在容器里把任务跑两遍：

- **oracle**：跑参考解。它必须拿到 **1.0**，否则说明任务不可解、或者参考解本身没写出
  verifier 要检查的东西。
- **baseline**：跑一个什么都不做的 agent。它必须**拿不到满分**，否则这个任务白送分，
  测不出任何东西。

两者之间的差额就是 agent 要争取的奖励空间。任务从半成品起步时，用
`reward_floor` 记下未修状态的得分，归一化后的奖励是
`(reward - floor) / (1 - floor)`——floor 0.2 时，0.45 的奖励等于剩余空间里的 0.3125。

门需要 Harbor CLI 与运行中的 Docker daemon。缺任何一个，它会**明说自己没跑成**，
而不是当作通过。

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
uv sync --extra dev --extra vector
uv run pytest          # 92 项测试

`vector` 这一档装上 zvec：配方检索走向量库而不是关键词加权。zvec 只提供
CPython 3.10–3.14 的 wheel，所以本仓库锁在 3.13（见 `.python-version`）。
不装这一档照样能用，只是退回内置的词法匹配。
uv run ruff check src tests
```

## 限制

- 生成的是**初版**任务：结构完整、schema 合法、执行门能跑通，但难度标定与校验严格
  程度仍取决于模型，发布进 benchmark 前请人工过一遍。
- 执行门需要 Harbor CLI 与运行中的 Docker daemon。缺了它会明说没跑成，而不是假装
  通过——所以"门过了"这句话只在真的跑过时才成立。
- 解题 agent 与 verifier 都没有网络，任务若需要联网取数据会失败。
- 只支持 `linux` 与 `windows` 目标环境，与 Harbor 自身的枚举一致。
- envwiki 不替你跑 agent：合成质量取决于你的 agent 与模型，也可能它不按工具走。
- 配方检索默认走 BM25 稀疏向量；要语义检索得自己配一个 embedding 端点。
- 配方匹配只是把你带到正确的邻域，最终选哪条仍由模型决定。

## License

MIT，见 [LICENSE](LICENSE)。
