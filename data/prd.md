# FastAPI TODO 清单应用 PRD

## 产品概述
一款基于 FastAPI 的轻量级 TODO 清单应用，提供任务的增删改查（CRUD）核心能力，支持任务状态管理和基础分类。

## 核心功能
1. 创建 TODO 任务（标题、描述、优先级、截止日期）
2. 查询 TODO 列表（支持按状态/优先级筛选、分页）
3. 更新 TODO 任务（修改内容、标记完成/未完成）
4. 删除 TODO 任务（软删除）
5. 按 ID 查询单条任务详情

## 技术选型
- 框架：FastAPI + Pydantic v2
- 数据库：SQLite（开发）/ PostgreSQL（生产），使用 SQLAlchemy 2.0 async
- 迁移：Alembic
- 测试：pytest + httpx（异步测试）
- API 文档：FastAPI 自动生成的 Swagger UI / ReDoc

## 非功能需求
- 性能：P99 响应时间 < 200ms，支持 100 QPS
- 安全：输入校验（Pydantic）、SQL 注入防护（ORM 参数化）、CORS 配置
- 可扩展性：分层架构（router → service → repository），便于后续接入认证、多租户等能力