import os
import json
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select
from openai import OpenAI
from dotenv import load_dotenv

from backend.models.user import User
from backend.models.budget import BudgetAnalysis, BudgetResponse, BudgetSummaryItem, BudgetSummary, CategoryBudget
from backend.models.analyze_spending import SpendingAnalysis

from backend.tools.recommend_budget import recommend_budget_logic


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# insight 프롬프트 생성
def create_insight_prompt(
    recommended_budget,
    spending_history,
    needs_adjustment_info,
    baseline,
):
    needs_cap = baseline["summary"]["needs"]["amount"]
    wants_cap = baseline["summary"]["wants"]["amount"]
    savings_cap = baseline["summary"]["savings"]["amount"]
    income = baseline["total_income"]

    recommended_budget = json.dumps(recommended_budget, ensure_ascii=False, indent=2)
    spending_json = json.dumps(spending_history, ensure_ascii=False, indent=2)
    adjustment_json = json.dumps(needs_adjustment_info, ensure_ascii=False, indent=2)

    over_amount = needs_adjustment_info.get("over_amount", 0)

    prompt = f"""
# 역할
당신은 대학생을 위한 개인 금융 설계 전문가입니다.

이번 예산안은 이미 서버에서 확정되었으며, 
당신의 역할은 조정이 필요했던 경우에만(필수 지출 cap을 맞추지 못한 경우) 
**조정이 왜 필요한지 + 조정 방향 제안 + 기대 효과**를 요약하는 것입니다.

# 핵심 규칙 (반드시 지켜야 함)
1) Insight는 총 3개 문장만 기본 생성한다.
   - sub_text (문제 원인 분석)
   - main_suggestion (핵심 행동 제안)
   - expected_effect (예상 효과)

2) 만약 예비비(예비비(필수 지출) / 예비비(선택 지출))이 존재한다면 extra_suggestion을 생성한다.
   - validation_json 안에 "예비비" 관련 카테고리가 존재하면 생성
   - 존재하지 않으면 extra_suggestion = null

3) {over_amount:,}가 0보다 큰 경우(조정해도 cap 이하로 줄일 수 없는 경우) adjustment_info를 생성한다.
   - {over_amount:,} > 0인 경우 생성
   - {over_amount:,} == 0이면 adjustment_info = null

4) 반드시 숫자 기반 문장을 사용해야 한다.
    - “얼마 줄였는지 / 얼마나 늘렸는지”
    - “현재 지출 대비 어떤 변화가 있었는지”
    - “Cap 달성에 어떤 영향을 주는지”

5) 절대 사실과 다른 내용을 작성하면 안 된다.
    → 아래 제공된 “현재 지출” 과 “최종 권장 금액”을 기반으로 직접 계산해야 한다.

6) 대학생에게 맞는 현실적인 톤으로 작성할 것.
   - 존댓말
   - 부드럽고 설득력 있는 문장
   - 비난 금지, 대안 중심
   - cap, needs/wants 같은 단어 대신 “필수 지출 / 선택 지출 / 예산 목표”를 사용


---

# 제공 데이터

[현재 지출 내역 (기준)]
{spending_json}

[최종 확정된 예산안]
{recommended_budget}

[필수지출 조정 정보]
{adjustment_json}

- needs cap: {needs_cap:,}원
- wants cap: {wants_cap:,}원
- savings cap: {savings_cap:,}원
- total income: {income:,}원

---

# 작성 가이드 (매우 중요)

## 1. sub_text (문제 원인 분석) - 필수
- 반드시 “변화율(%)이 가장 큰 카테고리” 또는 “변화율 상위 2개 중 소비 패턴상 가장 의미 있는 카테고리”를 선택합니다.
    - 변화율 = |(최종 권장 금액 - 현재 지출) / 현재 지출| × 100
    - 현재 지출이 0원인 항목은 변화폭 자체가 크더라도 의미가 낮으므로 우선순위를 뒤로 둡니다.
- 선택된 항목 1개만 설명합니다.
- 아래 요소를 한 문장으로 포함해야 합니다:
    1) 어떤 카테고리를 얼마나 조정했는지 (증액/감액)
    2) 조정 전 금액 → 조정 후 금액
    3) 왜 변경이 필요한지 (소비 패턴 기반 근거: 습관성/고가성/낭비 가능성 등)
예: “쇼핑/꾸미기 지출을 102,000원에서 152,000원으로 49% 증액해 최근 소비 비중 증가와 패턴 변화를 반영했습니다.”
※ 예시는 형식만 참고용이며 실제 카테고리명을 그대로 따라 쓰지 마세요.

## 2. main_suggestion (핵심 행동 제안) - 필수
- 행동 변화를 정확히 1문장으로 제안합니다.
- 반드시 구체적인 실천 방식이 포함되어야 합니다.
- “횟수 줄이기 / 단가 낮추기 / 대안 찾기 / 할인 활용” 등 행동 중심으로 작성합니다.
예: "배달 횟수를 주 2회에서 1회로 줄이고 학식 이용을 늘리면 월 2만원 절약할 수 있습니다."

## 3. expected_effect (예상 효과) - 필수
- 조정된 예산이 어떠한 긍정적인 결과를 만드는지 1문장으로 설명합니다.
- 목표 달성 효과 또는 재정 안정 효과를 반드시 포함합니다.
- 숫자 기반 문장이 반드시 들어가야 합니다.
예: "이번 조정으로 선택 지출 33만원 목표를 무리 없이 달성하면서도 지출 균형을 유지할 수 있습니다."

## 4. extra_suggestion
- “예비비” 카테고리가 존재할 때만 작성합니다.
    - 필수 지출 예비비 / 선택 지출 예비비 모두 포함
- 1문장만 작성합니다.
- 아래 두 요소를 포함해야 합니다:
    1) 왜 예비비이 생겼는지 (소비 수준·지출 구조 기반 설명)
    2) 예비비을 어떻게 활용하면 좋은지 (저축/투자/비상금/장기 계획)
예: “필수 지출이 상대적으로 낮아 120,000원의 예비비이 발생했으며, 이를 비상금 또는 단기저축에 활용하면 재정 안정에 도움이 됩니다.”
- 예비비이 없다면 extra_suggestion은 null을 반환합니다.

## 5. adjustment_info
- 필수 지출을 조정했음에도 불구하고 needs_adjustment_info.over_amount > 0인 경우에만 생성합니다.
- needs_adjustment_info.over_amount == 0이면 adjustment_info는 null을 반환합니다.
- 1문장만 작성합니다.
- 아래 두 요소를 반드시 포함합니다:
    1) 왜 필수 지출 한도를 정확히 맞추기 어려웠는지 (고정비 크기, 식비 구조, 소비 패턴 등)
    2) 사용자가 시도해볼 수 있는 개선 조언 (구독 점검, 식비 구조 조정 등 실천 가능 조언)
- cap이라는 표현은 사용하지 않고 “필수 지출 한도”, “예산 목표” 등을 사용합니다.

---

# 용어 규칙 (중요)

- Insight 문장에서는 "Needs", "Wants"라는 단어를 절대 사용하지 않는다.
- 대신 아래 한국어 용어를 사용한다.
  - Needs → "필수 지출"
  - Wants → "선택 지출"
- Savings는 "저축" 또는 "저축/투자"로 자연스럽게 표현한다.

---

# 출력 형식 (JSON Only)
```json
{{
  "ai_insight": {{
    "sub_text": "문제 원인 분석 (정확한 수치 포함)",
    "main_suggestion": "핵심 행동 제안 1줄",
    "expected_effect": "예상 효과 1줄 (Cap 달성 포함)",
    "extra_suggestion": "예비비이 있을 때만 나타나는 문장 (없으면 null)",
    "adjustment_info": "needs의 cap을 넘어섰을 때만 나타나는 문장 (아니면 Null)"
  }}
}}
```
    
⚠️ sub_text, main_suggestion, expected_effect는 반드시 존재해야 합니다.
하나라도 누락되면 잘못된 출력으로 간주하고 다시 생성해야 합니다.
절대 생략하거나 null을 넣지 마세요.
"""
    return prompt


