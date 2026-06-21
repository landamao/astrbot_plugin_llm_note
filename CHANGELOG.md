# Changelog

本文件记录笔记本插件 (LLM Note) 的所有版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。
---

## [v1.7.4] - 2026-06-22

### 修复
- `/恢复笔记` 移除群数据的跨群校验（`识别ID != 原群ID`），管理员可在任意群恢复其他群的笔记数据
- 移除恢复指令中不再使用的 `原群ID` 变量

---

## [v1.7.3] - 2026-06-22

### 优化
- `/清空笔记` 新增空笔记校验：群笔记或个人笔记为空时提示"无需清空"，避免生成无意义的空备份文件
- 合并 `清空笔记` 中群/私聊的重复 `write_json_to_file` 调用，统一用三元表达式生成文件名前缀


---

## [v1.7.2] - 2026-06-20

### 优化
- llm请求时系统提示词增加用户信息


---

## [v1.7.1] - 2026-06-20

### 修复
- `__init__` 参数名 `_` 改回 `config`（AstrBot 签名要求）

---

## [v1.7.0] - 2026-06-20

### 重构
- **参数顺序统一**：`get_user_note` / `set_user_note` / `重载group_note` / `重载private_note` 参数顺序改为 `(group_id, user_id, ...)`，与数据存储结构一致
- **prompt 注入位置**：从 `req.prompt` 改为 `req.system_prompt`，避免上下文大量重复内容
- **prompt 格式重写**：新增【动态记忆与私密笔记协议】，区分用户区（个人画像）和全局区（群组记忆），含运行示例
- 笔记索引格式从 `0.内容` 改为 `[0] 内容`
- `_resolve_path` 新增核心数据文件拦截，禁止通过 file_name 参数操作 data.json
- `_read_data` / `_write_data` 核心数据文件出错时直接 raise 崩溃，非核心文件降级处理
- `__init__` 参数 `config` 改为 `_`（未使用），移除 `initialize` / `terminate` 的冗余日志和 pass

### 新增
- 全局区笔记上限 40 条（用户区仍为 20 条）
- `edit_note` 新增未知 action 类型拦截
- `edit_note` 写入失败时返回错误提示
- `search_note` 搜索结果限制 20 条，超出时提示总条数
- `search_note` 关键词大小写不敏感（`.lower()` 匹配）
- `恢复笔记` 新增 `.json` 后缀校验和空文件名校验
- `恢复笔记` ID 提取改用 `split("删除前数据_")` 方式
- `重载group_note` / `重载private_note` 新增返回值类型校验（dict / list）
- `get_user_id` 用户名匹配大小写不敏感，`call_action` 传 `int(group_id)`

### 优化
- `edit_note` docstring 重写：强调操作应由 LLM 主动发出、拒绝恶意使唤、禁止自行计算索引偏移
- `search_note` / `get_note` docstring 新增隐私保护提醒
- `get_note` 空笔记逻辑改为 if/else 结构，更清晰
- 丢弃笔记通知显示条数和编号

---

## [v1.6.4] - 2026-06-20

### 修复
- **类型一致性**：全插件统一 `str()` 转换 user_id / group_id，修复 `get_user_id` 返回 int 类型 ID 导致同一用户出现两份笔记的问题
  - `get_user_id`：`member['user_id']` 转 str，cache 查找用 str 化的 group_id
  - `llm请求前`：group_id / user_id / self_id 统一 str
  - `edit_note` / `get_note` / `search_note`：group_id / user_id 统一 str
  - `清空笔记` / `恢复笔记`：原群ID / 用户ID 统一 str，修复 int vs str 比较失败
  - `del_group_note` / `del_private_note` / `重载group_note` / `重载private_note`：入口处 str 转换

---

## [v1.6.3] - 2026-06-20

