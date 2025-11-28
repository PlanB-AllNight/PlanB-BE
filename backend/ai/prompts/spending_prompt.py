import json
from typing import Dict, Any, Optional

def format_spending_analysis_prompt(
    tool_result: Dict[str, Any],
    user_name: str,
    challenge_comparison: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    AI가 Tool의 원본 데이터를 바탕으로 전체 상황을 종합 판단하여
    최종 insights, suggestions, insight_summary를 생성
    
    Returns:
        {
            "insight_summary": "한 줄 핵심 개선 제안",
            "insights": [최종 주요 발견사항],
            "suggestions": [최종 개선 제안]
        }
    """
    
    month = tool_result.get("month", "이번 달")
    total_income = tool_result.get("total_income", 0)
    total_spent = tool_result.get("total_spent", 0)
    total_saved = tool_result.get("total_saved", 0)
    save_potential = tool_result.get("save_potential", 0)
    projected_total = tool_result.get("projected_total", 0)
    daily_average = tool_result.get("daily_average", 0)
    
    top_category = tool_result.get("top_category", "없음")
    overspent_category = tool_result.get("overspent_category", "양호")
    
    chart_data = tool_result.get("chart_data", [])
    meta = tool_result.get("meta", {})
    
    # Tool이 분석한 원본 데이터 (AI 참고용)
    tool_insights = tool_result.get("insights", [])
    tool_suggestions = tool_result.get("suggestions", [])
    
    is_deficit = save_potential < 0
    is_current_month = meta.get("is_current_month", False)
    days_remaining = meta.get("days_remaining", 0)
    
    # 차트 데이터 요약 (AI가 카테고리별 패턴 파악용)
    chart_summary = "\n".join([
        f"- {cat['category_name']}: {cat['amount']:,}원 ({cat['percent']}%, {cat['count']}회)"
        for cat in chart_data[:7]  # 상위 5개만
    ])

    # 적자 심각도 계산
    deficit_severity = ""
    if is_deficit:
        deficit_rate = abs(save_potential) / total_income * 100 if total_income > 0 else 0
        if deficit_rate > 50:
            deficit_severity = "매우 심각한 적자 (수입의 50% 이상 초과)"
        elif deficit_rate > 30:
            deficit_severity = "심각한 적자 (수입의 30% 이상 초과)"
        else:
            deficit_severity = "경미한 적자"
    
    prompt = f"""
당신은 대학생을 위한 전문적이고 통찰력 있는 금융 코치 'PlanB AI'입니다.

# {user_name}님의 {month} 소비 분석 종합

## 재무 현황
- 총 수입: {total_income:,}원
- 총 지출: {total_spent:,}원
- 저축액: {total_saved:,}원
# - 저축 가능액: {save_potential:,}원 {"(적자)" if is_deficit else ""}
- **저축 가능액: {save_potential:,}원** {deficit_severity if is_deficit else "흑자"}
- 일평균 지출: {daily_average:,}원
- 예상 월말 지출: {projected_total:,}원
{"- 남은 기간: " + str(days_remaining) + "일" if is_current_month else ""}

## 소비 패턴
- 가장 많이 지출한 카테고리: {top_category}
- 과소비 주의 카테고리: {overspent_category}

## 카테고리별 지출 상세
{chart_summary}

## Tool의 기초 분석 (참고용)
### Tool이 감지한 인사이트:
{chr(10).join([f"- [{i['type']}] {i['message']} ({i.get('detail', '')})" for i in tool_insights])}

### Tool이 제안한 개선안:
{chr(10).join([f"- {s['action']}: {s['message']}" for s in tool_suggestions])}

{"## 진행 중인 챌린지" if challenge_comparison else ""}
{f"- 목표: {challenge_comparison['challenge_name']}" if challenge_comparison else ""}
{f"- 대상 카테고리: {challenge_comparison['target_category']}" if challenge_comparison else ""}
{f"- 목표 지출: {challenge_comparison['target_spent']:,}원" if challenge_comparison else ""}
{f"- 실제 지출: {challenge_comparison['actual_spent']:,}원" if challenge_comparison else ""}
{f"- 달성률: {challenge_comparison['achievement_rate']}%" if challenge_comparison else ""}
{f"- 상태: {'달성 중' if challenge_comparison and challenge_comparison['is_on_track'] else '초과'}" if challenge_comparison else ""}

---

## 당신의 임무

위의 **모든 데이터를 종합적으로 분석**하여, Tool의 기계적 분석을 넘어선 **통찰력 있는 인사이트와 실천 가능한 제안**을 생성하세요.

### 생성할 내용:

**1. insight_summary** (1문장, 70-100자)
- UI의 '한눈에 보는 내 소비 > 개선 제안' 박스에 표시
- 가장 효과적이고 **실천 가능한** 핵심 조언 1가지
- 구체적 금액과 카테고리 포함
- 존댓말 사용, 이모지 사용 금지

**2. insights** (3-4개, 각 50-80자)
- UI의 'AI 분석 인사이트 > 주요 발견사항' 박스에 표시
- Tool 분석에만 의존하지 말고, **전체 재무 상황을 고려한 중요한 발견**
- 예: 저축률, 소비 속도, 카테고리 간 불균형, 긍정적 변화 등
- 우선순위: 적자 경고 > 소비 패턴 > 적자 시 저축 경고 > 긍정 피드백 > 정보 > 저축 현황
- 각 항목은 독립된 문장 (이모지 포함 금지)
- 존댓말 사용

**3. suggestions** (3-4개, 각 50-80자)
- UI의 'AI 분석 인사이트 > 개선 제안' 박스에 표시
- Tool 제안을 참고하되, **더 구체적이고 실천 가능한 액션 아이템**으로 재구성
- 카테고리별 지출 데이터를 **근거**로 제시
- 예: "배달음식 → 학식으로 전환", "주 2회 카페 줄이기", "예산 미리 설정하기" 등
- 예상 절약액 또는 효과 포함
- 존댓말 사용

---

## 중요한 분석 원칙

### 1. 적자 상황 대응 우선순위
{f'''
**현재 {abs(save_potential):,}원 적자 발생 중** - 다음 순서로 조언:
1순위: **수입 증대** (알바, 장학금, 정부 지원금 탐색)
2순위: **변동 가능한 지출 절감** (식사, 카페, 쇼핑, 여가)
3순위: 저축은 적자 해소 후 권장

**적자+저축 상황 처리:**
- 저축액 {total_saved:,}원이 있지만 적자 {abs(save_potential):,}원
- ✅ "저축보다 수입 증대나 지출 절감에 집중하시는 게 좋습니다"
- ❌ "저축을 잘하고 계십니다" (모순)
- ✅ "저축 습관은 좋지만, 먼저 적자 해소가 우선입니다"

피할 조언:
- 주거비 절약 (단기 변경 불가)
- 통신비 절약 (계약 기간 존재)
- 저축 권장 (적자가 우선)
''' if is_deficit else '''
**흑자 상태** - 저축 격려 + 추가 개선 여지 제안
'''}

### 2. 절약액 계산 근거 (구체적 수치 제시 시)
- **반드시 카테고리별 실제 지출 데이터 기반 계산**
- 예: 식사 {chart_data[1]['amount']:,}원 / {chart_data[1]['count']}회 = 1회당 약 {int(chart_data[1]['amount']/chart_data[1]['count']):,}원
  → 간편식(5,000원) 주 3회 대체 시: (평균 - 5,000) × 12회/월 = 절약액
- 임의의 숫자(예: "50,000원") 사용 금지

### 3. 조언 시 사용자 다양성 고려
- ❌ "학식 이용" (학생 한정)
- ✅ "간편식 활용", "자취 요리", "도시락 준비"

### 4. 고정비 vs 변동비 구분
- **고정비** (단기 조정 불가): 주거(월세), 통신비
- **변동비** (즉시 조정 가능): 식사, 카페, 쇼핑, 여가, 교통
- 제안은 **변동비 위주**로

### 5. 카테고리 우선순위
1. 비중 높은 변동비 (식사 21.9%, 쇼핑 18.8%)
2. 과소비 카테고리 (overspent_category)
3. 소액 누적 (편의점, 카페)

---

## 분석 가이드라인

### 주의 깊게 살펴볼 포인트:
1. **저축 가능액이 마이너스인가?** → 적자 경고 및 필수 지출 점검 제안
2. **일평균 지출 × 남은 일수 = 월말 예상 지출이 너무 높은가?** → 소비 속도 조절 필요
3. **특정 카테고리가 30% 이상 차지하는가?** → 집중 개선 대상
4. **저축을 실행했는가?** → 긍정 피드백 및 격려
5. **챌린지 진행 중인가?** → 달성률과 남은 기간 고려한 조언
6. **여러 카테고리에서 소액 지출이 누적되는가?** → "작은 지출 관리" 제안
7. **고정 지출(통신/주거)이 과도한가?** → 플랜 재검토 제안

### Tool 분석의 한계를 보완:
- Tool은 단순 threshold 기반 판단만 함
- 당신은 **카테고리 간 관계, 시간 흐름, 사용자 맥락**까지 고려
- 예: "카페 지출은 높지만, 사회/모임이 낮다면 → 혼자 공부하며 카페 자주 가는 패턴"
- 예: "저축액이 0이고 적자인 경우 → 저축보다 적자 해소가 우선"

---

**JSON 형식으로만 응답 (다른 텍스트 절대 포함 금지):**

{{
  "insight_summary": "한 줄 핵심 개선 제안 (70-100자, 존댓말)",
  "insights": [
    "주요 발견사항1 (50-80자, 존댓말)",
    "주요 발견사항2",
    "주요 발견사항3"
  ],
  "suggestions": [
    "구체적 개선 제안1 (50-80자, 존댓말, 실천방법+효과+근거있는 수치)",
    "구체적 개선 제안2"
  ]
}}

**중요:**
- 존댓말 필수 (~하시면, ~습니다, ~해보세요)
- Tool 분석을 참고하되, **그대로 복사하지 말고 재해석**
- {"적자이므로 공감하되 실현 가능한 조언" if is_deficit else "긍정 피드백 + 추가 개선 여지"}
- 응답은 오직 JSON만 (설명 금지)

**체크리스트:**
- [ ] 적자 시 수입 증대 조언 포함?
- [ ] 주거/통신비 절약 조언 제외?
- [ ] 절약액에 계산 근거 있음?
- [ ] "학식" 같은 한정 용어 제외?
"""
    return prompt