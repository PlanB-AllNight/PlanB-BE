"""
대학생 소비 패턴 기반 3개월 거래 데이터 생성기
- 기간: 2024년 9월 1일 ~ 11월 30일
- 현실적인 소비 패턴 반영
"""

import json
import random
from datetime import datetime, timedelta

# 초기 잔액
INITIAL_BALANCE = 1500000

# 카테고리별 거래 패턴
TRANSACTIONS_PATTERNS = {
    "카페": {
        "stores": ["스타벅스", "이디야커피", "투썸플레이스", "할리스커피", "파스쿠찌", "카페베네"],
        "amount_range": (3500, 9000),
        "frequency": 0.7,  # 하루 발생 확률 70%
        "time_slots": [(9, 11), (14, 16), (19, 21)]
    },
    "식비": {
        "stores": ["학교 학식", "배달의민족", "쿠팡이츠", "맥도날드", "롯데리아", "버거킹", "파리바게뜨"],
        "amount_range": (4000, 18000),
        "frequency": 0.9,  # 하루 발생 확률 90%
        "time_slots": [(12, 14), (18, 20)]
    },
    "편의점": {
        "stores": ["GS25", "CU", "세븐일레븐"],
        "amount_range": (2000, 8000),
        "frequency": 0.5,
        "time_slots": [(8, 10), (20, 23)]
    },
    "교통": {
        "stores": ["지하철", "버스", "카카오T", "택시"],
        "amount_range": (1500, 15000),
        "frequency": 0.6,
        "time_slots": [(8, 9), (18, 20)]
    },
    "쇼핑": {
        "stores": ["쿠팡", "네이버페이", "무신사", "지마켓"],
        "amount_range": (20000, 100000),
        "frequency": 0.15,  # 일주일에 1번 정도
        "time_slots": [(14, 23)]
    },
    "사회": {
        "stores": ["동아리 회비", "술집", "노래방", "회식"],
        "amount_range": (25000, 60000),
        "frequency": 0.1,  # 10일에 1번
        "time_slots": [(18, 23)]
    },
    "여가": {
        "stores": ["CGV", "롯데시네마", "PC방", "볼링장"],
        "amount_range": (8000, 20000),
        "frequency": 0.2,
        "time_slots": [(14, 22)]
    },
    "뷰티": {
        "stores": ["올리브영", "다이소", "미용실"],
        "amount_range": (10000, 35000),
        "frequency": 0.15,
        "time_slots": [(12, 20)]
    },
    "도서": {
        "stores": ["교보문고", "YES24", "알라딘"],
        "amount_range": (15000, 40000),
        "frequency": 0.1,
        "time_slots": [(12, 20)]
    },
    "학습": {
        "stores": ["학원비", "인강", "교재비"],
        "amount_range": (50000, 200000),
        "frequency": 0.05,  # 한 달에 1~2번
        "time_slots": [(10, 18)]
    },
    "패션": {
        "stores": ["무신사", "지그재그", "옷가게"],
        "amount_range": (50000, 150000),
        "frequency": 0.08,
        "time_slots": [(14, 22)]
    }
}

# 고정 지출 (매월)
FIXED_EXPENSES = [
    {"day": 1, "store": "넷플릭스", "category": "구독", "amount": 13500, "method": "자동결제"},
    {"day": 5, "store": "멜론", "category": "구독", "amount": 10900, "method": "자동결제"},
    {"day": 9, "store": "KT 통신비", "category": "통신", "amount": 55000, "method": "자동이체"},
]

# 수입 패턴
INCOME_PATTERNS = [
    {"day": 5, "store": "아르바이트 급여", "amount": 500000},
    {"day": 10, "store": "부모님 송금", "amount": 600000},
]

def generate_time(time_slots):
    """시간대 범위에서 랜덤 시간 생성"""
    slot = random.choice(time_slots)
    hour = random.randint(slot[0], slot[1])
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return f"{hour:02d}:{minute:02d}:{second:02d}"

