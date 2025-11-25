import pandas as pd
import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from backend.core.config import settings

# OpenAI 설정
client = OpenAI(api_key=settings.OPENAI_API_KEY)
DATA_PATH = "mydata.json"

# 카테고리 매핑 (Raw -> Standard)
CATEGORY_MAP = {
    "식비": "식사", "편의점": "식사",
    "카페": "카페/디저트",
    "술집": "사회/모임", "회식": "사회/모임", "동아리": "사회/모임",
    "교통": "교통", "택시": "교통",
    "쇼핑": "쇼핑/꾸미기", "패션": "쇼핑/꾸미기", "뷰티": "쇼핑/꾸미기",
    "도서": "교육/학습", "학습": "교육/학습", "학원": "교육/학습",
    "여가": "취미/여가", "구독": "통신/구독", "통신": "통신/구독",
    "주거": "주거", "월세": "주거",
    "수입": "수입", "저축": "저축/투자", "투자": "저축/투자"
}

def analyze_spending_logic(target_month: str = None):
    # 1. 데이터 로드
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError("mydata.json 파일이 없습니다.")
    
    df = pd.read_json(DATA_PATH)
    df['dt'] = pd.to_datetime(df['date'])
    df['month_str'] = df['dt'].dt.strftime('%Y-%m')
    
    # 타겟 월: 데이터의 마지막 달
    target_month = df['month_str'].max()
        
    # 2. 데이터 전처리
    df['std_category'] = df['category'].map(CATEGORY_MAP).fillna("기타")
    current_df = df[df['month_str'] == target_month]
    
    # 3. 핵심 통계 계산
    income = int(current_df[current_df['type'] == '입금']['amount'].sum())
    expense_df = current_df[current_df['type'] == '출금']['amount'].copy()
    spent = int(expense_df['amount'].sum())
    save_potential = income - spent

    if spent == 0: spent = 1  # 0 나누기 방지
    
    # 4. 카테고리별 통계 - amount 기준 내림차순 정렬
    cat_group = expense_df.groupby('std_category')['amount'].sum().sort_values(ascending=False)
    
    categories = []
    for cat, amount in cat_group.items():
        percent = round((amount / spent) * 100, 1)
        categories.append({"category": cat, "amount": int(amount), "percent": percent})

    if not categories: # 지출이 없는 경우 예외 처리
        categories = [{"category": "기타", "amount": 0, "percent": 0}]
    
    # 5. 지표 계산
    # 시간대 컬럼 추가
    expense_df['hour'] = pd.to_datetime(expense_df['time'], format='%H:%M:%S').dt.hour
    expense_df['weekday'] = expense_df['dt'].dt.weekday

    # 심야 지출 (22:00 ~ 04:00)
    late_night_spent = expense_df[(expense_df['hour'] >= 22) | (expense_df['hour'] < 4)]['amount'].sum()
    late_night_percent = round((late_night_spent / spent) * 100, 1)

    # 주말 지출 (금/토/일)
    weekend_spent = expense_df[expense_df['weekday'].isin([4, 5, 6])]['amount'].sum()
    weekend_percent = round((weekend_spent / spent) * 100, 1)

    # 티끌 지출 (1만원 미만)
    micro_df = expense_df[expense_df['amount'] < 10000]
    micro_count = len(micro_df)
    micro_sum = int(micro_df['amount'].sum())

    # 고정비 비중 (주거, 통신, 교통)
    fixed_cats = ['주거', '통신', '교통']
    fixed_df = expense_df[expense_df['category'].isin(fixed_cats)]
    fixed_spent = int(fixed_df['amount'].sum())
    fixed_ratio = round((fixed_spent / spent) * 100, 1)

    # 최다 지출/빈도
    most_spent = categories[0]
    most_spent_category = most_spent['category']     # 가장 많이 쓴 카테고리

    freq_counts = expense_df['std_category'].value_counts()
    if not freq_counts.empty:
        top_freq_cat = freq_counts.idxmax()
        top_freq_count = freq_counts.max()
    else:
        top_freq_cat = "없음"
        top_freq_count = 0

    # 과소비 후보군
    candidates = [c for c in categories[:3] if c['category'] not in ['주거']]
        
    # 6. AI 분석용 지표 추출
    freq_counts = expense_df['std_category'].value_counts()
    top_freq_cat = freq_counts.idxmax()
    top_freq_count = freq_counts.max()

    top3_categories = categories[:3]
    candidates = [c for c in top3_categories if c['category'] not in ['주거']]
    
    # 7. AI 호출 (인사이트 생성)
    ai_result = generate_ai_insight(
        month=target_month,
        top_cat=most_spent_category,
        top_freq_cat=top_freq_cat,
        save_potential=save_potential,
        late_night_percent=late_night_percent,
        weekend_percent=weekend_percent,
        micro_count=micro_count,
        micro_sum=micro_sum,
        fixed_ratio=fixed_ratio,
        candidates=candidates,
        total_spent=spent
    )
    
    # 결과 반환 (Dict)
    return {
        "month": target_month,
        "total_income": income,
        "total_spent": spent,
        "save_potential": save_potential,
        "categories": categories,
        "top_category": top_cat['category'],
        "insight_list": ai_result['insight_list'],
        "suggestion_list": ai_result['suggestion_list'],
        "summary_suggestion": ai_result['summary_suggestion']
    }

def generate_ai_insight(month, top_cat, top_pct, freq_cat, freq_cnt, save_pot):
    prompt = f"""
    [분석 데이터: {month}]
    1. 지출 1위: {top_cat} ({top_pct}%)
    2. 빈도 1위: {freq_cat} (월 {freq_cnt}회)
    3. 저축 여력: 월 {save_pot:,}원

    위 데이터를 기반으로 JSON을 생성해.
    - insight_list: 4개의 주요 발견사항 (문장)
    - suggestion_list: 3개의 구체적 행동 제안 (문장)
    - summary_suggestion: 제안 중 하나를 20자 이내로 요약 (문장)
    말투는 친절한 해요체로.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[{"role": "system", "content": "너는 금융 코치야. JSON으로만 답해."}, 
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {
            "insight_list": ["AI 분석 중 오류가 발생했습니다."],
            "suggestion_list": ["잠시 후 다시 시도해주세요."],
            "summary_suggestion": "분석 오류"
        }