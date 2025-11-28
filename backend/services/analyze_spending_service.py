from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from fastapi import HTTPException
from datetime import datetime

from backend.models.user import User
from backend.models.challenge import Challenge, ChallengeStatus
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
from backend.tools.analyze_spending import analyze_spending

from backend.ai.services.spending_ai_service import generate_ai_comprehensive_analysis

# ========================================
# 챌린지 관련 함수
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
    """챌린지 목표와 현재 소비 비교"""
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
        
        if actual_spent <= target_spent:
            achievement_rate = 100
            is_on_track = True
            saved_amount = baseline_spent - actual_spent
            saved_percent = int((saved_amount/baseline_spent) * 100) if baseline_spent > 0 else 0
            message = f"{target_category} 지출을 목표보다 {saved_percent}% 줄이셨습니다!"
        else:
            achievement_rate = int((target_spent / actual_spent) * 100) if actual_spent > 0 else 0
            is_on_track = False
            over_amount = actual_spent - target_spent
            message = f"{target_category} 지출이 목표보다 {over_amount:,}원 초과했습니다"
        
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
# 통합 서비스 함수 (메인)
# ========================================

async def run_spending_analysis_service(
    user: User,
    month: str,
    session: Session
) -> Dict[str, Any]:
    
    # 1. Tool 실행 (원본 데이터 수집)
    print(f"{user.name}님 {month} 소비 분석 시작...")
    tool_result = analyze_spending(month=month, use_demo_mode=True)
    
    if "error" in tool_result:
        raise HTTPException(status_code=400, detail=tool_result["error"])
    
    print(f"   Tool 분석 완료")
    print(f"      - 총 지출: {tool_result['total_spent']:,}원")
    print(f"      - 주요 카테고리: {tool_result['top_category']}")
    print(f"      - 과소비 카테고리: {tool_result['overspent_category']}")
    
    # 2. 챌린지 비교
    challenge_comparison = None
    active_challenges = get_active_challenges(user.id, session)
    if active_challenges:
        latest_challenge = active_challenges[0]
        challenge_comparison = compare_with_challenge(tool_result, latest_challenge)
        print(f"   🎯 챌린지 비교 완료: {challenge_comparison['challenge_name']}")
    
    # 3. AI 종합 분석 (최종 insights, suggestions, insight_summary 생성)
    print(f"   🤖 AI 종합 분석 시작...")
    ai_analysis = generate_ai_comprehensive_analysis(
        tool_result=tool_result,
        user_name=user.name,
        challenge_comparison=challenge_comparison
    )
    
    # 4. DB 저장 준비
    chart_data_list = tool_result.pop("chart_data", [])
    meta_info = tool_result.pop("meta", {})
    
    # Tool의 원본 insights/suggestions는 버림 (AI 결과로 대체)
    tool_result.pop("insights", [])
    tool_result.pop("suggestions", [])
    
    # analysis_date 변환 (str → date)
    tool_result_copy = tool_result.copy()
    tool_result_copy["analysis_date"] = datetime.strptime(
        tool_result["analysis_date"], "%Y-%m-%d"
    ).date()
    
    # AI가 생성한 최종 결과를 DB에 저장
    tool_result_copy["insight_summary"] = ai_analysis["insight_summary"]
    tool_result_copy["insights"] = ai_analysis["insights"]
    tool_result_copy["suggestions"] = ai_analysis["suggestions"]
    
    # 5. DB 저장
    try:
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
    
    # 6. 프론트엔드 응답
    response_data = {
        # 기본 정보
        "month": tool_result["month"],
        "analysis_date": tool_result["analysis_date"],
        
        # 재무 요약
        "total_income": tool_result["total_income"],
        "total_spent": tool_result["total_spent"],
        "total_saved": tool_result["total_saved"],
        "save_potential": tool_result["save_potential"],
        "daily_average": tool_result["daily_average"],
        "projected_total": tool_result["projected_total"],
        
        # 한눈에 보는 내 소비
        "top_category": tool_result["top_category"],
        "overspent_category": tool_result["overspent_category"],
        "insight_summary": ai_analysis["insight_summary"],
        
        # AI 분석 인사이트
        "insights": ai_analysis["insights"],
        "suggestions": ai_analysis["suggestions"],
        
        # 차트 데이터
        "chart_data": chart_data_list,
        
        # 메타 정보
        "meta": meta_info
    }
    
    if challenge_comparison:
        response_data["challenge_status"] = challenge_comparison
    
    print(f"전체 분석 완료\n")
    return response_data