def generate_transactions(start_date, end_date):
    """3개월 거래 데이터 생성"""
    transactions = []
    balance = INITIAL_BALANCE
    tx_id_counter = 1
    
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 1. 고정 지출 추가
        for fixed in FIXED_EXPENSES:
            if current_date.day == fixed["day"]:
                tx_time = "00:05:00"
                balance -= fixed["amount"]
                
                transactions.append({
                    "transactionId": f"TRX{date_str.replace('-', '')}{tx_id_counter:04d}",
                    "date": date_str,
                    "time": tx_time,
                    "type": "출금",
                    "store": fixed["store"],
                    "category": fixed["category"],
                    "amount": fixed["amount"],
                    "balance": balance,
                    "paymentMethod": fixed["method"]
                })
                tx_id_counter += 1
        
        # 2. 수입 추가
        for income in INCOME_PATTERNS:
            if current_date.day == income["day"]:
                tx_time = "23:59:59"
                balance += income["amount"]
                
                transactions.append({
                    "transactionId": f"TRX{date_str.replace('-', '')}{tx_id_counter:04d}",
                    "date": date_str,
                    "time": tx_time,
                    "type": "입금",
                    "store": income["store"],
                    "category": "수입",
                    "amount": income["amount"],
                    "balance": balance,
                    "paymentMethod": "계좌이체"
                })
                tx_id_counter += 1
        
        # 3. 일반 거래 생성
        for category, pattern in TRANSACTIONS_PATTERNS.items():
            # 확률적으로 거래 발생 여부 결정
            if random.random() < pattern["frequency"]:
                store = random.choice(pattern["stores"])
                amount = random.randint(pattern["amount_range"][0], pattern["amount_range"][1])
                tx_time = generate_time(pattern["time_slots"])
                
                # 결제 수단 랜덤
                methods = ["체크카드", "신용카드", "간편결제", "현금"]
                method = random.choice(methods)
                
                balance -= amount
                
                transactions.append({
                    "transactionId": f"TRX{date_str.replace('-', '')}{tx_id_counter:04d}",
                    "date": date_str,
                    "time": tx_time,
                    "type": "출금",
                    "store": store,
                    "category": category,
                    "amount": amount,
                    "balance": balance,
                    "paymentMethod": method
                })
                tx_id_counter += 1
        
        current_date += timedelta(days=1)
    
    # 시간순 정렬
    transactions.sort(key=lambda x: (x["date"], x["time"]))
    
    # transactionId 재번호 부여
    for i, tx in enumerate(transactions, 1):
        date_part = tx["date"].replace("-", "")
        tx["transactionId"] = f"TRX{date_part}{i:04d}"
    
    return transactions

def main():
    """메인 실행 함수"""
    start = datetime(2024, 9, 1)
    end = datetime(2024, 11, 30)
    
    print("🔄 거래 데이터 생성 중...")
    transactions = generate_transactions(start, end)
    
    print(f"✅ 총 {len(transactions)}건의 거래 생성 완료!")
    
    # JSON 파일로 저장
    with open("mydata_3months.json", "w", encoding="utf-8") as f:
        json.dump(transactions, f, ensure_ascii=False, indent=2)
    
    # 통계 출력
    total_income = sum(tx["amount"] for tx in transactions if tx["type"] == "입금")
    total_expense = sum(tx["amount"] for tx in transactions if tx["type"] == "출금")
    
    print(f"\n📊 통계:")
    print(f"- 기간: 2024-09-01 ~ 2024-11-30 (3개월)")
    print(f"- 총 거래: {len(transactions)}건")
    print(f"- 총 수입: {total_income:,}원")
    print(f"- 총 지출: {total_expense:,}원")
    print(f"- 순 자산 변화: {total_income - total_expense:,}원")
    print(f"- 최종 잔액: {transactions[-1]['balance']:,}원")
    
    # 카테고리별 통계
    category_stats = {}
    for tx in transactions:
        if tx["type"] == "출금":
            category = tx["category"]
            category_stats[category] = category_stats.get(category, 0) + tx["amount"]
    
    print(f"\n📈 카테고리별 지출:")
    for cat, amount in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"- {cat}: {amount:,}원")

if __name__ == "__main__":
    main()