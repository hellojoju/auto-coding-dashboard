# AI 全自动开发平台

> 人类当甲方，AI 干所有活

一个端到端的 AI 驱动开发平台，可以用自然语言描述需求，AI 自动完成代码编写、测试、部署全流程。

## 架构

```
├── cli.py              # CLI 入口
├── packages/           # 核心引擎
├── dashboard-ui/       # 前端界面（Next.js）
└── pyproject.toml      # Python 依赖
```

## 快速开始

### 后端

```bash
uv run python cli.py dashboard --port 8000
```

### 前端

```bash
cd dashboard-ui
npm install
npm run dev -- -p 3568
```

打开 http://localhost:3568 访问 Dashboard。

## 功能

- AI 驱动的自动化开发流程
- 实时看板管理开发任务
- 事件驱动架构
- 多代理协作
- 代码审查与安全扫描
- MCP 协议支持

## 技术栈

- **后端**：Python 3.12+，uv，Anthropic API，MCP
- **前端**：Next.js，React，TypeScript
- **部署**：Playwright（自动化浏览器操作）

## License

MIT
