# ADR-003: 选择 SQLite 作为持久化存储

## 状态

已采纳（Accepted）

## 背景

mini-harness 需要为 SessionStore 和 Tracer 两个组件提供持久化存储能力。需要选型存储方案。

## 决策

**选择 SQLite 作为默认存储引擎。**

## 考虑的方案

### 方案 A：SQLite（✅ 采纳）

- 零依赖（Python 标准库内置 `sqlite3` 模块）
- 单机部署，无需额外服务进程
- 支持标准 SQL 查询，适合追踪数据的结构化统计
- 文件存储，备份/迁移只需复制一个文件
- 支持 WAL 模式提升并发读取性能

### 方案 B：Redis（❌ 否决）

- 需要额外安装和运维 Redis 服务
- 内存型存储，大量追踪数据成本高
- 增加项目依赖数量，违背"零框架依赖"原则
- 适合高频写入场景，但 mini-harness 不需要

### 方案 C：PostgreSQL（❌ 否决）

- 需要额外安装和运维数据库
- 重量级，不适合"一个下午读完源码"的定位
- SQLite 的 SQL 能力足够满足当前需求

## 影响

- 所有持久化组件（SessionStore、Tracer）使用 SQLite
- 使用 `check_same_thread=False` + WAL 模式支持多线程
- 使用 `threading.Lock` 保护写入操作避免并发冲突
- 未来如果需要分布式部署，可通过抽象接口替换存储引擎
