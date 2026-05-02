# Ralph Runtime Console 集成修复计划

## 问题确认

当前实现存在严重的契约不匹配问题，导致前后端无法真实通信。

---

## 修复任务清单

### 任务 1：统一 API 契约（最高优先级）

**问题：**
- 前端 `listWorkUnits()` 期望返回 `WorkUnit[]`，后端返回 `{ work_units, total }`
- 前端 Evidence URL 是 `/api/ralph/work-units/{id}/evidence`，后端实际是 `/api/ralph/evidence/{work_id}`

**修复方案：**
- 修改前端 `ralph-api.ts` 适配后端的响应包装格式
- 修改前端 URL 路径与后端对齐
- 或者：修改后端返回格式与前端对齐（选择此方案，因为后端更灵活）

**决策：后端适配前端**，因为前端类型定义更完整，且已是既定接口。

**具体修改：**
```python
# routes.py 修改点：
# 1. list_work_units 返回 { work_units: [...], total: n } → 改为直接返回 [...]
# 2. list_evidence 保持 /api/ralph/evidence/{work_id}
# 3. 其他列表端点同理
```

### 任务 2：修复 Command 契约

**问题：**
- 前端发送 `{ command_type, target_id }`，后端要求 `{ type, work_id }`
- CommandConsumer 不识别 Ralph 命令类型

**修复方案：**
- 统一字段名：`command_type`（前端对）vs `type`（后端错）→ 后端改为 `command_type`
- 统一 target：`target_id`（前端对）vs `work_id`（后端限）→ 后端改为 `target_id`
- Consumer 新增 Ralph Command 处理分支

### 任务 3：修复类型定义不一致

**问题：**
- `Evidence`：前端要 `file_name/file_type/size_bytes`，后端是 `evidence_type/file_path/description`
- `Blocker`：前端要 `category/created_at`，后端是 `blocker_type/resolution/resolved`

**修复方案：**
- 修改后端 schema 序列化，与前端对齐
- 或者修改前端类型，与后端对齐

**决策：后端对齐前端**，因为前端 UI 已按前端类型实现。

### 任务 4：修复 Tab 路由和内容渲染

**问题：**
- Tab 只是 UI 状态，不驱动路由
- WorkUnit 点击只 `addTab`，没有导航
- Sidebar 点击也只是加 Tab

**修复方案：**
- Tab 点击时：`router.push()` 到对应路由
- WorkUnit 列表点击：`router.push('/ralph/${workId}')`
- Sidebar 点击：`router.push('/ralph/approvals')` 等
- 当前激活 Tab 应反映当前路由

### 任务 5：接入 WebSocket

**问题：**
- 前端连 `/ws/events`，后端只有 `/ws/dashboard`
- WebSocket 没有在页面里实例化

**修复方案：**
- 后端新增 `/ws/ralph` 端点，或统一使用 `/ws/dashboard` 但增加 Ralph 事件类型
- 在 `layout.tsx` 或页面组件中实例化 `RalphWebSocket`
- 连接建立后订阅事件

### 任务 6：集成 EvidenceViewer

**问题：**
- WorkUnitDetail 中 EvidenceViewer 还是占位符

**修复方案：**
- 删除占位符，引入真实 `EvidenceViewer` 组件

### 任务 7：修复质量门禁

**问题：**
- ESLint 失败：`no-explicit-any`，unused vars，hook deps
- TypeScript 检查失败

**修复方案：**
- 修复 Ralph 相关文件的 ESLint 问题
- 修复类型定义问题

### 任务 8：后端回归测试修复

**问题：**
- 5 个测试失败，原因是调用 `python -m py_compile` 但环境只有 `python3`

**修复方案：**
- 修改代码使用 `python3` 而不是 `python`

---

## 执行顺序

```
并行组 1：后端契约修复（任务 1、2、3）
  ↓
并行组 2：前端功能修复（任务 4、5、6）
  ↓
并行组 3：质量修复（任务 7、8）
  ↓
集成验证
```

## 验收标准

- [ ] 前端 `npm run lint` 通过
- [ ] 前端 `npx tsc --noEmit` 通过
- [ ] 后端 `pytest tests/test_ralph_api.py` 通过
- [ ] 真实 WorkUnit 列表能加载并显示
- [ ] 点击 WorkUnit 能打开详情页并显示数据
- [ ] 审批中心能加载 pending actions
- [ ] 批准/拒绝能创建 Command 成功（200，不是 422）
- [ ] WebSocket 能连接并接收事件
- [ ] Evidence 能在详情页查看
