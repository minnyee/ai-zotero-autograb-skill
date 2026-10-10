# AI Zotero AutoGrab Skill

**AI 自动文献检索、动态分类与 Zotero 自动入库。**

[English](README.md)

**联动 AI 文献检索与分类，自动入库 Zotero 的 AI Agent Skill。** 告诉 AI 要找什么：它按选定的出版范围检索和筛选，根据文章证据动态分类，再将核验后的书目条目保存到 Zotero。

## 亮点

- **贯通检索到入库：** AI 负责搜索与分类，内置 Python 脚本校验已取得的书目证据、去重并自动写入本机 Zotero。
- **按文章动态组织：** 不预设领域分类，同一条文献可以多重归类而不生成副本，主题父目录直接显示全部已归属文献。
- **过程可控、支持续查：** 确认关键词和出版范围，入库前预览，后续发现追加到原目录，同时保护已有条目和附件。
- **目录由你选择：** 可以新建分类目录，也可以合并追加到已有目录。入库复用匹配条目，不删除或覆盖已有条目、附件和笔记。
- **依赖轻量：** Python 标准库与 Zotero 10+，无需额外 MCP 服务器或 Zotero 浏览器扩展。

这是安装在具备所需能力的 AI 客户端中的 [Agent Skill](https://agentskills.io/specification)，例如具备本机执行能力的 ChatGPT Work 或 Codex；它不是 Zotero 内部插件，也不是独立搜索引擎。全文获取沿用用户自己的 Zotero 配置。

## 使用前提

- AI 客户端支持本机文件系统 skill、网页检索和本机 Python 执行。**已验证 Windows 本机智能体执行环境**。ChatGPT Work、Codex 或其他客户端的实际工具与权限满足这些要求、且能连接本机 Zotero 时即可使用。普通网页聊天或仅有云端执行、无法访问 Zotero 所在电脑的环境不能直接使用。
- **Python 3.10+**，仅使用标准库。
- 正在运行的 **Zotero 10+**，以及可写的个人文库 **My Library**。暂不支持群组文库。
- 在 Zotero 中开启 **设置 → 高级 → 允许此计算机上的其他应用程序与 Zotero 通信**；首次通过本地 API 写入时，在 Zotero 弹窗中授权。

执行环境必须能连接 Zotero 所在电脑的 `127.0.0.1:23119`，客户端沙箱可能也需要允许本机访问。仅开启 Zotero 设置不能让远端云环境连接你的电脑。参见 [Zotero 本地 API 官方说明](https://www.zotero.org/support/dev/web_api/v3/local_api)。

**无需额外 MCP、Python 第三方包或 Zotero 浏览器扩展。** 脚本使用 Zotero 内置 Connector 协议和本地 API，不点击浏览器扩展，也不运行浏览器网页翻译器。

全文获取另行处理：依靠 Zotero 内置功能或用户自行配置的插件，例如 Sci-Hub 类插件。skill 不提供或配置这些插件，保存条目也不保证自动下载 PDF 或触发插件。

## 安装与使用

分享[仓库链接](https://github.com/minnyee/ai-zotero-autograb-skill)。如果客户端提供本机 skill 安装器，可以直接请求：

> 请安装这个 skill：https://github.com/minnyee/ai-zotero-autograb-skill/tree/main/skills/ai-zotero-autograb-skill

也可把完整的 `skills/ai-zotero-autograb-skill` 文件夹复制到客户端配置的本机 skill 目录。当前 OpenAI 文档列出的用户目录为 `~/.agents/skills`，已有客户端也可能使用自定义或旧版位置，参见[本机 skill 目录说明](https://learn.chatgpt.com/docs/build-skills)。必要时重新加载，保留 `SKILL.md` 附带的脚本和参考文件。

示例请求：

> 使用 ai-zotero-autograb-skill，查找〈主题〉在〈出版范围〉内的文献，追加到现有〈分类目录〉。检索前让我确认关键词，入库前先预览；只保存书目条目，不下载全文。

1. **确认范围、关键词和目标目录。** 选择追加到已有目录或新建主题；明确选择后不重复询问。同主题补充检索默认追加，新主题不继承旧限制。
2. **检索与筛选。** 覆盖同义词、缩写与全称、分页和引文线索，复用缓存，报告未覆盖分支和访问限制。
3. **核验与预览。** 从出版社记录或官方导出取得信息，确认 DOI 对应当前文章，而不只是能够解析。未解决的书目冲突留在本地候选报告中，不写入 Zotero。
4. **入库与分类。** 复用已有匹配条目，按检索目的和文章证据动态分类。同一条目可归入多个目录，不生成副本；同时直接归入主题父目录和中间各级目录。
5. **返回结果。** 报告新增、复用、候选和冲突数量、目标目录、分类证据及剩余检索缺口。

## 范围与保护规则

| 范围选项 | 出版范围 |
| --- | --- |
| IEEE-Trans | IEEE Transactions，包含联合 Transactions |
| IEEE-Journals | IEEE 期刊 |
| IEEE-Papers | IEEE 期刊与会议 |
| Global | 跨出版社学术文献 |
| Custom / 自定义 | 自行指定出版社、期刊、年份及文章类型 |

支持自定义出版社、期刊、年份和文章类型。限定出版社或期刊时，**优先使用官方检索平台或已经配置的官方 API**；IEEE 范围优先 IEEE Xplore。Global 范围选择合适的学术数据库。官方网站上的全部内容不等于都符合要求，仍须逐篇核对实际出版物。

快捷选项只是便捷入口，不限制只能从表中选择。出版社官方平台、可选跨出版社发现入口及覆盖说明见[检索入口参考表](skills/ai-zotero-autograb-skill/references/search-sources.md)；参考表用于导航，不要求逐站重复检索。

不把其他网站作为必须重复执行的平行检索。确有访问或覆盖缺口时，先说明用途，由用户选择是否启用其他检索入口或扩大出版范围。单篇 DOI 核验与主题检索分开处理。

保护已有元数据、附件、笔记、标签和目录归属。普通入库只追加已授权的目录归属，不删除条目或目录；用户要求的清理属于另行明确授权的操作。期刊声誉不能单独证明论文相关性或质量；没有证据时不宣称检索完整或已阅读全文。

## 数据与授权

授权凭据和运行状态保存在安装者本机，与 skill 文件分开，不包含在 GitHub 分发包中。首次通过本地 API 写入由用户在 Zotero 中授权，之后也可在 Zotero 设置中撤销授权。

日常使用只需向 AI 提出请求，无需手动运行脚本。命令、运行目录及排查方法见[技术参考文档](skills/ai-zotero-autograb-skill/references/manifest.md)。

## 欢迎参与完善

欢迎建议、问题反馈、功能需求及各类改进贡献。

也欢迎补充期刊或出版社的官方检索入口、修正平台信息和链接，或提醒入口失效，帮助完善[检索入口参考](skills/ai-zotero-autograb-skill/references/search-sources.md)。

- 通过 [Issue](https://github.com/minnyee/ai-zotero-autograb-skill/issues) 分享使用反馈、提问或讨论改进建议。
- 有具体修改时，欢迎直接提交 [Pull Request（PR）](https://github.com/minnyee/ai-zotero-autograb-skill/pulls)，完善 skill、文档或参考资料。小型文档和链接修正无需先开 Issue。

补充检索入口时，请附来源名称、官方网址及简短覆盖说明，并区分出版社平台与跨出版社发现服务。

## 验证与许可

在仓库根目录运行 `python -m unittest discover -s tests`。**48 项自动化测试**使用虚构条目和本机模拟服务器，不接触真实 Zotero 文库；覆盖 DOI 对应与冲突、严格 IEEE 范围、目标目录续查、多级归属、已有数据保护、授权、部分保存、分页及迁移后的 Unicode 路径。测试通过不能证明检索完整或学术质量。

| 环境 | 验证情况 |
| --- | --- |
| Windows / Python / 本机 AI 智能体执行环境 | 自动化测试和 skill 格式校验通过 |
| Windows / Zotero 10.0.5 | 此前已实际验证入库、去重、分类、文库保护，以及已保存但响应失败时的恢复 |
| macOS、Linux、其他 AI 客户端 | 尚未实机测试 |

真实 Zotero 验证属于历史验证记录，不是自动化测试的一部分。分发内容仅包含代码、测试、文档和许可证，不包含个人文库数据或凭据。采用 [MIT 许可证](LICENSE)。
