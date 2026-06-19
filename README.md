# 📒 笔记本

AstrBot 插件 —— 让 LLM 拥有持久化记忆笔记。

## 功能

- **个人笔记**：每个用户在每个群聊/私聊中拥有独立的笔记列表
- **全局笔记**：群聊级别的共享笔记，所有成员可见
- **自动注入**：LLM 请求前自动将笔记内容注入 prompt，无需手动触发
- **LLM 工具调用**：LLM 可通过 `edit_user_note` 工具自主管理笔记（增/删/改）
- **上限保护**：笔记数量限制 20 条，超出自动截断

## 安装

将本插件放入 AstrBot 的插件目录即可，无需额外配置。

## 工作原理

1. 用户与 LLM 对话时，插件在 `on_llm_request` 钩子中读取该用户的笔记
2. 将笔记内容以 `<notes_plugin>` 标签注入 prompt
3. LLM 可调用 `edit_user_note` 工具对笔记进行批量操作

## LLM 工具：edit_user_note

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 用户ID，留空为当前用户；填 `global` 为全局笔记 |
| `operations` | array | 操作列表，见下方 |

每个操作对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | `add` / `delete` / `replace` |
| `index` | number | 目标索引（从 0 开始），`-1` 表示追加到末尾 |
| `content` | string | 笔记内容（add/replace 必填） |

示例：

```json
[
  {"action": "add", "index": 0, "content": "用户喜欢简洁风格"},
  {"action": "replace", "index": 1, "content": "更新后的内容"},
  {"action": "delete", "index": 2}
]
```

## 数据存储

笔记数据保存在插件数据目录下的 `data.json`，结构为：

```json
{
  "群号": {
    "用户ID": ["笔记1", "笔记2"],
    "global": ["全局笔记1"]
  }
}
```

## 配置

无需配置，开箱即用。

## License

MIT
