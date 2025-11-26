import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from fastapi import HTTPException
from datetime import datetime

from backend.models.user import User
from backend.models.challenge import Challenge, ChallengeStatus
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
from backend.tools.analyze_spending import analyze_spending

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ========================================
# 1. 챌린지 관련 함수
# ========================================

def get_active_challenges(user_id: int, session: Session) -> List[Challenge]:
    """사용자의 진행 중인 챌린지 조회"""
    try:
        challenges = session.exec(
            select(Challenge)
            .where(Challenge.user_id == user_id)
            .where(Challenge.status == ChallengeStatus.IN_PROGRESS)
            .order_by(Challenge.created_at.desc())
        ).all()
        return list(challenges)
    except Exception as e:
        print(f"챌린지 조회 실패: {e}")
        return []


def compare_with_challenge(
    tool_result: Dict[str, Any], 
    challenge: Challenge
) -> Optional[Dict[str, Any]]:
    """
    챌린지 목표와 현재 소비 비교
    """
    try:
        plan_detail = challenge.plan_detail
        
        target_category = plan_detail.get("target_category")
        reduce_percent = plan_detail.get("reduce_percent", 10)
        
        if not target_category:
            return None
        
        chart_data = tool_result.get("chart_data", [])
        category_found = None
        
        for cat in chart_data:
            if cat["category_name"] == target_category:
                category_found = cat
                break
        
        if not category_found:
            return None
        
        actual_spent = category_found["amount"]
        baseline_spent = plan_detail.get("baseline_amount", actual_spent)
        target_spent = int(baseline_spent * (1 - reduce_percent / 100))
        
        # 달성률 계산
        if actual_spent <= target_spent:
            achievement_rate = 100
            is_on_track = True
            saved_amount = baseline_spent - actual_spent
            saved_percent = int((saved_amount/baseline_spent) * 100) if baseline_spent > 0 else 0
            message = f"{target_category} 지출을 목표보다 {saved_percent}% 줄이셨어요! 🎉"
        else:
            achievement_rate = int((target_spent / actual_spent) * 100) if actual_spent > 0 else 0
            is_on_track = False
            over_amount = actual_spent - target_spent
            message = f"{target_category} 지출이 목표보다 {over_amount:,}원 초과했어요. 조금만 더 노력해봐요!"
        
        return {
            "challenge_id": challenge.id,
            "challenge_name": challenge.event_name,
            "is_on_track": is_on_track,
            "target_category": target_category,
            "target_reduce_percent": reduce_percent,
            "actual_spent": actual_spent,
            "target_spent": target_spent,
            "baseline_spent": baseline_spent,
            "achievement_rate": achievement_rate,
            "message": message
        }
    
    except Exception as e:
        print(f"챌린지 비교 실패: {e}")
        return None


# ========================================
# 2. 인사이트 구조화 함수
# ========================================

def generate_structured_insights(
    tool_result: Dict[str, Any],
    challenge_comparison: Optional[Dict[str, Any]] = None
) -> Dict[str, List[str]]:
    insights = tool_result.get("insights", [])
    suggestions = tool_result.get("suggestions", [])
    
    major_findings = []
    improvement_suggestions = []
    
    # Tool insights → 주요 발견사항
    for insight in insights:
        msg = insight.get("message", "")
        insight_type = insight.get("type", "")
        
        if insight_type in ["warning", "alert", "info", "positive"]:
            major_findings.append(msg)
    
    # Tool suggestions → 개선 제안
    for sug in suggestions:
        msg = sug.get("message", "")
        if msg:
            improvement_suggestions.append(msg)
    
    # 챌린지 비교 추가
    if challenge_comparison:
        if challenge_comparison["is_on_track"]:
            major_findings.append(
                f"'{challenge_comparison['challenge_name']}' 챌린지 목표 달성 중!"
            )
        else:
            over = challenge_comparison['actual_spent'] - challenge_comparison['target_spent']
            major_findings.append(
                f"'{challenge_comparison['challenge_name']}' 챌린지: 목표보다 {over:,}원 초과"
            )
            improvement_suggestions.append(challenge_comparison["message"])
    
    return {
        "major_findings": major_findings[:4],
        "improvement_suggestions": improvement_suggestions[:3]
    }


# ========================================
# 3. AI 자연어 요약 생성
# ========================================