# 최종 예산안을 가지고 Insight 생성
def generate_ai_insight(baseline):
    recommended_budget = baseline["recommended_budget"]
    spending_history = baseline["spending_history"]
    needs_adjustment_info = baseline.get("needs_adjustment_info", {})

    prompt = create_insight_prompt(
        recommended_budget,
        spending_history,
        needs_adjustment_info,
        baseline
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": """
                당신은 PlanB의 대학생 전문 예산 설계 AI입니다. 당신의 역할은 대학생을 위한 현실적이고 꼼꼼한 '금융 예산 설계 전문가'입니다.
사용자의 소비 내역와 목표 규칙, 목표 배분액을 바탕으로 카테고리별 권장 예산안을 짜주세요. 단순히 비율대로 나누지 않고, **대학생들의 특성**을 반영해서 각 항목의 소비 **내역과 맥락**, **중복성**, **습관**, **낭비 가능성**을 면밀히 분석해서 불필요한 소비를 줄이고, **현실적인 절약 가능성과 구체적인 실행 제안**을 함께 제공합니다. 존댓말을 사용해 답해주세요.
                """
             
             },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=1200
    )

    ai_text = response.choices[0].message.content
    return json.loads(ai_text)["ai_insight"]


# BudgetAnalysis 테이블에 저장할 데이터 변환
def convert_to_budget_analysis_format(baseline, ai_output):
    essential = baseline["summary"]["needs"]["amount"]
    optional = baseline["summary"]["wants"]["amount"]
    saving = baseline["summary"]["savings"]["amount"]

    ai_proposal_list = [
        ai_output["ai_insight"]["sub_text"],
        ai_output["ai_insight"]["main_suggestion"],
        ai_output["ai_insight"]["expected_effect"]
    ]

    # extra_suggestion이 존재하고 None/빈값이 아닐 때만 추가
    extra = ai_output["ai_insight"].get("extra_suggestion")
    if extra and isinstance(extra, str) and extra.strip():
        ai_proposal_list.append(extra)
    
    # adjustment_info가 존재하고 None/빈값이 아닐 때만 추가
    adjust = ai_output["ai_insight"].get("adjustment_info")
    if adjust and isinstance(adjust, str) and adjust.strip():
        ai_proposal_list.append(adjust)

    # ai_output["categories"]가 이제 그룹별 딕셔너리 구조
    grouped_categories = ai_output["categories"]
    
    return {
        "essential_budget": essential,
        "optional_budget": optional,
        "saving_budget": saving,
        "category_proposals": grouped_categories,  # 그룹별 구조
        "ai_proposal": ai_proposal_list
    }


def normalize_terms(text: str) -> str:
    return (
        text.replace("Needs", "필수 지출")
            .replace("Wants", "선택 지출")
            .replace("needs", "필수 지출")
            .replace("wants", "선택 지출")
    )

async def run_budget_recommendation_service(
    user: User,
    selected_plan: str,
    session: Session
):
    print(f"[{user.name}] 맞춤 예산 생성 시작…")

    # 1. 최근 소비 분석 ID 찾기
    recent_analysis = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == user.id)
        .order_by(SpendingAnalysis.id.desc())
    ).first()

    if not recent_analysis:
        raise HTTPException(status_code=404, detail="먼저 소비 분석을 진행해주세요.")

    spending_analysis_id = recent_analysis.id

    # 2. Tool 호출 (가장 첫 단계)
    baseline = recommend_budget_logic(
        user_id=user.id,
        selected_plan=selected_plan,
        recent_analysis=recent_analysis,
        session=session
    )

    # 3. 최종 예산안 기준으로 Insight 생성
    ai_insight = generate_ai_insight(baseline)
    insight = ai_insight
    insight["sub_text"] = normalize_terms(insight["sub_text"])
    insight["main_suggestion"] = normalize_terms(insight["main_suggestion"])
    insight["expected_effect"] = normalize_terms(insight["expected_effect"])
    if insight.get("extra_suggestion"):
        insight["extra_suggestion"] = normalize_terms(insight["extra_suggestion"])
    if insight.get("adjustment_info"):
        insight["adjustment_info"] = normalize_terms(insight["adjustment_info"])

    # 6. 최종 결과 조합
    ai_output = {
        "categories": baseline["recommended_budget"],
        "ai_insight": insight
    }

    # 7. BudgetAnalysis 저장 형태로 변환
    final_data = convert_to_budget_analysis_format(baseline, ai_output)

    # 8. DB 저장
    db_obj = BudgetAnalysis(
        user_id=user.id,
        spending_analysis_id=spending_analysis_id,
        plan_type=selected_plan,

        essential_budget=final_data["essential_budget"],
        optional_budget=final_data["optional_budget"],
        saving_budget=final_data["saving_budget"],

        category_proposals=final_data["category_proposals"],
        ai_proposal=final_data["ai_proposal"],

        created_at=datetime.now()
    )

    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    print(f"🎉 BudgetAnalysis 저장 완료 (ID: {db_obj.id})")

    response = BudgetResponse(
        total_income=baseline["total_income"],
        selected_plan=baseline["selected_plan"],
        budget_summary=BudgetSummary(
            needs=BudgetSummaryItem(**baseline["summary"]["needs"]),
            wants=BudgetSummaryItem(**baseline["summary"]["wants"]),
            savings=BudgetSummaryItem(**baseline["summary"]["savings"])
        ),
        category_proposals={
            "needs": [CategoryBudget(**item) for item in baseline["recommended_budget"]["needs"]],
            "wants": [CategoryBudget(**item) for item in baseline["recommended_budget"]["wants"]],
            "savings": [CategoryBudget(**item) for item in baseline["recommended_budget"]["savings"]],
        },
        ai_proposal=final_data["ai_proposal"]
    )

    # 7. 프론트 응답
    return response