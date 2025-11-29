import json

from typing import Dict, Any, List


def format_simulate_prompt(
    user_name: str,
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    tool_plans_for_ai: List[Dict[str, Any]], 
) -> Dict[str, Any]:

    #  AI 프롬프트 (Tool이 준 데이터를 그대로 활용하도록 유도)
    prompt = f"""
당신은 대학생을 위한 금융 코치 'PlanB'입니다.
사용자({user_name})의 목표('{event_name}') 달성을 위한 시뮬레이션 결과를 보고, 사용자에게 보여줄 플랜 카드를 완성해주세요.

## 목표 정보
- 금액: {target_amount:,}원
- 기간: {period_months}개월
- 현재 자산: {current_amount:,}원

## Tool이 계산한 플랜 후보들 (이 데이터를 기반으로 작성)
{json.dumps(tool_plans_for_ai, ensure_ascii=False, indent=2)}

## 임무
1. 위 'Tool이 계산한 플랜 후보들'을 **하나도 빠짐없이** 모두 포함하여 JSON으로 반환하세요.
2. 각 플랜의 **`plan_title`**, **`description`**, **`recommendation`**을 더 매력적이고 자연스러운 한국어(존댓말)로 다듬어주세요.
   - 예: "식비 절약 플랜" -> "배달 줄이고 집밥 먹기" 
   - 예: "식비 20% 절약 시..." -> "식비를 20%만 줄여도 목표에 한 걸음 더 가까워집니다."
3. **`tags`**는 해당 플랜의 핵심 특징(절약 금액, 감축 비율, 추천 여부 등)을 잘 나타내는 키워드로 **2~3개**를 생성해주세요.
   - `tool_tags`를 참고하되, 더 직관적인 단어로 변경해도 좋습니다.
   - 예: ["월 10만원 SAVE", "커피값 줄이기", "강력 추천"]
4. **중요**: 금액(`monthly_required`, `final_estimated_asset` 등)과 기간은 **절대 수정하지 말고** 입력받은 그대로 반환하세요. (계산은 Tool이 정확함)
5. `variant_id`는 입력받은 값을 그대로 유지하세요.

## 응답 형식 (JSON)
{{
    "ai_summary": "전체 분석 요약 (한 줄평)",
    "recommendation": "최종 조언",
    "plans": [
        {{
            "variant_id": "입력받은 variant_id 그대로",
            "plan_type": "...",
            "plan_title": "AI가 다듬은 제목",
            "description": "AI가 다듬은 설명",
            "recommendation": "AI가 쓴 추천/비추천 멘트",
            "tags": ["태그1", "태그2"],
            "is_recommended": true/false (Tool 값 참고하되 조정 가능)
        }},
        ...
    ]
}}
"""
    return prompt