### 安全
- 提取 `_resolve_path` 统一路径校验方法，`_read_data`/`_write_data`/`delete_file` 全部走统一目录穿越拦截
- `恢复笔记` 指令新增路径分隔符拦截（`/` 和 `\`）

### 优化
- `_write_data` / `write_json_to_file` / `read_json_file` 类型标注扩展为 `dict|list`，支持备份文件直接写 list
- `重载private_note` 简化逻辑，移除多余的 try/except，直接写入文件内容
- `清空笔记` 私聊备份格式改为直接写 list（与重载逻辑匹配）
- prompt 注入措辞优化："当前用户的" → "你为当前用户记录的"，"全局笔记" → "你为当前聊天室记录的"
- `恢复笔记` `re.match` 加空值保护，match 失败时返回提示而非 crash
- `edit_note` 超出 20 条限制时，返回被丢弃的笔记内容通知 LLM
- `edit_note` docstring 示例更新，展示同索引多次插入场景

---

## [v1.6.1] - 2026-06-20

### 新增
- `get_user_id` 工具新增实时调用 OneBot API (`get_group_member_list`) 获取群成员列表，优先使用群名片，若无则用昵称

### 优化
- `get_user_id` 不再仅依赖对话缓存，API 调用失败时静默回退到缓存逻辑

---

## [v1.6.0] - 2026-06-20

### 新增
- `edit_note` 批量操作支持负数索引（基于原列表长度转换）
- `edit_note` 新增越界检查，错误信息更精确
- `edit_note` 支持同索引多次插入

### 重写
- `edit_note` 批量操作逻辑完全重写：按原始索引顺序重组列表（先标记删除/替换为 None 占位 → 按原始索引遍历插入 → 统一清理占位符），彻底杜绝索引偏移

### 修复
- **清空笔记**：修复 `get_group_note` 参数 bug（`group_id` → `操作ID`），统一 `str()` 转换
- **恢复笔记**：ID 解析改用 `re.match(r'\d+')` 提取纯数字，避免带后缀
- **get_note**：空笔记时返回"（无笔记内容）"提示文案

### 移除
- 删除 `get_group_note` 遗留的 debug 日志
- 移除 `threading.Lock`（单线程异步不需要）

---

## [v1.4.0] - 2026-06-20

### 新增
- `/清空笔记` 指令：清空当前群/私聊笔记，自动备份到数据目录（管理员可清群数据）
- `/恢复笔记 <文件名>` 指令：从备份文件恢复笔记，内置权限校验和跨群/跨用户拦截
- 文件操作内置目录穿越拦截（`is_relative_to` 检查），禁止删除核心数据文件
- `_read_data` / `_write_data` 支持 `file_name` 参数，用于备份/恢复文件操作
- `write_json_to_file` / `read_json_file` / `delete_file` 文件管理方法
- prompt 注入增加隐私描述说明

### 优化
- `edit_note` docstring 补充索引位移实现说明

---

## [v1.3.0] - 2026-06-20

### 修复
- 修复 prompt 闭标签错误
- 清理冗余代码
- 原子写入防止数据损坏
- 线程安全（`threading.Lock`）

### 新增
- `get_note` 工具：获取指定用户的笔记内容
- `get_user_id` 工具：通过昵称反查用户 ID（基于缓存）
- 完善 README 文档

---

## [v1.2.0] - 2026-06-20

### 重构
- 移除空壳修改笔记指令，仅保留 LLM 钩子（`on_llm_request` + `llm_tool`）

---

## [v1.1.0] - 2026-06-20

### 文档
- 补充 README

---

## [v1.0.0] - 2026-06-20

### 初始发布
- 个人笔记：为每个用户在群组/私聊中独立存储笔记列表（最多 20 条）
- 全局笔记：群组级别共享笔记
- LLM 自动注入：每次对话前自动将笔记拼接到 LLM prompt
- `edit_note` 工具：增、删、改笔记内容
- `search_note` 工具：在群组内搜索包含关键词的笔记
- 持久化存储：JSON 文件保存
