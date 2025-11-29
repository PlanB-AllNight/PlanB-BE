import json
import pandas as pd
import os
from datetime import datetime
import calendar
from typing import Dict, List, Any, Optional

# 데이터 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "../data/mydata.json")

# 카테고리 매핑
CATEGORY_MAP = {
    "식비": "식사", "편의점": "식사",
    "카페": "카페/디저트",
    "사회": "사회/모임", "술집": "사회/모임", "회식": "사회/모임",
    "쇼핑": "쇼핑/꾸미기", "패션": "쇼핑/꾸미기", "뷰티": "쇼핑/꾸미기",
    "도서": "교육/학습", "학습": "교육/학습", "학원": "교육/학습",
    "여가": "취미/여가",
    "교통": "교통", "택시": "교통",
    "주거": "주거", "월세": "주거",
    "구독": "통신/구독", "통신": "통신/구독",
    "저축": "저축/투자", "투자": "저축/투자",
    "수입": "수입"
}

# 과소비 기준
OVERSPEND_THRESHOLDS = {
    "카페/디저트": 15,
    "사회/모임": 20,
    "쇼핑/꾸미기": 20,
    "식사": 40,
    "취미/여가": 15,
}


def analyze_spending(month: Optional[str] = None) -> Dict[str, Any]:
    """
    소비 분석 실행
    
    Args:
        month: 분석할 월 (선택)
            - "10월" 또는 "2024-10" 형태
            - None: 자동으로 최신 달 분석
    
    핵심 로직:
        1. month 지정 시 → 해당 월 데이터 필터링
        2. month 없을 시 → mydata 최신 날짜의 달로 자동 결정
        3. analysis_date → 필터링된 데이터의 최신 날짜
    """
    
    try:
        if not os.path.exists(DATA_PATH):
            return {"error": "데이터 파일을 찾을 수 없습니다."}
        
        df = pd.read_json(DATA_PATH)
        df['date'] = pd.to_datetime(df['date'])

        if df.empty:
            return {"error": "데이터가 없습니다."}
        
        if month:
            if "월" in month:
                nums = [int(s) for s in month.replace("월", "") if s.isdigit()]
                if nums:
                    target_month = int(''.join(map(str, nums)))
                    latest_date = df['date'].max()
                    target_year = latest_date.year
            elif "-" in month:
                parts = month.split("-")
                if len(parts) == 2:
                    target_year = int(parts[0])
                    target_month = int(parts[1])
            else:
                return {"error": "month 형식 오류 (예: '10월' 또는 '2024-10')"}
        else:
            latest_date = df['date'].max()
            target_year = latest_date.year
            target_month = latest_date.month

        df_month = df[
            (df['date'].dt.year == target_year) & 
            (df['date'].dt.month == target_month)
        ]

        if df_month.empty:
            return {
                "error": f"{target_year}년 {target_month}월 데이터가 없습니다.",
                "suggestion": "다른 월을 선택하거나 데이터를 업로드해주세요."
            }
        
        analysis_date = df_month['date'].max()
        analysis_date_str = analysis_date.strftime("%Y-%m-%d")

        current_date = datetime.now()
        is_current_month = (
            target_year == current_date.year and 
            target_month == current_date.month
        )

        df_month['display_category'] = df_month['category'].map(CATEGORY_MAP).fillna("기타")
                
        # 수입/지출/저축 분리
        income_df = df_month[df_month['type'] == '입금']
        expense_df = df_month[df_month['type'] == '출금']
        
        # 저축/투자는 소비 통계에서 제외 (자산 이동)
        spending_df = expense_df[expense_df['display_category'] != '저축/투자']
        saving_df = expense_df[expense_df['display_category'] == '저축/투자']
        
        total_income = int(income_df['amount'].sum())
        total_spent = int(spending_df['amount'].sum())  # 순수 소비
        total_saved = int(saving_df['amount'].sum())    # 저축액
        
        # 저축 가능액 = 수입 - 순수 소비 (저축 제외한 여유)
        save_potential = total_income - total_spent
        
        # 예상 지출액 계산
        daily_average = 0
        projected_total = total_spent
        days_passed = 0
        days_remaining = 0
        
        if is_current_month and total_spent > 0:
            _, last_day = calendar.monthrange(target_year, target_month)
            days_passed = current_date.day
            days_remaining = max(0, last_day - current_date.day)
            
            if days_passed > 0:
                daily_average = int(total_spent / days_passed)
                projected_total = total_spent + (daily_average * days_remaining)
        
        # 카테고리별 집계
        cat_group = spending_df.groupby('display_category')['amount'].agg(['sum', 'count'])
        
        if total_spent > 0:
            cat_group['percent'] = (cat_group['sum'] / total_spent * 100).round(1)
        else:
            cat_group['percent'] = 0.0
        
        cat_group = cat_group.sort_values(by='sum', ascending=False)
        
        top_category = cat_group.index[0] if not cat_group.empty else "없음"
        
        # 과소비 탐지 및 인사이트 생성
        overspent_categories = []

        for cat_name, row in cat_group.iterrows():
            pct = row['percent']
            threshold = OVERSPEND_THRESHOLDS.get(cat_name, None)
            
            # 기준이 있고, 초과한 경우
            if threshold and pct > threshold:
                overspent_categories.append({
                    "category": cat_name,
                    "percent": pct,
                    "threshold": threshold,
                    "excess": pct - threshold  # 초과 비율
                })
        
        # 초과 비율이 가장 큰 카테고리를 대표 과소비 항목으로 선정
        if overspent_categories:
            overspent_categories.sort(key=lambda x: x["excess"], reverse=True)
            overspent_category = overspent_categories[0]["category"]
        else:
            overspent_category = "양호"

        
        insights = []
        suggestions = []
        
        # 월말 예상 지출 경고
        if is_current_month and projected_total > total_spent * 1.15:
            insights.append({
                "type": "alert",
                "category": "전체",
                "message": f"현재 소비 속도라면 월말 약 {projected_total:,}원 지출 예상",
                "detail": f"일평균 {daily_average:,}원 (남은 {days_remaining}일)"
            })

        # 과소비 카테고리별 경고 (상위 3개만)
        for oversp in overspent_categories[:3]:
            cat_name = oversp["category"]
            pct = oversp["percent"]
            threshold = oversp["threshold"]
            
            amt = int(cat_group.loc[cat_name, 'sum'])
            cnt = int(cat_group.loc[cat_name, 'count'])
            
            insights.append({
                "type": "warning",
                "category": cat_name,
                "message": f"'{cat_name}' 지출 비중({pct}%)이 권장({threshold}%)보다 높습니다",
                "detail": f"{cnt}회 사용, 총 {amt:,}원"
            })
            
            # 개선 제안 생성
            save_amt = int(amt * 0.1)
            suggestions.append({
                "category": cat_name,
                "action": f"{cat_name} 지출을 10% 줄이기",
                "expected_saving": save_amt,
                "message": f"월 {save_amt:,}원 절약 가능"
            })
        
        if total_saved > 0:
            saving_count = len(saving_df)
            insights.append({
                "type": "positive",
                "category": "저축/투자",
                "message": f"이번 달 {saving_count}회 저축 실행",
                "detail": f"총 {total_saved:,}원 저축 👏"
            })
        
        if top_category != "없음":
            top_pct = cat_group.loc[top_category, 'percent']
            insights.append({
                "type": "info",
                "category": top_category,
                "message": f"총 소비의 {top_pct}%가 '{top_category}'에서 발생",
                "detail": f"주요 지출 항목입니다"
            })
                
        chart_data = []
        for cat_name, row in cat_group.iterrows():
            chart_data.append({
                "category_name": cat_name,
                "amount": int(row['sum']),
                "count": int(row['count']),
                "percent": float(row['percent'])
            })
        
        return {
            # SpendingAnalysis
            "month": f"{target_year}-{target_month:02d}",
            "analysis_date": analysis_date_str,
            "total_income": total_income,
            "total_spent": total_spent,
            "total_saved": total_saved,
            "save_potential": save_potential,
            "daily_average": daily_average,
            "projected_total": projected_total,
            
            "top_category": top_category,
            "overspent_category": overspent_category,
            
            "insights": insights,
            "suggestions": suggestions,
            
            # SpendingCategoryStats
            "chart_data": chart_data,
            
            # 메타 정보
            "meta": {
                "is_current_month": is_current_month,
                "days_passed": days_passed,
                "days_remaining": days_remaining
            }
        }
    
    except Exception as e:
        return {"error": f"분석 중 오류 발생: {str(e)}"}

