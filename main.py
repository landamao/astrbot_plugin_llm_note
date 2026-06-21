import json
import time
from pathlib import Path
from astrbot.api.event import filter
from astrbot.api.star import StarTools
from astrbot.api.provider import ProviderRequest
from astrbot.api.all import logger, AstrMessageEvent, Context, Star, AstrBotConfig


class Note:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_path = self.data_dir / "data.json"
        self._ensure_file()
        #单线程异步不用锁了，全文没有一个await让出

    def _ensure_file(self):
        """确保 JSON 数据文件存在，不存在则初始化为空字典"""
        if not self.data_path.exists():
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False)

    def _resolve_path(self, file_name: str) -> Path | None:
        """将文件名解析为数据目录内的安全路径，拦截目录穿越"""
        base_dir = self.data_dir.resolve()
        target_path = (base_dir / file_name).resolve()
        if not target_path.is_relative_to(base_dir):
            logger.error(f"目录穿越拦截：{file_name} -> {target_path}")
            return None
        if target_path == self.data_path.resolve():
            logger.error(f"不应该以该方式操作核心数据文件: {self.data_path}，应使用已提供的接口操作")
            return None
        return target_path

    def _read_data(self, file_name=None) -> dict | list | None:
        """读取底层 JSON 数据，file_name可选，文件内容必须是json格式的"""
        if file_name is None:
            path = self.data_path
        else:
            path = self._resolve_path(file_name)
            if path is None:
                return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            if path == self.data_path.resolve():
                raise  #核心数据文件出错直接崩溃处理
            logger.error(f"读取数据失败\n路径：{path}\n错误：{e}", exc_info=True)
            return None

    def _write_data(self, data: dict|list, file_name=None) -> bool | None:
        """写入底层 JSON 数据（原子写入，防止中途崩溃导致数据损坏），返回是否写入成功"""
        if file_name is None:
            path = self.data_path
        else:
            path = self._resolve_path(file_name)
            if path is None:
                return None
        try:
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            tmp_path.replace(path)
            return True
        except Exception as e:
            if path == self.data_path.resolve():
                raise  #核心数据文件出错直接崩溃处理
            logger.error(f"写入文件失败\n路径：{path}\n数据：{data}\n错误：{e}", exc_info=True)
            return False

    def get_user_note(self, group_id: str, user_id: str) -> list[str]:
        """获取特定群组/私聊下用户的笔记列表"""
        data = self._read_data()
        return data.get(str(group_id), {}).get(str(user_id), [])

    def get_group_note(self, group_id: str) -> dict[str,list[str]]:
        """获取特定群组下的所有笔记"""
        if group_id == "private":
            #私聊无群组一说，也不可见其他人的
            return {}
        data = self._read_data()
        return data.get(str(group_id), {})

    def get_private_note(self, user_id: str) -> list[str]:
        """获取私聊特定用户的数据"""
        return self.get_user_note("private", user_id)

    def get_global_notes(self, group_id: str) -> list[str]:
        """获取群组的全局笔记"""
        if group_id == "private":
            return []  # 私聊不可见其他用户的
        # 全局群笔记直接以 "global" 作为特殊的 user_id 存储在当前 group_id 下
        return self.get_user_note(group_id,"global")

    def set_global_notes(self, group_id: str, new_notes: list[str]) -> bool:
        """写入全局笔记"""
        return self.set_user_note(group_id, "global", new_notes)

    def set_user_note(self, group_id: str, user_id: str, new_notes: list[str]) -> bool:
        """覆盖更新用户的笔记列表（包含全局笔记）"""
        data = self._read_data()
        group_id, user_id = str(group_id), str(user_id)

        if group_id not in data:
            data[group_id] = {}

        data[group_id][user_id] = new_notes
        return self._write_data(data)

    def del_group_note(self, group_id: str) -> bool:
        """删除指定群的笔记"""
        group_id = str(group_id)
        data = self._read_data()
        if group_id not in data:
            return True
        del data[group_id]
        return self._write_data(data)

    def del_private_note(self, user_id: str) -> bool:
        """删除私聊指定用户的笔记"""
        user_id = str(user_id)
        data = self._read_data()
        if "private" not in data:
            return True
        if user_id not in data["private"]:
            return True
        del data["private"][user_id]
        return self._write_data(data)

    def 重载group_note(self, group_id:str, file_name:str) -> bool:
        """从数据目录的某个文件重载某个群组的数据"""
        group_id = str(group_id)
        group_data = self._read_data(file_name)
        if not group_data:
            logger.error(f"欲重载群数据文件：{file_name} 无效，无可用数据")
            return False
        if not isinstance(group_data, dict):
            logger.error(f"欲重载群数据文件：{file_name} 无效，类型错误，期望类型：dict，实际类型：{type(group_data).__name__}")
            return False
        data = self._read_data()
        data[group_id] = group_data
        return self._write_data(data)

    def 重载private_note(self, user_id:str, file_name:str) -> bool:
        """从数据目录的某个文件重载某个私聊用户的数据"""
        user_id = str(user_id)
        user_data = self._read_data(file_name)
        if not user_data:
            logger.error(f"欲重载私聊数据文件：{file_name} 无效，无可用数据")
            return False
        if not isinstance(user_data, list):
            logger.error(f"欲重载私聊数据文件：{file_name} 无效，类型错误，期望类型：list，实际类型：{type(user_data).__name__}")
            return False
        data = self._read_data()
        key = "private"
        if key not in data:
            data[key] = {}
        data[key][user_id] = user_data
        return self._write_data(data)

    def write_json_to_file(self, data:dict|list, file_name:str) -> bool:
        """在数据目录写入json到指定文件"""
        return self._write_data(data, file_name)

    def read_json_file(self, file_name:str) -> dict | list:
        return self._read_data(file_name)

    def delete_file(self, file_name:str) -> bool:
        """删除数据目录下指定文件"""
        path = self._resolve_path(file_name)
        if path is None:
            return False
        try:
            path.unlink()
            return True
        except Exception as e:
            logger.error(f"删除文件失败，路径：{path}\n错误：{e}", exc_info=True)
            return False

