import json

from backend.ai.prompts.system_prompts import SYSTEM_PROMPT_BUDGET
from backend.ai.prompts.budget_prompt import format_budget_insight_prompt
from backend.ai.client import generate_json

def generate_ai_insight(baseline):
    recommended_budget = baseline["recommended_budget"]
    spending_history = baseline["spending_history"]
    needs_adjustment_info = baseline.get("needs_adjustment_info", {})

    prompt = format_budget_insight_prompt(
        recommended_budget,
        spending_history,
        needs_adjustment_info,
        baseline
    )

    response = generate_json(SYSTEM_PROMPT_BUDGET, prompt)

    ai_text = response.choices[0].message.content
    parsed = json.loads(ai_text)

    insight = parsed["ai_insight"]
    title = parsed["title"]

    insight["sub_text"] = normalize_terms(insight["sub_text"])
    insight["main_suggestion"] = normalize_terms(insight["main_suggestion"])
    insight["expected_effect"] = normalize_terms(insight["expected_effect"])
    if insight.get("extra_suggestion"):
        insight["extra_suggestion"] = normalize_terms(insight["extra_suggestion"])
    if insight.get("adjustment_info"):
        insight["adjustment_info"] = normalize_terms(insight["adjustment_info"])

    ai_output = {
        "categories": baseline["recommended_budget"],
        "ai_insight": insight,
        "title": title
    }

    return ai_output

def normalize_terms(text: str) -> str:
    return (
        text.replace("Needs", "필수 지출")
            .replace("Wants", "선택 지출")
            .replace("needs", "필수 지출")
            .replace("wants", "선택 지출")
    )