def get_current_asset(user_id: int) -> int:
    """
    사용자의 현재 보유 자산(최신 잔액)을 조회합니다.
    
    TODO:
        현재는 공용 mydata.json 사용
        실제 서비스에서는 user_id별 파일 경로 분리 필요
        예: f"backend/data/mydata_{user_id}.json"
    """
    try:
        if not os.path.exists(DATA_PATH):
            return 0
            
        df = pd.read_json(DATA_PATH)
        
        if not df.empty:
            df['dt'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
            df = df.sort_values(by='dt')
            
            last_balance = df.iloc[-1]['balance']
            return int(last_balance)
            
        return 0
        
    except Exception as e:
        print(f"[User {user_id}] 자산 조회 실패: {e}")
        return 0

def get_latest_mydata_date(user_id: int) -> Optional[str]:
    try:
        if not os.path.exists(DATA_PATH):
            return None
            
        df = pd.read_json(DATA_PATH)
        
        if df.empty:
            return None
            
        df['dt'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
        df = df.sort_values(by='dt')
        
        latest_date = df.iloc[-1]['date']

        if isinstance(latest_date, (pd.Timestamp, datetime)):
            return latest_date.strftime("%Y-%m-%d")
        
        return str(latest_date)
        
    except Exception as e:
        print(f"mydata 날짜 조회 실패: {e}")
        return None


# 테스트용 함수 (기존 함수명 호환)
def analyze_spending_logic(month: str = None):
    """
    기존 코드 호환용 래퍼 함수
    """
    result = analyze_spending(month=month)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    print("=" * 60)
    print("소비분석 Tool")
    print("=" * 60)
    
    # 테스트 1: 10월 분석 (11월 데이터도 있다고 가정)
    print("\n[테스트 1] 10월 분석")
    result1 = analyze_spending(month="10월")
    if "error" not in result1:
        print(f"  month: {result1['month']}")
        print(f"  analysis_date: {result1['analysis_date']}")
        print(f"  → 10월 데이터 중 마지막 날짜")
    else:
        print(f"  오류: {result1['error']}")

    # 테스트 2: 자동 분석 (최신 달)
    print("\n[테스트 2] 자동 분석 (month 지정 안 함)")
    result2 = analyze_spending()
    if "error" not in result2:
        print(f"  month: {result2['month']}")
        print(f"  analysis_date: {result2['analysis_date']}")
        print(f"  → mydata 최신 날짜의 달 + 최신 날짜")
    else:
        print(f"  오류: {result2['error']}")
    
    print("\n" + "=" * 80)
    print("테스트 완료!")