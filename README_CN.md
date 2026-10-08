# Zotero 文献检索

[English](README.md)

**联动 AI 文献检索与分类，自动入库 Zotero 的 AI Agent Skill。** 告诉 AI 要找什么：它按选定的出版范围检索和筛选，根据文章证据动态分类，再将核验后的书目条目保存到 Zotero。

## 亮点

- **贯通检索到入库：** AI 负责搜索与分类，内置 Python 脚本校验已取得的书目证据、去重并自动写入本机 Zotero。
- **按文章动态组织：** 不预设领域分类，同一条文献可以多重归类而不生成副本，主题父目录直接显示全部已归属文献。
- **过程可控、支持续查：** 确认关键词和出版范围，入库前预览，后续发现追加到原目录，同时保护已有条目和附件。
- **依赖轻量：** Python 标准库与 Zotero 10+，无需额外 MCP 服务器或 Zotero 浏览器扩展。

这是安装在具备所需能力的 AI 客户端中的 [Agent Skill](https://agentskills.io/specification)，例如使用 GPT 的 Codex 环境；它不是 Zotero 内部插件，也不是独立搜索引擎。全文获取沿用用户自己的 Zotero 配置。

## 使用前提

- AI 客户端支持 skill、网页检索和本机 Python 执行。**已验证 Windows 上的 Codex**，但不强制使用 Codex；ChatGPT 或其他客户端只有在执行环境具备这些能力且能访问本机 Zotero 时才适用。
- **Python 3.10+**，仅使用标准库。
- 正在运行的 **Zotero 10+**，以及可写的个人文库 **My Library**。暂不支持群组文库。
- 在 Zotero 中开启 **设置 → 高级 → 允许此计算机上的其他应用程序与 Zotero 通信**；首次通过本地 API 写入时，在 Zotero 弹窗中授权。

执行环境必须能连接 Zotero 所在电脑的 `127.0.0.1:23119`，客户端沙箱可能也需要允许本机访问。仅开启 Zotero 设置不能让远端云环境连接你的电脑。参见 [Zotero 本地 API 官方说明](https://www.zotero.org/support/dev/web_api/v3/local_api)。

**无需额外 MCP、Python 第三方包或 Zotero 浏览器扩展。** 脚本使用 Zotero 内置 Connector 协议和本地 API，不点击浏览器扩展，也不运行浏览器网页翻译器。

全文获取另行处理：依靠 Zotero 内置功能或用户自行配置的插件，例如 Sci-Hub 类插件。skill 不提供或配置这些插件，保存条目也不保证自动下载 PDF 或触发插件。

## 安装与使用

把完整的 `skills/zotero-literature-search` 文件夹复制到客户端的 skill 目录。Codex 默认位置为 `~/.codex/skills/zotero-literature-search`，也可使用 `$CODEX_HOME/skills/zotero-literature-search`；其他客户端按各自约定安装。必要时重新加载 skill，保留 `SKILL.md` 附带的脚本和参考文件。

示例请求：

> 使用 zotero-literature-search，查找〈主题〉在〈出版范围〉内的文献，追加到现有〈分类目录〉。检索前让我确认关键词，入库前先预览；只保存书目条目，不下载全文。

1. **确认范围、关键词和目标目录。** 选择追加到已有目录或新建主题；明确选择后不重复询问。同主题补充检索默认追加，新主题不继承旧限制。
2. **检索与筛选。** 覆盖同义词、缩写与全称、分页和引文线索，复用缓存，报告未覆盖分支和访问限制。
3. **核验与预览。** 从出版社记录或官方导出取得信息，确认 DOI 对应当前文章，而不只是能够解析。未解决的书目冲突留在本地候选报告中，不写入 Zotero。
4. **入库与分类。** 复用已有匹配条目，按检索目的和文章证据动态分类。同一条目可归入多个目录，不生成副本；同时直接归入主题父目录和中间各级目录。
5. **返回结果。** 报告新增、复用、候选和冲突数量、目标目录、分类证据及剩余检索缺口。

## 范围与保护规则

| 快捷选项 | 出版范围 |
| --- | --- |
| IEEE-Trans | IEEE Transactions，包含联合 Transactions |
| IEEE-Journals | IEEE 期刊 |
| IEEE-Papers | IEEE 期刊与会议 |
| Global | 跨出版社学术文献 |

支持自定义出版社、期刊、年份和文章类型。限定出版社或期刊时，**优先使用官方检索平台或已经配置的官方 API**；IEEE 范围优先 IEEE Xplore。Global 范围选择合适的学术数据库。官方网站上的全部内容不等于都符合要求，仍须逐篇核对实际出版物。

不把其他网站作为必须重复执行的平行检索。确有访问或覆盖缺口时，先说明用途，由用户选择是否启用其他检索入口或扩大出版范围。单篇 DOI 核验与主题检索分开处理。

保护已有元数据、附件、笔记、标签和目录归属。普通入库只追加已授权的目录归属，不删除条目或目录；用户要求的清理属于另行明确授权的操作。期刊声誉不能单独证明论文相关性或质量；没有证据时不宣称检索完整或已阅读全文。

## 脚本与本机数据

在安装后的 skill 目录中执行以下命令。AI 按[清单格式与示例](skills/zotero-literature-search/references/manifest.md)准备 manifest；脚本本身不检索网站，也不抓取 DOI 核验证据。

```sh
python scripts/zotero_library.py doctor
python scripts/zotero_library.py ingest --manifest manifest.json --dry-run --report preview.json
python scripts/zotero_library.py ingest --manifest manifest.json --report import.json
```

`doctor` 检查连接，不测试实际写入。部分失败后应先检查结果再重试，因为条目可能已经保存、只是响应失败。全局选项和恢复方法见清单参考文档。

凭据与运行数据保留在安装者本机，放在分发 skill 之外。Windows 默认状态目录为 `%LOCALAPPDATA%/zotero-literature-search`，其他平台为 `$XDG_STATE_HOME/zotero-literature-search` 或 `~/.local/state/zotero-literature-search`。Windows 凭据使用当前用户绑定的 DPAPI，其他平台使用私有文件。不要把清单、报告、缓存或密钥提交到 Git；可通过 Zotero 的 **Clear Write Authorizations（清除写入授权）** 撤销授权。

## 验证与许可

在仓库根目录运行 `python -m unittest discover -s tests`。**48 项自动化测试**使用虚构条目和本机模拟服务器，不接触真实 Zotero 文库；覆盖 DOI 对应与冲突、严格 IEEE 范围、目标目录续查、多级归属、已有数据保护、授权、部分保存、分页及迁移后的 Unicode 路径。测试通过不能证明检索完整或学术质量。

| 环境 | 验证情况 |
| --- | --- |
| Windows / Python / Codex | 自动化测试和 skill 格式校验通过 |
| Windows / Zotero 10.0.5 | 此前已实际验证入库、去重、分类、文库保护，以及已保存但响应失败时的恢复 |
| macOS、Linux、其他 AI 客户端 | 尚未实机测试 |

真实 Zotero 验证属于历史验证记录，不是自动化测试的一部分。分发内容仅包含代码、测试、文档和许可证，不包含个人文库数据或凭据。采用 [MIT 许可证](LICENSE)。
