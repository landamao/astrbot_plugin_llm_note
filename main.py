import asyncio, json, re, shutil, time
from pathlib import Path
from astrbot.api.event import filter
from astrbot.api.star import StarTools
from astrbot.api.provider import ProviderRequest
from astrbot.api.all import logger, At, Reply, AstrMessageEvent, Context, Star, AstrBotConfig


class Note:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_path = self.data_dir / "data.json"
        self._ensure_file()

    def _ensure_file(self):
        """确保 JSON 数据文件存在，不存在则初始化为空字典"""
        if not self.data_path.exists():
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False)

    def _read_data(self) -> dict:
        """读取底层 JSON 数据"""
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取笔记数据失败: {e}")
            return {}

    def _write_data(self, data: dict):
        """写入底层 JSON 数据"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"写入笔记数据失败: {e}")

    def get_user_note(self, user_id: str, group_id: str = "private") -> list[str]:
        """获取特定群组/私聊下用户的笔记列表"""
        data = self._read_data()
        group_id_str, user_id_str = str(group_id), str(user_id)
        return data.get(group_id_str, {}).get(user_id_str, [])

    def get_global_notes(self, group_id: str = "private") -> list[str]:
        """获取群组的全局笔记"""
        if group_id == "private":
            return []  # 私聊不可见其他用户的
        # 全局群笔记直接以 "global" 作为特殊的 user_id 存储在当前 group_id 下
        return self.get_user_note("global", group_id)

    def set_user_note(self, user_id: str, group_id: str, new_notes: list[str]):
        """覆盖更新用户的笔记列表（包含全局笔记）"""
        data = self._read_data()
        group_id_str, user_id_str = str(group_id), str(user_id)

        if group_id_str not in data:
            data[group_id_str] = {}

        data[group_id_str][user_id_str] = new_notes
        self._write_data(data)


class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()  # type: Path
        self.note = Note(self.data_dir)

    async def initialize(self) -> None:
        """可选异步初始化，当插件被激活时会调用这个方法"""
        logger.info("笔记插件初始化完成，数据存储已准备就绪。")

    async def terminate(self) -> None:
        """可选异步终止，当插件被关闭时调用这个方法"""
        pass

    @filter.on_llm_request()
    async def llm请求前(self, event: AstrMessageEvent, req: ProviderRequest):
        group_id = event.get_group_id() or "private"
        user_id = event.get_sender_id()
        self_id = event.get_self_id()

        if user_id == self_id:
            return

        notes = self.note.get_user_note(user_id, group_id)
        global_notes = self.note.get_global_notes(group_id)

        # 如果个人笔记和全局笔记都为空，则不注入 prompt
        if not notes and not global_notes:
            return

        prompt_segments = ["\n\n<notes_plugin>"]

        if notes:
            note_str = ''.join([f"{i}.{j}\n" for i, j in enumerate(notes)])
            prompt_segments.append(f"这是当前用户的笔记本内容（格式：索引.内容\\n\\n）：\n{note_str}")

        if global_notes:
            global_note_str = ''.join([f"{i}.{j}\n" for i, j in enumerate(global_notes)])
            prompt_segments.append(f"这是当前聊天室全局笔记内容：\n{global_note_str}")

        prompt_segments.append("<notes_plugin>\n\n")

        # 合并拼接提示词
        req.prompt += "\n".join(prompt_segments)

    @filter.llm_tool(name="edit_user_note")
    async def llm_修改笔记(
            self,
            event: AstrMessageEvent,
            user_id: str = None,
            operations: list[dict] = None
    ) -> str:
        """
        批量修改用户的笔记列表（支持按索引增、删、改），笔记总数不超过20条，若超出，则会自动删掉最前面的
        笔记内容不会主动告诉用户，可填写好对用户的感度、印象、关系等
        Args:
            user_id(string): 用户ID，不填默认为当前用户。，若填global，则填入到当前聊天室全局
            operations(array): 操作列表，每个元素是一个对象(object)，包含 action、index、content 三个字段。
                字段说明：
                - action(string): 必填，操作类型。可选值 "add"（添加）、"delete"（删除）、"replace"（替换），删除不会影响索引位置变化，我们会正确处理
                - index(number): 必填，目标索引（从 0 开始）。若为 -1 或超出当前长度，对于 add 操作将追加到末尾。
                - content(string): 对于 add 和 replace 操作必填，表示笔记内容；对于 delete 操作可忽略。

                示例（JSON格式）：
                [
                    {"action": "add", "index": 0, "content": "插入到第一条"},
                    {"action": "replace", "index": 2, "content": "覆盖第三条内容"},
                    {"action": "delete", "index": 1}
                ]
        Returns:
            操作后的列表内容
        """
        if not operations:
            return "未执行任何操作，笔记列表未变动。"

        group_id = event.get_group_id() or "private"
        user_id = user_id or event.get_sender_id()

        if user_id == "global" and group_id == "private":
            return "当前为私聊，无全局笔记，请保持user_id为空"

        # 根据传入的 user_id 类型路由到不同的笔记数据源
        if user_id == "global":
            raw_notes = self.note.get_global_notes(group_id)
        else:
            raw_notes = self.note.get_user_note(user_id, group_id)

        # 将原始列表复制出来以便操作
        temp_notes = raw_notes.copy()

        # 根据提示，把需要删除或修改的位置在当前副本上处理，用 None 占位防止索引发生位移
        for op in operations:
            action = op.get("action")
            index = op.get("index", -1)
            content = op.get("content", "")

            if action == "delete":
                if isinstance(index, int) and 0 <= index < len(temp_notes):
                    temp_notes[index] = None
            elif action == "replace":
                if isinstance(index, int) and 0 <= index < len(temp_notes):
                    temp_notes[index] = content
            elif action == "add":
                if index == -1 or not isinstance(index, int) or index >= len(temp_notes):
                    temp_notes.append(content)
                else:
                    temp_notes.insert(index, content)

        # 统一清理操作完毕后的 None 占位符
        new_notes = [b for b in temp_notes if b is not None]

        # 限制长度不超过20
        if len(new_notes) > 20:
            new_notes = new_notes[-20:]

        # 持久化保存
        self.note.set_user_note(user_id, group_id, new_notes)

        if not new_notes:
            return f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n（笔记已清空）"

        # 格式化输出返回给大模型
        note_str = '\n'.join([f"{i}.{j}" for i, j in enumerate(new_notes)])
        return f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n{note_str}"