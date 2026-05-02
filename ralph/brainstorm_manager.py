from pathlib import Path
import json
from ralph.schema.brainstorm_record import (
    BrainstormRecord, ConfirmedFact, OpenAssumption, UserPath, _now_iso,
)


class BrainstormManager:
    """多轮需求共创管理器。每轮对话产出 BrainstormRecord，持久化到 .ralph/brainstorm/"""

    TOPICS_TO_COVER = [
        "目标用户", "用户角色", "核心功能", "暂不做的功能",
        "成功路径", "失败路径", "边界状态", "验收标准",
        "数据模型概要", "权限规则",
    ]

    def __init__(self, ralph_dir: Path):
        self._dir = ralph_dir / "brainstorm"
        self._dir.mkdir(parents=True, exist_ok=True)

    def start_session(self, project_name: str, user_message: str) -> BrainstormRecord:
        record = BrainstormRecord(
            record_id=f"bs-{_now_iso().replace(':', '-')}",
            project_name=project_name,
            round_number=1,
            user_message=user_message,
        )
        self._save(record)
        return record

    def generate_questions(self, record: BrainstormRecord) -> list[str]:
        """分析当前记录，生成下一轮要追问的问题。"""
        questions = []
        covered = {f.topic for f in record.confirmed_facts}

        for topic in self.TOPICS_TO_COVER:
            if topic not in covered:
                questions.append(self._question_for_topic(topic))

        if not questions:
            for assumption in record.open_assumptions:
                if assumption.status == "open":
                    questions.append(f"关于「{assumption.question}」，你的判断是？")

        return questions[:5]

    def process_response(self, record: BrainstormRecord,
                         user_response: str,
                         extracted_facts: list[dict] | None = None,
                         ) -> BrainstormRecord:
        record.round_number += 1
        record.user_message = user_response

        if extracted_facts:
            for fact_data in extracted_facts:
                if fact_data.get("type") == "confirmed":
                    record.confirmed_facts.append(ConfirmedFact(
                        topic=fact_data["topic"],
                        fact=fact_data["fact"],
                        source_quote=fact_data.get("source_quote", user_response),
                    ))
                elif fact_data.get("type") == "assumption":
                    record.open_assumptions.append(OpenAssumption(
                        question=fact_data["question"],
                        context=fact_data.get("context", ""),
                    ))
                elif fact_data.get("type") == "user_path":
                    record.user_paths.append(UserPath(
                        name=fact_data["name"],
                        steps=fact_data.get("steps", []),
                        edge_cases=fact_data.get("edge_cases", []),
                    ))

        self._save(record)
        return record

    def is_complete(self, record: BrainstormRecord) -> bool:
        return (record.completeness_score() >= 0.8
                and len(record.open_assumptions) == 0)

    def get_summary(self, record: BrainstormRecord) -> dict:
        return {
            "project_name": record.project_name,
            "total_rounds": record.round_number,
            "completeness": record.completeness_score(),
            "confirmed_facts": [
                {"topic": f.topic, "fact": f.fact} for f in record.confirmed_facts
            ],
            "open_assumptions": [
                {"question": a.question, "status": a.status}
                for a in record.open_assumptions
            ],
            "user_paths": [
                {"name": p.name, "steps": p.steps, "edge_cases": p.edge_cases}
                for p in record.user_paths
            ],
        }

    def list_sessions(self) -> list[dict]:
        records = []
        for f in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                records.append({
                    "record_id": data.get("record_id", f.stem),
                    "project_name": data.get("project_name", ""),
                    "round_number": data.get("round_number", 0),
                    "completeness": BrainstormRecord(**data).completeness_score(),
                    "created_at": data.get("created_at", ""),
                })
            except Exception:
                continue
        return records

    def load(self, record_id: str) -> BrainstormRecord | None:
        path = self._dir / f"{record_id}.json"
        if not path.is_file():
            return None
        return BrainstormRecord(**json.loads(path.read_text()))

    def _save(self, record: BrainstormRecord) -> None:
        path = self._dir / f"{record.record_id}.json"
        path.write_text(json.dumps(
            {k: v for k, v in record.__dict__.items() if not k.startswith("_")},
            indent=2, ensure_ascii=False, default=str,
        ))

    @staticmethod
    def _question_for_topic(topic: str) -> str:
        questions = {
            "目标用户": "这个产品给谁用？请描述目标用户画像。",
            "用户角色": "有哪些不同的用户角色？每个角色能做什么？",
            "核心功能": "第一版必须有哪些功能？按重要性排序。",
            "暂不做的功能": "有哪些功能明确不做（至少第一版不做）？",
            "成功路径": "用户最常见的成功使用流程是什么？",
            "失败路径": "当用户操作失败时，系统应该如何响应？",
            "边界状态": "极端或异常状态下系统应该如何表现？",
            "验收标准": "你怎么判断这个产品'真的可以用了'？",
            "数据模型概要": "系统需要存储哪些核心数据？",
            "权限规则": "有哪些权限控制需求？",
        }
        return questions.get(topic, f"请详细说明「{topic}」方面的需求。")