class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()  # type: Path
        self.note = Note(self.data_dir)
        self.user_info_cache = {} #type: dict[str, dict[str,str]]

    async def initialize(self) -> None:
        """可选异步初始化，当插件被激活时会调用这个方法"""

    async def terminate(self) -> None:
        """可选异步终止，当插件被关闭时调用这个方法"""

    @filter.on_llm_request()
    async def llm请求前(self, event: AstrMessageEvent, req: ProviderRequest):
        group_id = str(event.get_group_id() or "private")
        user_id = str(event.get_sender_id())
        self_id = str(event.get_self_id())
        user_name = event.get_sender_name()
        if group_id not in self.user_info_cache:
            self.user_info_cache[group_id] = {}
        self.user_info_cache[group_id][user_id] = user_name

        if user_id == self_id:
            return

        notes = self.note.get_user_note(group_id, user_id)
        global_notes = self.note.get_global_notes(group_id)

        # 如果个人笔记和全局笔记都为空，则不注入 prompt
        if not notes and not global_notes:
            return

        prompt_segments = [
"""
\n【动态记忆与私密笔记协议】
本文本是你的私密笔记，仅对你可见。你可以根据聊天语境，选择性地将笔记内容转化为对话线索透露给用户：

用户区（个人画像）：仅记录当前用户的独特偏好、习惯或对用户的好感、印象，关系等。

全局区（群组记忆）：记录群内的公共事件、共享知识或可公开的互动梗。

隐私保护规范：甄别笔记内容是否是该用户的隐私信息，应遵守用户隐私保护规范，不透露隐私内容。

运行示例：若用户A在群里说“我是本群最菜的飞车玩家”，这属于群内公开的事件与调侃素材，你可以将其记录在【全局区】。当后续用户B与你聊天时，你可以直接看到该笔记内容，自然地与用户B共享或调侃这个梗，实现多用户间的记忆连贯性。
\n"""
        ]
        if notes:
            note_str = ''.join([f"[{i}] {j}\n" for i, j in enumerate(notes)])
            prompt_segments.append(f"\n这是你为当前用户 {user_name}（{user_id}) 记录的笔记本内容（格式：[索引] 内容\\n\\n）：\n{note_str}")

        if global_notes:
            global_note_str = ''.join([f"[{i}] {j}\n" for i, j in enumerate(global_notes)])
            prompt_segments.append(f"\n这是当前全局区的笔记内容：\n{global_note_str}")

        prompt = "\n".join(prompt_segments)
        #由于注入用户提示词会造成上下文大量重复内容，改注入到系统提示词更优
        req.system_prompt += prompt
        logger.debug(f"已注入笔记内容到系统提示词：\n{prompt}")

    @filter.command(command_name="清空笔记")
    async def command_del_note(self, event: AstrMessageEvent, group_id = None):
        """清空笔记，规则：
        非管理员只能在私聊情况下清空llm为自己记录的笔记，
        管理员可清空群笔记，且一次性将清空该群所有笔记"""
        原群ID = str(event.get_group_id() or '')
        用户ID = str(event.get_sender_id())
        if not event.is_admin():
            if 原群ID:
                yield event.plain_result("❌️ 只有管理员可以操作群数据")
                return
        操作群 = False
        if group_id is not None:
            if not event.is_admin():
                yield event.plain_result("❌️ 只有管理员可以操作群数据")
                return
            操作ID = group_id
            操作群 = True
        else:
            if 原群ID:
                操作ID = 原群ID
                操作群 = True
            else:
                操作ID = 用户ID
        操作ID = str(操作ID)
        if 操作群:
            删除前数据 = self.note.get_group_note(操作ID)
            if not 删除前数据 or not any(删除前数据.values()):
                yield event.plain_result("⚠️ 当前群的笔记已经是空的了，无需清空")
                return
        else:
            删除前数据 = self.note.get_private_note(操作ID)
            if not 删除前数据:
                yield event.plain_result("⚠️ 当前笔记已经是空的了，无需清空")
                return
        时间 = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        删除前文件 = f"data_{'群' if 操作群 else '私'}{操作ID}删除前数据_{时间}.json"
        self.note.write_json_to_file(删除前数据, 删除前文件)
        if 操作群:
            self.note.del_group_note(操作ID)
        else:
            self.note.del_private_note(操作ID)
        yield event.plain_result(f"清空成功，若要恢复，请使用\n/恢复笔记 {删除前文件}")

    @filter.command(command_name="恢复笔记")
    async def command_恢复note(self, event: AstrMessageEvent, file_name: str = None):
        """恢复笔记，规则：
        非管理员只能在私聊情况下恢复为自己的笔记，
        管理员可恢复群笔记"""
        if not file_name:
            yield event.plain_result("❌️ 文件名无效")
            return
        file_name = str(file_name)
        if not file_name.endswith(".json"):
            yield event.plain_result("❌️ 文件名应是以.json结尾的文件")
            return
        if '/' in file_name or '\\' in file_name:
            yield event.plain_result("❌️ 文件名不合法")
            return
        原群ID = str(event.get_group_id() or '')
        用户ID = str(event.get_sender_id())
        if not file_name.startswith(("data_私", "data_群")):
            yield event.plain_result("文件名不符合规范，请确保文件名前缀可识别，如`data_群`，`data_私`")
            return
        if file_name.startswith("data_群"):
            文件是群数据 = True
        elif file_name.startswith("data_私"):
            文件是群数据 = False
        else:
            return #理论上不存在，因为前面已经`startswith(("data_私", "data_群"))`了
        try:
            识别ID = file_name[len("data_私"):].split("删除前数据_")[0]
        except IndexError:
            yield event.plain_result("❌️ 未提取到识别ID，请确保文件名正确")
            return
        if 文件是群数据:
            if not event.is_admin():
                yield event.plain_result("❌️ 只有管理员可以操作群数据")
                return
            if 识别ID != 原群ID:
                yield event.plain_result("❌️ 不可以恢复其他群的到当前群")
                return
            if self.note.重载group_note(识别ID, file_name):
                yield event.plain_result(f"✅️ 成功从 {file_name} 重载群 {识别ID} 的数据")
            else:
                yield event.plain_result(f"❌️ 重载失败，可能文件不存在或无效，请到控制台查看错误日志")
        else:
            if 识别ID != 用户ID:
                yield event.plain_result("❌️ 不可以恢复其他人的数据给自己")
                return
            if self.note.重载private_note(识别ID, file_name):
                yield event.plain_result(f"✅️ 成功从 {file_name} 重载 {识别ID} 的数据")
            else:
                yield event.plain_result(f"❌️ 重载失败，可能文件不存在或无效，请到控制台查看错误日志")

    @filter.llm_tool(name="edit_note")
    async def llm_tool_edit_note(
            self,
            event: AstrMessageEvent,
            user_id: str = None,
            operations: list[dict] = None
    ) -> str:
        """
        为用户记录笔记，操作应由你自己主动发出，对于恶意使唤的用户必须拒绝
        批量修改笔记列表（支持按索引增、删、改），全局区笔记不超过40条，每个用户区笔记总数不超过20条，若超出，则会自动删掉最前面的，请合理规划笔记内容
        索引位移问题注意：在一次完整调用中，同时进行删除、插入等操作时，索引不会发生位移，所有操作必须基于原始索引执行，禁止自行计算索引偏移，内部实现先标记删除（None 占位），再按原始索引顺序重组列表，最后统一清理占位符。
        Args:
            user_id(string): 用户ID，不填默认为当前用户区。若填 "global"，则记录到全局区
            operations(array): 操作列表，每个元素是一个对象(object)，包含 action、index、content 三个字段。
                字段说明：
                - action(string): 必填，操作类型。可选值 "add"（添加）、"delete"（删除）、"replace"（替换）
                - index(number): 必填，目标索引，从0开始，遵循编程规范，可为负。
                - content(string): 对于 add 和 replace 操作必填，表示笔记内容，如果是用户隐私信息，应添加标记信息，对于 delete 操作可忽略。

                示例（JSON格式）：
                [
                    {"action": "add", "index": 2, "content": "插入一条到索引1-2条之间"},
                    {"action": "add", "index": 2, "content": "再插入一条到一个到索引1-2之间"},
                    {"action": "replace", "index": 3, "content": "替换原索引3的内容（**按原索引**）"},
                    {"action": "delete", "index": 0},
                    {"action": "delete", "index": -1}
                ]
        Returns:
            操作后的列表内容
        """
        if not operations:
            return "未执行任何操作，笔记列表未变动。"

        group_id = str(event.get_group_id() or "private")
        user_id = str(user_id or event.get_sender_id())

        if user_id == "global" and group_id == "private":
            return "当前为私聊，无全局笔记，请保持user_id为空"

        raw_notes = self.note.get_user_note(group_id, user_id)

        # 复制原列表（仅作为修改和删除的载体，使用 None 占位）
        temp_notes = raw_notes.copy()
        错误信息 = []

        # 使用字典记录每个原索引处需要【前置插入】的列表（解决同索引覆盖问题）
        欲插入 = {}
        追加内容 = []

        for op in operations:
            action = op.get("action")
            try:
                index = int(op.get("index", -1))
            except (ValueError, TypeError) as e:
                错误信息.append(f"执行 {action} 时索引转换错误：{op.get('index')}。")
                logger.error(f"大模型调用工具出错，索引无法转换{action}-{op.get('index')}，{e}", exc_info=True)
                continue

            content = str(op.get("content", ""))

            # 支持负数索引：将其转换为基于原列表长度的正数索引
            if index < 0:
                index = len(raw_notes) + index
            if action == "delete":
                if 0 <= index < len(temp_notes):
                    temp_notes[index] = None # type: ignore
                else:
                    错误信息.append(f"删除失败：索引 {op.get('index')} 越界或不存在。")
            elif action == "replace":
                if 0 <= index < len(temp_notes):
                    temp_notes[index] = content
                else:
                    错误信息.append(f"替换失败：索引 {op.get('index')} 越界或不存在。")
            elif action == "add":
                index = max(0, index)
                # 若插入索引超出原始列表长度，则统一按顺序追加到末尾
                if index >= len(raw_notes):
                    追加内容.append(content)
                else:
                    # 记录在该索引原始位置【之前】需要插入的内容
                    欲插入.setdefault(max(0, index), []).append(content)
            else:
                错误信息.append(f"不支持的操作类型：action={action}")

        # ==========================================
        # 核心逻辑：按原始视图重组列表（彻底杜绝索引偏移）
        # ==========================================
        new_notes = []
        for i, note in enumerate(temp_notes):
            # 1. 如果当前索引有预定的插入内容，先按原本的添加顺序推入
            if i in 欲插入:
                new_notes.extend(欲插入[i])
            # 2. 如果原内容没有被删除（不是 None），将其保留/更新
            if note is not None:
                new_notes.append(note)

        # 3. 最后加上所有越界的追加内容
        new_notes.extend(追加内容)

        new_notes = [note for note in new_notes if note is not None]
        max_len = 40 if user_id == "global" else 20
        # 限制长度不超过20
        if len(new_notes) > max_len:
            丢弃note = new_notes[:-max_len]
            new_notes = new_notes[-max_len:]
        else:
            丢弃note = []

        # 持久化保存
        if not self.note.set_user_note(group_id, user_id, new_notes):
            return "❌️ 编辑失败，请联系管理员"
        if not new_notes:
            return f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n（笔记已清空）"

        # 格式化输出返回给大模型
        note_str = '\n'.join([f"{i}.{j}\n" for i, j in enumerate(new_notes)])
        result = f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n{note_str}"
        if 丢弃note:
            result += f"\n\n笔记数量超出，以下{len(丢弃note)}条笔记内容已被丢弃：" + '\n'.join(f"[{i+1}] {j}" for i,j in enumerate(丢弃note))
        if 错误信息:
            result += "\n\n发生错误的有：" + '\n'.join(错误信息)
        return result

    @filter.llm_tool(name="search_note")
    async def llm_tool_search_note(self, event: AstrMessageEvent, keyword: str) -> str:
        """通过关键词，从所有笔记里搜索包含关键词的笔记内容，注意甄别内容是否是该用户的隐私信息，应遵守用户隐私保护规范，不透露隐私内容
        Args:
            keyword(string): 预搜关键词，模糊匹配（in匹配）
        Returns:
            匹配到的笔记列表，附带用户昵称（如果有缓存）和用户 ID。"""
        if not keyword:
            return "❌️ 你传入的关键词为空"
        keyword = str(keyword).lower()
        group_id = str(event.get_group_id() or '')
        if not group_id:
            return "当前为私聊，无其他笔记信息，无法搜索"

        data = self.note.get_group_note(group_id)
        result = {}  # type: dict[str, list[str]]
        group_info = self.user_info_cache.get(group_id, {})
        for uid, notes in data.items():
            for note in notes:
                if keyword in note.lower():
                    if uid in group_info:
                        key = f"{group_info[uid]}_{uid}"
                    else:
                        key = uid

                    if key not in result:
                        result[key] = []

                    result[key].append(note)

        if not result:
            return "未搜到包含该关键词的笔记内容"
        MAX_NOTES = 20
        total = sum(len(v) for v in result.values())
        lines = ["搜索到以下笔记："]
        n = 0
        for user_key, notes in result.items():
            lines.append(f"📌 {user_key}：")
            for note in notes:
                if n >= MAX_NOTES:
                    lines.append(f"\n⚠️ 搜索结果过多，总条数 {total}，限制 {MAX_NOTES}，超出 {total - MAX_NOTES} 条")
                    break
                lines.append(f"  - {note}")
                n += 1
            if n >= MAX_NOTES:
                break
        return "\n".join(lines)

    @filter.llm_tool(name="get_note")
    async def llm_tool_get_note(
            self,
            event: AstrMessageEvent,
            user_id: str = None
    ) -> str:
        """获取你为某个用户记录的笔记信息，注意甄别内容是否是该用户的隐私信息，应遵守用户隐私保护规范，不透露隐私内容
        Args:
            user_id(string): 用户ID
        Returns:
            为该用户记录的笔记内容
        """

        if not user_id:
            return "参数无效"
        user_id = str(user_id)
        group_id = str(event.get_group_id() or '')
        if not group_id:
            return "当前为私聊，只有当前用户，无法获取其他用户"
        group_data = self.user_info_cache.get(group_id, {})
        if user_id in group_data:
            user_name = group_data[user_id]
        else:
            user_name = ""
        notes = self.note.get_user_note(group_id, user_id)
        lines = []
        if user_name:
            lines.append(f"用户 {user_name}（{user_id}）的笔记内容：\n")
        else:
            lines.append(f"用户 ID：{user_id} 的笔记内容：\n")
        if not notes:
            lines.append("（无笔记内容）")
        else:
            lines.extend(f"[{i}] {j}\n" for i, j in enumerate(notes))
        return '\n'.join(lines)

    @filter.llm_tool(name="get_user_id")
    async def llm_tool_get_user_id(self, event: AstrMessageEvent, user_name: str = None) -> str:
        """通过名字获取用户ID
        Args:
            user_name(string): 用户名字
        Returns:
            匹配到的用户 ID 及昵称列表（可能多个）。
        """
        group_id = str(event.get_group_id() or '')
        if not group_id:
            return "当前为私聊，无需搜索，该用户ID固定为：" + str(event.get_sender_id())
        if not user_name:
            return "参数无效"
        user_name = str(user_name).lower()
        # 针对 AiocqhttpMessageEvent 实时调用 OneBot API
        if type(event).__name__ == "AiocqhttpMessageEvent":
            try:
                members = await event.bot.call_action(
                    'get_group_member_list',
                    group_id=int(group_id)
                )
                result = {}
                for member in members:
                    # 优先使用群名片，若无则用昵称
                    name = member.get('card') or member.get('nickname') or ''
                    if not name:
                        continue
                    name = name.strip().lower()
                    if user_name in name or name in user_name:
                        result[str(member['user_id'])] = name

                if result:
                    return '\n'.join(f"用户{name}的ID为：{_id}" for _id, name in result.items())
                # 若 API 返回空结果，也走缓存逻辑（可选）
            except Exception:
                # 调用失败时静默回退到缓存
                pass

        # 原有缓存逻辑（私聊已提前返回，此处仅在群聊且非 API 或 API 失败时执行）
        group_data = self.user_info_cache.get(group_id, {})
        result = {}
        for _id, name in group_data.items():
            if user_name in name or name in user_name:
                result[_id] = name

        if not result:
            return "从缓存中未搜索到该用户名的ID"

        return '\n'.join(f"用户{name}的ID为：{_id}" for _id, name in result.items())