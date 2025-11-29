from typing import Any, Dict, List
from backend.mcp.templates.support_message_templates import TEMPLATES
from backend.services.support.search_support import compute_category_weights


def build_support_message(query: str, results: List[Dict[str, Any]]) -> str:
    NEG_KEYWORDS = ["말고", "빼고", "제외", "말곤", "말고는"]

    if any(neg in query for neg in NEG_KEYWORDS):
        template = TEMPLATES["negation"]
    else:
        regions = ["서울", "부산", "대구", "경기", "인천", "광주", "대전", "울산"]
        region_found = next((r for r in regions if r in query), None)

        if region_found:
            template = TEMPLATES["region"]
        else:
            weights = compute_category_weights(query)
            best_category = max(weights, key=weights.get)

            template = TEMPLATES.get({
                "장학금/지원금": "scholarship",
                "생활/복지": "welfare",
                "취업/진로": "job",
                "자산 형성": "asset",
                "대출 상품": "loan",
            }.get(best_category, "default"), TEMPLATES["default"])

    items_text = ""
    for idx, r in enumerate(results, 1):
        items_text += f"{idx}. {r['title']} — {r['subtitle']}\n"

    message = template.format(
        items=items_text.strip(),
        region=region_found or ""
    )

    return message.strip()