def generate_ai_summary(
    tool_result: Dict[str, Any],
    user_name: str,
    structured_insights: Dict[str, List[str]],
    challenge_comparison: Optional[Dict[str, Any]] = None
) -> str:
    """AI 자연어 요약 생성"""
    
    month = tool_result.get("month", "이번 달")
    total_income = tool_result.get("total_income", 0)
    total_spent = tool_result.get("total_spent", 0)
    total_saved = tool_result.get("total_saved", 0)
    save_potential = tool_result.get("save_potential", 0)
    projected_total = tool_result.get("projected_total", 0)
    
    top_category = tool_result.get("top_category", "없음")
    overspent_category = tool_result.get("overspent_category", "양호")
    
    is_deficit = save_potential < 0
    
    # AI 프롬프트 구성
    prompt = f"""
당신은 대학생을 위한 친근하고 공감적인 금융 코치 'PlanB AI'입니다.

# {user_name}님의 {month} 소비 분석 결과

## 재무 요약
- 총 수입: {total_income:,}원
- 총 지출: {total_spent:,}원
- 저축액: {total_saved:,}원
- 저축 가능액: {save_potential:,}원 {"(적자 ⚠️)" if is_deficit else ""}
- 예상 월말 지출: {projected_total:,}원

## 소비 패턴
- 가장 많이 쓴 카테고리: {top_category}
- 과소비 카테고리: {overspent_category}

## 주요 발견 사항
{chr(10).join([f"- {finding}" for finding in structured_insights["major_findings"]])}

## 개선 제안
{chr(10).join([f"- {suggestion}" for suggestion in structured_insights["improvement_suggestions"]])}

{"## 챌린지 진행 상황" if challenge_comparison else ""}
{f"- 목표: {challenge_comparison['challenge_name']}" if challenge_comparison else ""}
{f"- {challenge_comparison['target_category']} 목표: {challenge_comparison['target_spent']:,}원" if challenge_comparison else ""}
{f"- 실제 지출: {challenge_comparison['actual_spent']:,}원" if challenge_comparison else ""}
{f"- 달성률: {challenge_comparison['achievement_rate']}%" if challenge_comparison else ""}

---

위 정보를 바탕으로 {user_name}님께 **2-3문장**으로 간결하게 응답해주세요:

1. 첫 문장: 재무 상태 요약 (적자/흑자, 핵심 문제/잘한 점)
2. 두 번째 문장: 가장 중요한 조언 1가지 (구체적 숫자 포함)
3. 세 번째 문장: 응원 메시지 또는 챌린지 피드백

**작성 규칙:**
- 반말 사용 (친근하게)
- 이모지 1-2개만 사용
- 숫자는 천단위 쉼표 표시
- 총 150자 이내
- {"적자 상황이므로 공감과 현실적 조언" if is_deficit else "긍정적이고 격려하는 톤"}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 PlanB의 금융 코치 AI입니다. 대학생의 눈높이에 맞춰 친근하고 실용적인 조언을 2-3문장으로 간결하게 제공합니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        ai_summary = response.choices[0].message.content.strip()
        print(f"AI 응답 생성 완료 ({len(ai_summary)}자)")
        return ai_summary
        
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        # 폴백 응답
        if is_deficit:
            return f"이번 달 {abs(save_potential):,}원 적자가 발생했어요. {overspent_category} 지출을 줄이면 개선할 수 있어요! 💪"
        else:
            return f"수입 {total_income:,}원 대비 잘 관리하고 계시네요! {top_category} 항목을 조금만 더 줄이면 완벽해요. 👍"


# ========================================
# 4. 통합 서비스 함수 (메인)
# ========================================

async def run_spending_analysis_service(
    user: User,
    month: str,
    session: Session
) -> Dict[str, Any]:
    
    # 1. Tool 실행
    print(f"{user.name}님 {month} 소비 분석 시작...")
    tool_result = analyze_spending(month=month, use_demo_mode=True)
    
    if "error" in tool_result:
        raise HTTPException(status_code=400, detail=tool_result["error"])
    
    # 2. 챌린지 비교
    challenge_comparison = None
    active_challenges = get_active_challenges(user.id, session)
    if active_challenges:
        latest_challenge = active_challenges[0]  # 가장 최근 챌린지
        challenge_comparison = compare_with_challenge(tool_result, latest_challenge)
    
    # 3. 구조화된 인사이트 생성
    structured_insights = generate_structured_insights(tool_result, challenge_comparison)
    
    # 4. AI 자연어 요약 생성
    ai_summary = generate_ai_summary(
        tool_result=tool_result,
        user_name=user.name,
        structured_insights=structured_insights,
        challenge_comparison=challenge_comparison
    )
    
    # 5. DB 저장 준비
    chart_data_list = tool_result.pop("chart_data", [])
    meta_info = tool_result.pop("meta", {})
    
    # analysis_date 변환 (str → date)
    tool_result_copy = tool_result.copy()
    tool_result_copy["analysis_date"] = datetime.strptime(
        tool_result["analysis_date"], "%Y-%m-%d"
    ).date()
    
    # AI 요약을 insight_summary에 저장
    tool_result_copy["insight_summary"] = ai_summary
    
    # 6. DB 저장 (Transaction)
    try:
        # 부모 테이블 저장
        analysis_db = SpendingAnalysis(**tool_result_copy, user_id=user.id)
        session.add(analysis_db)
        session.commit()
        session.refresh(analysis_db)

        for stat in chart_data_list:
            category_stat = SpendingCategoryStats(
                analysis_id=analysis_db.id,
                **stat
            )
            session.add(category_stat)
        
        session.commit()
        print(f"{user.name}님 분석 데이터 저장 완료 (ID: {analysis_db.id})")
        
    except Exception as e:
        session.rollback()
        print(f"DB 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {str(e)}")
    
    # 7. 응답
    response_data = {
        **tool_result,
        "ai_summary": ai_summary,
        "major_findings": structured_insights["major_findings"],
        "improvement_suggestions": structured_insights["improvement_suggestions"],
        "chart_data": chart_data_list,
        "meta": meta_info
    }
    
    if challenge_comparison:
        response_data["challenge_status"] = challenge_comparison
    
    return response_data