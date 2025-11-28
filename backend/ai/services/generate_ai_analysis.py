import json
from typing import Dict, Any, Optional

from backend.ai.prompts.spending_prompt import format_spending_analysis_prompt
from backend.ai.prompts.system_prompts import SYSTEM_PROMPT_SPENDING
from backend.ai.client import generate_json

def generate_ai_comprehensive_analysis(
    tool_result: Dict[str, Any],
    user_name: str,
    challenge_comparison: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    
    tool_insights = tool_result.get("insights", [])
    tool_suggestions = tool_result.get("suggestions", [])
    overspent_category = tool_result.get("overspent_category", "양호")
    
    prompt = format_spending_analysis_prompt(tool_result, user_name, challenge_comparison)

    try:
        response = generate_json(SYSTEM_PROMPT_SPENDING, prompt, 0.8)
        
        ai_response_text = response.choices[0].message.content.strip()
        
        # JSON 파싱
        ai_analysis = json.loads(ai_response_text)
        
        # 챌린지 정보 추가 (있을 경우)
        if challenge_comparison:
            if challenge_comparison["is_on_track"]:
                ai_analysis["insights"].insert(0, 
                    f"🎉 '{challenge_comparison['challenge_name']}' 챌린지 목표를 달성하고 계십니다!"
                )
            else:
                over = challenge_comparison['actual_spent'] - challenge_comparison['target_spent']
                ai_analysis["insights"].insert(0,
                    f"⚠️ '{challenge_comparison['challenge_name']}' 챌린지: 목표보다 {over:,}원 초과했습니다"
                )
        
        print(f"AI 종합 분석 생성 완료")
        print(f"   - insight_summary: {ai_analysis['insight_summary']}")
        print(f"   - insights: {len(ai_analysis['insights'])}개")
        print(f"   - suggestions: {len(ai_analysis['suggestions'])}개")
        
        return ai_analysis
        
    except json.JSONDecodeError as e:
        print(f"AI 응답 JSON 파싱 실패: {e}")
        print(f"   원본 응답: {ai_response_text[:200]}...")
        
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
    
    # ========================================
    # 폴백: AI 실패 시 Tool 데이터 그대로 사용
    # ========================================
    print("AI 생성 실패 - Tool 데이터 사용")
    
    fallback_insights = []
    for insight in tool_insights[:4]:
        msg = insight.get("message", "")
        insight_type = insight.get("type", "")
        
        if insight_type == "alert":
            fallback_insights.append(f"{msg}")
        elif insight_type == "warning":
            fallback_insights.append(f"{msg}")
        elif insight_type == "positive":
            fallback_insights.append(f"{msg}")
        else:
            fallback_insights.append(f"{msg}")
    
    fallback_suggestions = [s.get("message", "") for s in tool_suggestions[:3]]
    
    fallback_summary = fallback_suggestions[0] if fallback_suggestions else \
                       (f"'{overspent_category}' 지출을 줄이시면 개선 가능합니다" 
                        if overspent_category != "양호" 
                        else "현재 소비 패턴을 유지하시면 좋겠습니다")
    
    return {
        "insight_summary": fallback_summary,
        "insights": fallback_insights,
        "suggestions": fallback_suggestions
    }