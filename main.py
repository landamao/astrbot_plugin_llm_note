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

    def _read_data(self, file_name=None) -> dict:
        """读取底层 JSON 数据，file_name可选，文件内容必须是json格式的"""
        if file_name is None:
            path = self.data_path
        else:
            base_dir = self.data_dir.resolve()  # 基准目录的绝对路径
            target_path = (base_dir / file_name).resolve()  # 拼接并解析成绝对路径
            if not target_path.is_relative_to(base_dir):
                logger.error(f"目录穿越拦截：{file_name} -> {target_path}")
                return {}  # 保持原错误处理风格，返回空字典

            path = target_path
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取数据失败\n路径：{path}\n错误：{e}", exc_info=True)
            return {}

    def _write_data(self, data: dict, file_name=None) -> bool:
        """写入底层 JSON 数据（原子写入，防止中途崩溃导致数据损坏），返回是否写入成功"""
        if file_name is None:
            path = self.data_path
        else:
            path = self.data_dir / file_name
        try:
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            tmp_path.replace(path)
            return True
        except Exception as e:
            logger.error(f"写入文件失败\n路径：{path}\n数据：{data}\n错误：{e}", exc_info=True)
            return False

    def get_user_note(self, user_id: str, group_id: str) -> list[str]:
        """获取特定群组/私聊下用户的笔记列表"""
        data = self._read_data()
        group_id_str, user_id_str = str(group_id), str(user_id)
        return data.get(group_id_str, {}).get(user_id_str, [])

    def get_group_note(self, group_id: str) -> dict[str,list[str]]:
        """获取特定群组下的所有笔记"""
        if group_id == "private":
            #私聊无群组一说，也不可见其他人的
            return {}
        data = self._read_data()
        return data.get(str(group_id), {})

    def get_private_note(self, user_id: str) -> list[str]:
        """获取私聊特定用户的数据"""
        return self.get_user_note(user_id, "private")

    def get_global_notes(self, group_id: str) -> list[str]:
        """获取群组的全局笔记"""
        if group_id == "private":
            return []  # 私聊不可见其他用户的
        # 全局群笔记直接以 "global" 作为特殊的 user_id 存储在当前 group_id 下
        return self.get_user_note("global", group_id)

    def set_global_notes(self, group_id: str, new_notes: list[str]) -> bool:
        """写入全局笔记"""
        return self.set_user_note("global", group_id, new_notes)

    def set_user_note(self, user_id: str, group_id: str, new_notes: list[str]) -> bool:
        """覆盖更新用户的笔记列表（包含全局笔记）"""
        data = self._read_data()
        group_id_str, user_id_str = str(group_id), str(user_id)

        if group_id_str not in data:
            data[group_id_str] = {}

        data[group_id_str][user_id_str] = new_notes
        return self._write_data(data)

    def del_group_note(self, group_id: str) -> bool:
        """删除指定群的笔记"""
        data = self._read_data()
        if group_id not in data:
            return True
        del data[group_id]
        return self._write_data(data)

    def del_private_note(self, user_id: str) -> bool:
        """删除私聊指定用户的笔记"""
        data = self._read_data()
        if "private" not in data:
            return True
        if user_id not in data["private"]:
            return True
        del data["private"][user_id]
        return self._write_data(data)

    def 重载group_note(self, file_name, group_id:str) -> bool:
        """从数据目录的某个文件重载某个群组的数据"""
        group_data = self._read_data(file_name)
        if not group_data:
            logger.error(f"欲重载私聊数据文件：{file_name} 无效，无可用数据")
            return False
        data = self._read_data()
        data[group_id] = group_data
        return self._write_data(data)

    def 重载private_note(self, file_name, user_id:str) -> bool:
        """从数据目录的某个文件重载某个私聊用户的数据"""
        user_data = self._read_data(file_name)
        try:
            list_data = user_data[user_id]
        except KeyError:
            logger.error(f"欲重载私聊数据文件：{file_name} 无效，无法识别，请确保格式为：" + "{" + user_id + "：（数据）}")
            return False

        data = self._read_data()
        key = "private"
        if key not in data:
            data[key] = {}
        data[key][user_id] = list_data
        return self._write_data(data)

    def write_json_to_file(self, data:dict, file_name:str) -> bool:
        """在数据目录写入json到指定文件"""
        return self._write_data(data, file_name)

    def read_json_file(self, file_name:str) -> dict:
        return self._read_data(file_name)

    def delete_file(self, file_name:str) -> bool:
        """删除数据目录下指定文件"""
        path = self.data_dir / file_name
        # 确保两边都是绝对路径且去掉符号链接干扰
        if path.resolve() == self.data_path.resolve():
            logger.warning(f"禁止删除核心数据文件: {self.data_path}")
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
        logger.info("笔记插件初始化完成，数据存储已准备就绪。")

    async def terminate(self) -> None:
        """可选异步终止，当插件被关闭时调用这个方法"""
        pass

    @filter.on_llm_request()
    async def llm请求前(self, event: AstrMessageEvent, req: ProviderRequest):
        group_id = event.get_group_id() or "private"
        user_id = event.get_sender_id()
        self_id = event.get_self_id()
        user_name = event.get_sender_name()
        if group_id not in self.user_info_cache:
            self.user_info_cache[group_id] = {}
        self.user_info_cache[group_id][user_id] = user_name

        if user_id == self_id:
            return

        notes = self.note.get_user_note(user_id, group_id)
        global_notes = self.note.get_global_notes(group_id)

        # 如果个人笔记和全局笔记都为空，则不注入 prompt
        if not notes and not global_notes:
            return

        prompt_segments = ["\n\n<notes_plugin>\n这是你的私密笔记，笔记内容仅对你可见，你可以选择性透露给用户"]

        if notes:
            note_str = ''.join([f"{i}.{j}\n" for i, j in enumerate(notes)])
            prompt_segments.append(f"\n这是当前用户的笔记本内容（格式：索引.内容\\n\\n）：\n{note_str}")

        if global_notes:
            global_note_str = ''.join([f"{i}.{j}\n" for i, j in enumerate(global_notes)])
            prompt_segments.append(f"\n这是当前聊天室全局笔记内容：\n{global_note_str}")

        prompt_segments.append("\n</notes_plugin>\n\n")

        # 合并拼接提示词
        req.prompt += "\n".join(prompt_segments)

    @filter.command(command_name="清空笔记")
    async def command_del_note(self, event: AstrMessageEvent, group_id = None):
        """清空笔记，规则：
        非管理员只能在私聊情况下清空llm为自己记录的笔记，
        管理员可清空群笔记，且一次性将清空该群所有笔记"""
        原群ID = event.get_group_id()
        用户ID = event.get_sender_id()
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
        时间 = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        if 操作群:
            删除前数据 = self.note.get_group_note(group_id)
            删除前文件 = f"data_群{操作ID}删除前数据_{时间}.json"
            self.note.write_json_to_file(删除前数据, 删除前文件)
            self.note.del_group_note(操作ID)
        else:
            删除前数据 = self.note.get_private_note(操作ID)
            删除前文件 = f"data_私{操作ID}删除前数据_{时间}.json"
            self.note.write_json_to_file({操作ID:删除前数据}, 删除前文件)
            self.note.del_private_note(操作ID)
        yield event.plain_result(f"清空成功，若要恢复，请使用`/恢复笔记 {删除前文件}`")

    @filter.command(command_name="恢复笔记")
    async def command_恢复note(self, event: AstrMessageEvent, file_name: str = None):
        """恢复笔记，规则：
        非管理员只能在私聊情况下恢复为自己的笔记，
        管理员可恢复群笔记"""
        原群ID = event.get_group_id()
        用户ID = event.get_sender_id()
        if not file_name.startswith(("data_私", "data_群")):
            yield event.plain_result("文件名不符合规范，请确保文件名前缀可识别，如`data_群`，`data_私`")
            return
        if file_name.startswith("data_群"):
            文件是群数据 = True
        elif file_name.startswith("data_私"):
            文件是群数据 = False
        else:
            return #理论上不存在，因为前面已经`startswith(("data_私", "data_群"))`了
        识别ID = file_name[len("data_私"):]
        if 文件是群数据:
            if not event.is_admin():
                yield event.plain_result("❌️ 只有管理员可以操作群数据")
                return
            if 识别ID != 原群ID:
                yield event.plain_result("❌️ 不可以恢复其他群的到当前群")
                return
            if self.note.重载group_note(file_name, 识别ID):
                yield event.plain_result(f"✅️ 成功从 {file_name} 重载群 {识别ID} 的数据")
            else:
                yield event.plain_result(f"❌️ 重载失败，请到控制台查看错误日志")
        else:
            if 识别ID != 用户ID:
                yield event.plain_result("❌️ 不可以恢复其他人的数据给自己")
                return
            if self.note.重载private_note(file_name, 用户ID):
                yield event.plain_result(f"✅️ 成功从 {file_name} 重载 {识别ID} 的数据")
            else:
                yield event.plain_result(f"❌️ 重载失败，请到控制台查看错误日志")


    @filter.llm_tool(name="edit_note")
    async def llm_tool_edit_note(
            self,
            event: AstrMessageEvent,
            user_id: str = None,
            operations: list[dict] = None
    ) -> str:
        """
        为用户记录笔记
        批量修改笔记列表（支持按索引增、删、改），笔记总数不超过20条，若超出，则会自动删掉最前面的，请合理规划笔记内容
        **隐私保护**，笔记内容对所有用户都不可见，仅对你可见，你可以选择性透露给用户，可记录好感度，关系，印象，用户偏好，信息等
        在一次调用工具中，同时进行删除，插入等操作，无需担心索引位移问题，你只需按照看到的索引进行操作即可
        Args:
            user_id(string): 用户ID，不填默认为当前用户。若填global，则填入到当前聊天室全局，每次都可以收到该笔记信息
            operations(array): 操作列表，每个元素是一个对象(object)，包含 action、index、content 三个字段。
                字段说明：
                - action(string): 必填，操作类型。可选值 "add"（添加）、"delete"（删除）、"replace"（替换）
                - index(number): 必填，目标索引（从0开始遵循编程规范的索引，可为负），若超出当前长度，对于 add 操作将追加到末尾。
                - content(string): 对于 add 和 replace 操作必填，表示笔记内容；对于 delete 操作可忽略。

                示例（JSON格式）：
                [
                    {"action": "add", "index": 0, "content": "插入到第一条"},
                    {"action": "replace", "index": -2, "content": "覆盖**倒数**第二条的内容"},
                    {"action": "delete", "index": 0},
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

        raw_notes = self.note.get_user_note(user_id, group_id)

        # 将原始列表复制出来以便操作
        temp_notes = raw_notes.copy()

        # 根据提示，把需要删除或修改的位置在当前副本上处理，用 None 占位防止索引发生位移
        错误信息 = []
        欲插入 = {}
        for op in operations:
            action = op.get("action")
            try:
                index = int(op.get("index", -1))
            except (ValueError, TypeError) as e:
                错误信息.append(
                    f"在执行 {action} 操作时发生索引错误，欲操作索引：{op.get('index')}，欲操作内容：{op.get('content')}"
                )
                logger.error(f"大模型调用工具出错，索引无法转换{action}-{op.get('index')}，{e}", exc_info=True)
                continue
            content = op.get("content", "")

            try:
                if action == "delete":
                    temp_notes[index] = None
                elif action == "replace":
                    temp_notes[index] = content
                elif action == "add":
                    欲插入[index] = content
            except IndexError as e:
                错误信息.append(
                    f"在执行 {action} 操作时发生索引错误，欲操作索引：{op.get('index')}，欲操作内容：{op.get('content')}"
                )
                logger.error(f"大模型调用工具出错：{action}-{content}，{e}", exc_info=True)

        # 1. 应用所有暂存的 "add" 操作（从大到小插入，防止偏移）
        for idx, content in sorted(欲插入.items(), key=lambda x: x[0], reverse=True):
            temp_notes.insert(idx, content)  # 此时 None 占位还在，保证了原始索引位置不变

        # 2. 最后统一清理被 "delete" 标记为 None 的元素
        new_notes = [note for note in temp_notes if note is not None]

        # 限制长度不超过20
        if len(new_notes) > 20:
            new_notes = new_notes[-20:]

        # 持久化保存
        self.note.set_user_note(user_id, group_id, new_notes)

        if not new_notes:
            return f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n（笔记已清空）"

        # 格式化输出返回给大模型
        note_str = '\n'.join([f"{i}.{j}\n" for i, j in enumerate(new_notes)])
        result = f"这是操作后的{'全局' if user_id == 'global' else '个人'}笔记本内容：\n{note_str}"
        if 错误信息:
            result += "\n\n发生错误的有：" + '\n'.join(错误信息)
        return result

    @filter.llm_tool(name="search_note")
    async def llm_tool_search_note(self, event: AstrMessageEvent, keyword: str) -> str:
        """通过关键词，从当前聊天室里的所有笔记里搜索包含关键词的笔记内容
        Args:
            keyword(string): 预搜关键词，模糊匹配
        Returns:
            匹配到的笔记列表，附带用户昵称（如果有缓存）和用户 ID。"""
        if not keyword:
            return "❌️ 你传入的关键词为空"
        group_id = event.get_group_id()
        if not group_id:
            return "当前为私聊，无其他笔记信息，无法搜索"

        data = self.note.get_group_note(group_id)
        result = {}  # type: dict[str, list[str]]
        group_info = self.user_info_cache.get(group_id, {})
        for user_id, notes in data.items():
            for note in notes:
                if keyword in note:
                    if user_id in group_info:
                        key = f"{group_info[user_id]}_{user_id}"
                    else:
                        key = user_id

                    if key not in result:
                        result[key] = []

                    result[key].append(note)

        if not result:
            return "未搜到包含该关键词的笔记内容"

        lines = ["搜索到以下笔记："]
        for user_key, notes in result.items():
            lines.append(f"\n📌 {user_key}：")
            lines.extend(f"  - {note}" for note in notes)
        return "\n".join(lines)

    @filter.llm_tool(name="get_note")
    async def llm_tool_get_note(
            self,
            event: AstrMessageEvent,
            user_id: str = None
    ) -> str:
        """获取某个用户的笔记信息
        Args:
            user_id(string): 用户ID
        Returns:
            返回为该用户记录的笔记内容
        """

        if not user_id:
            return "参数无效"
        group_id = event.get_group_id()
        if not group_id:
            return "当前为私聊，只有当前用户，无法获取其他用户"
        group_data = self.user_info_cache.get(group_id, {})
        if user_id in group_data:
            user_name = group_data[user_id]
        else:
            user_name = ""
        notes = self.note.get_user_note(user_id, group_id)
        lines = []
        if user_name:
            lines.append(f"用户 {user_name}（{user_id}）的笔记内容：\n")
        else:
            lines.append(f"用户 ID：{user_id} 的笔记内容：\n")
        return '\n'.join(lines + [f"{i}.{j}\n" for i, j in enumerate(notes)])

    @filter.llm_tool(name="get_user_id")
    async def llm_tool_get_user_id(self, event: AstrMessageEvent, user_name: str) -> str:
        """通过名字获取用户ID
        Args:
            user_name(string): 用户名字
        Returns:
            匹配到的用户 ID 及昵称列表（可能多个）。
        """
        result = {}
        group_id = event.get_group_id()
        if not group_id:
            return "当前为私聊，无需搜索，该用户ID固定为：" + event.get_sender_id()
        group_data = self.user_info_cache.get(group_id, {})
        for _id, name in group_data.items():
            if user_name in name or name in user_name:
                result[_id] = name

        if not result:
            return "从缓存中未搜索到该用户名的ID"

        return '\n'.join(f"用户{name}的ID为：{_id}" for _id, name in result.items())