from __future__ import annotations

from pathlib import Path

from backend.prompting.examples_loader import load_idle_examples, load_tracking_examples
from backend.types import AudienceFeatures

HEIGHT_LABELS = {"tall": "高個", "medium": "中等身高", "short": "矮個", "unknown": "身高未明"}
BUILD_LABELS = {"broad": "厚實體型", "average": "普通體型", "slim": "偏瘦體型", "unknown": "體型未明"}
DISTANCE_LABELS = {"too_close": "過近", "near": "偏近", "mid": "中距離", "far": "偏遠", "unknown": "距離未明"}


class PromptBuilder:
    def __init__(self, tracking_system_path: str, idle_system_path: str) -> None:
        self.tracking_system = Path(tracking_system_path).read_text(encoding="utf-8")
        self.idle_system = Path(idle_system_path).read_text(encoding="utf-8")

    def build_tracking_prompt(
        self,
        sentence_index: int,
        selected_examples: list[str],
        audience: AudienceFeatures,
        event_summary: str,
        reacquired: bool,
    ) -> dict[str, str | list[str]]:
        stages = load_tracking_examples(selected_examples)
        stage_examples = stages.get(sentence_index, [])
        if not stage_examples:
            raise ValueError(f"no stage examples found for sentence {sentence_index}")
        style_lines = "\n".join(
            f"- 階段靈感{index + 1}: {row['event_hint'] or '一般觀察'}"
            for index, row in enumerate(stage_examples)
        )
        reacquire_lines = ""
        if reacquired and 0 in stages:
            reacquire_lines = "\n".join(
                f"- 重獲時偏向: {row['event_hint'] or '重新追上目標'}" for row in stages[0]
            )
        feature_summary = self._summarize_audience(audience)
        system_prompt = (
            f"{self.tracking_system.strip()}\n\n"
            "硬性輸出規則:\n"
            "1. 只輸出最終台詞，不要解釋，不要思考過程，不要條列。\n"
            "2. 不要加引號、前綴、角色名、備註。\n"
            "3. 只允許一行繁體中文完整句子。\n"
            "4. 句長必須在 8 到 22 字之間。\n"
            "5. 若未滿足條件，立刻重寫，不可輸出空字串。\n"
            "6. 不可直接重寫或輕微改寫任何 reference 例句，不可與參考句出現 6 個以上連續相同字。"
        )
        user_prompt = (
            f"任務: 生成第 {sentence_index} 句追蹤台詞。\n"
            f"階段限制: 只能參考第 {sentence_index} 句 examples 的壓迫程度、觀察方向與節奏，不可跳段，也不可照抄。\n"
            f"第 {sentence_index} 句階段靈感:\n{style_lines}\n"
            f"{reacquire_lines}\n"
            f"觀眾特徵摘要: {feature_summary}\n"
            f"即時事件: {event_summary or '無特殊事件'}\n"
            f"本句觀察優先順序: {self._priority_hint(event_summary, audience)}\n"
            "輸出檢查:\n"
            "- 必須反映至少一個觀眾特徵或事件\n"
            "- 若有即時事件，台詞核心必須先落在事件上\n"
            "- 若沒有即時事件，台詞核心要落在顏色、距離、身形三者之一\n"
            "- 禁止只寫抽象感受而不點出具體觀察\n"
            "- 必須是完整句子\n"
            "- 必須能直接拿去朗讀\n"
            "- 要有新鮮變化，不能像 examples 的近似改寫\n"
            "- 直接輸出台詞，不要任何其他文字"
        )
        return {
            "system": system_prompt,
            "user": user_prompt,
            "required_terms": self._required_terms(event_summary, audience),
        }

    def build_idle_prompt(self, selected_examples: list[str], idle_duration_ms: int) -> dict[str, str | list[str]]:
        examples = load_idle_examples(selected_examples)
        examples_text = "\n".join(
            f"- 例句: {row['語音文本內容']} | 氛圍:{row['氛圍提示']}" for row in examples[:10]
        )
        user_prompt = (
            f"目前閒置時間: {idle_duration_ms} ms\n"
            f"{examples_text}\n"
            "輸出要求: 單句、繁體中文、15字內。"
        )
        return {"system": self.idle_system, "user": user_prompt, "required_terms": []}

    def _summarize_audience(self, audience: AudienceFeatures) -> str:
        parts = [
            f"上衣{audience.top_color}",
            f"下身{audience.bottom_color}",
            HEIGHT_LABELS.get(audience.height_class, audience.height_class),
            BUILD_LABELS.get(audience.build_class, audience.build_class),
            f"距離{DISTANCE_LABELS.get(audience.distance_class, audience.distance_class)}",
        ]
        if audience.eye_confidence:
            parts.append(f"眼部追視可信度{audience.eye_confidence:.2f}")
        if audience.focus_score:
            parts.append(f"清晰度{audience.focus_score:.2f}")
        return "、".join(parts)

    def _priority_hint(self, event_summary: str, audience: AudienceFeatures) -> str:
        if event_summary and event_summary != "無":
            return f"先寫事件「{event_summary}」，再補一個外觀或距離特徵"
        return (
            f"優先寫距離{DISTANCE_LABELS.get(audience.distance_class, audience.distance_class)}，"
            f"再從上衣{audience.top_color}或{BUILD_LABELS.get(audience.build_class, audience.build_class)}擇一補充"
        )

    def _required_terms(self, event_summary: str, audience: AudienceFeatures) -> list[str]:
        if event_summary and event_summary != "無":
            keywords: list[str] = []
            if "揮手" in event_summary:
                keywords.extend(["揮", "手"])
            if "蹲" in event_summary:
                keywords.append("蹲")
            if "失焦" in event_summary or "模糊" in event_summary:
                keywords.extend(["失焦", "模糊", "近"])
            if "貼近" in event_summary or "太近" in event_summary:
                keywords.extend(["近", "貼"])
            if "遠離" in event_summary:
                keywords.extend(["遠", "退"])
            return list(dict.fromkeys(keywords))
        return [audience.top_color, DISTANCE_LABELS.get(audience.distance_class, audience.distance_class)]


def validate_generated_sentence(text: str, limit: int) -> list[str]:
    errors: list[str] = []
    cleaned = text.strip().replace("「", "").replace("」", "")
    core = cleaned.strip(" ,.，。!?！？:：;；\"'")
    if "\n" in cleaned:
        errors.append("must be a single line")
    if len(cleaned) > limit:
        errors.append(f"must be <= {limit} chars")
    if not cleaned:
        errors.append("must not be empty")
    chinese_char_count = sum(1 for char in core if "\u4e00" <= char <= "\u9fff")
    if core and chinese_char_count < 2:
        errors.append("must contain at least 2 chinese chars")
    if core and not any("\u4e00" <= char <= "\u9fff" for char in core):
        errors.append("must contain chinese text")
    if cleaned and not core:
        errors.append("must not be punctuation only")
    return errors
