import json
import random
import argparse
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

INITIAL_BALANCE = 2000000

BASE_PATTERNS = {
    "카페": {
        "stores": ["스타벅스", "이디야커피", "투썸플레이스", "메가커피", "컴포즈커피", "블루보틀"],
        "amount_range": (4000, 12000), 
        "frequency": 0.7, 
        "time_slots": [(8, 10), (12, 14), (19, 21)]
    },
    "식비": {
        "stores": ["학식", "배달의민족", "쿠팡이츠", "맥도날드", "김밥천국", "써브웨이", "파리바게뜨"],
        "amount_range": (5000, 20000), 
        "frequency": 0.9, 
        "time_slots": [(11, 14), (17, 20)]
    },
    "편의점": {
        "stores": ["GS25", "CU", "세븐일레븐"],
        "amount_range": (2000, 10000), 
        "frequency": 0.5, 
        "time_slots": [(8, 10), (20, 23)]
    },
    "교통": {
        "stores": ["지하철", "버스", "카카오T", "택시"],
        "amount_range": (1400, 15000), 
        "frequency": 0.6, 
        "time_slots": [(8, 9), (18, 20)]
    },
    "쇼핑": {
        "stores": ["쿠팡", "네이버페이", "무신사", "지그재그", "올리브영"],
        "amount_range": (20000, 150000), 
        "frequency": 0.15, 
        "time_slots": [(10, 23)]
    },
    "사회": {
        "stores": ["동아리 회비", "술집", "노래방", "회식", "인생네컷"],
        "amount_range": (20000, 70000), 
        "frequency": 0.1, 
        "time_slots": [(18, 24)]
    },
    "여가": {
        "stores": ["CGV", "롯데시네마", "PC방", "볼링장", "보드게임카페"],
        "amount_range": (8000, 25000), 
        "frequency": 0.2, 
        "time_slots": [(14, 22)]
    },
    "구독": { 
        "stores": ["넷플릭스", "유튜브프리미엄", "멜론"],
        "amount_range": (10000, 17000),
        "frequency": 0.03, # 월 1회 정도
        "time_slots": [(9, 10)]
    },
    "저축": {
        "stores": ["카카오뱅크 세이프박스", "토스 모으기", "주택청약"],
        "amount_range": (10000, 100000), 
        "frequency": 0.07, 
        "time_slots": [(20, 23)]
    }
}

BASE_FIXED_EXPENSES = [
    {"day": 25, "store": "집주인(월세)", "category": "주거", "amount": 500000},
    {"day": 10, "store": "통신비", "category": "통신", "amount": 65000},
]

PERSONAS = {
    "BALANCE": {
        "desc": "밸런스형 (2025.06.28 기준)",
        "end_date_str": "2025-06-28",
        "income_sources": [
            {"day": 10, "name": "아르바이트 급여", "amount": 600000},
            {"day": 25, "name": "부모님 용돈", "amount": 400000}
        ],
        "multipliers": {}
    },
    "OVERSPENDER": {
        "desc": "과소비형 (2025.08.22 기준)",
        "end_date_str": "2025-08-22",
        "income_sources": [
            {"day": 10, "name": "카페 알바", "amount": 550000}, 
            {"day": 1, "name": "부모님 용돈", "amount": 500000} 
        ],
        "multipliers": {
            "카페": {"freq": 1.5, "amount": 1.2},
            "식비": {"freq": 1.3, "amount": 1.5}, 
            "쇼핑": {"freq": 2.5, "amount": 1.5},
            "교통": {"freq": 1.5, "amount": 2.0}, 
            "저축": {"freq": 0.0, "amount": 0.0}
        }
    },
    "SAVER": {
        "desc": "저축형 (2025.09.17 기준)",
        "end_date_str": "2025-09-17",
        "income_sources": [
            {"day": 5, "name": "편의점 알바", "amount": 700000},
            {"day": 15, "name": "근로장학금", "amount": 400000},
            {"day": 25, "name": "부모님 용돈", "amount": 100000}
        ],
        "multipliers": {
            "카페": {"freq": 0.3, "amount": 0.5},
            "식비": {"freq": 0.7, "amount": 0.7},
            "쇼핑": {"freq": 0.2, "amount": 0.5},
            "사회": {"freq": 0.4, "amount": 0.6},
            "저축": {"freq": 3.0, "amount": 1.5}
        }
    },
    "NIGHT_OWL": {
        "desc": "야행성 (2025.11.30 기준)",
        "end_date_str": "2025-11-30",
        "income_sources": [
            {"day": 5, "name": "야간 PC방 알바", "amount": 900000},
            {"day": 20, "name": "부모님 용돈", "amount": 200000}
        ],
        "multipliers": {
            "식비": {"freq": 1.3, "amount": 1.3},
            "교통": {"freq": 1.5, "amount": 2.5},
            "여가": {"freq": 1.5, "amount": 1.0}
        },
        "time_shift": 4
    },
    "RANDOM": {
        "desc": "완전 랜덤형 (2025.12.31 기준)",
        "end_date_str": "2025-12-31",
        "income_sources": [
            {"day": 5, "name": "아르바이트 급여", "amount": 500000},
            {"day": 10, "name": "부모님 송금", "amount": 600000}
        ],
        "multipliers": {}
    }
}


def get_random_time(start_h, end_h):
    h = random.randint(start_h, end_h) % 24
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return f"{h:02d}:{m:02d}:{s:02d}"

def calculate_dates(end_date_str):
    """
    종료일 기준 3개월 전 달의 1일 시작일 계산
    예: End(2025-06-28) -> Start(2025-03-01)
    """
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    start_date = (end_date - relativedelta(months=3)).replace(day=1)
    return start_date, end_date

def generate_transactions(persona_key="BALANCE"):
    persona = PERSONAS.get(persona_key, PERSONAS["BALANCE"])
    
    start_date, end_date = calculate_dates(persona["end_date_str"])
    print(f"[{persona_key}] 데이터 생성 중...")
    print(f"   기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

    incomes = persona["income_sources"]
    multipliers = persona.get("multipliers", {})
    time_shift = persona.get("time_shift", 0)

    transactions = []
    balance = INITIAL_BALANCE
    tx_cnt = 1
    
    curr = start_date
    while curr <= end_date:
        date_str = curr.strftime("%Y-%m-%d")
        day = curr.day

        for fixed in BASE_FIXED_EXPENSES:
            if day == fixed["day"]:
                balance -= fixed["amount"]
                transactions.append({
                    "transactionId": f"TRX{curr.strftime('%Y%m%d')}{tx_cnt:04d}",
                    "date": date_str, "time": "09:00:00",
                    "type": "출금", "store": fixed["store"], "category": fixed["category"],
                    "amount": fixed["amount"], "balance": balance, "paymentMethod": "계좌이체"
                })
                tx_cnt += 1

        for inc in incomes:
            if day == inc["day"]:
                balance += inc["amount"]
                transactions.append({
                    "transactionId": f"TRX{curr.strftime('%Y%m%d')}{tx_cnt:04d}",
                    "date": date_str, "time": "10:00:00",
                    "type": "입금", "store": inc["name"], "category": "수입",
                    "amount": inc["amount"], "balance": balance, "paymentMethod": "계좌이체"
                })
                tx_cnt += 1

        for cat, rule in BASE_PATTERNS.items():
            mult = multipliers.get(cat, {"freq": 1.0, "amount": 1.0})
            
            final_freq = rule["frequency"] * mult["freq"]
            
            if random.random() < final_freq:
                store = random.choice(rule["stores"])
                
                min_amt = int(rule["amount_range"][0] * mult["amount"])
                max_amt = int(rule["amount_range"][1] * mult["amount"])
                amount = random.randint(min_amt, max_amt)
                amount = (amount // 100) * 100

                t_slot = random.choice(rule["time_slots"])
                start_h = (t_slot[0] + time_shift) % 24
                end_h = (t_slot[1] + time_shift) % 24
                
                if start_h > end_h: end_h += 24
                
                tx_time = get_random_time(start_h, end_h)

                balance -= amount
                transactions.append({
                    "transactionId": f"TRX{curr.strftime('%Y%m%d')}{tx_cnt:04d}",
                    "date": date_str, "time": tx_time,
                    "type": "출금", "store": store, "category": cat,
                    "amount": amount, "balance": balance,
                    "paymentMethod": "체크카드" if amount < 50000 else "신용카드"
                })
                tx_cnt += 1

        curr += timedelta(days=1)

    transactions.sort(key=lambda x: (x["date"], x["time"]))
    
    final_balance = INITIAL_BALANCE
    for i, tx in enumerate(transactions):
        tx["transactionId"] = f"TRX{tx['date'].replace('-', '')}{i+1:04d}"
        if tx["type"] == "입금":
            final_balance += tx["amount"]
        else:
            final_balance -= tx["amount"]
        tx["balance"] = final_balance

    return transactions


def main():
    parser = argparse.ArgumentParser(description="PlanB 데이터 생성기 (Multi-Persona)")
    parser.add_argument("--persona", type=str, default="BALANCE",
                        choices=["BALANCE", "OVERSPENDER", "SAVER", "NIGHT_OWL", "RANDOM"],
                        help="생성할 페르소나 선택")
    
    args = parser.parse_args()
    
    data = generate_transactions(args.persona)
    
    filename = "mydata_3months.json" 
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"생성 완료: {filename}")
    print(f"   - 페르소나: {args.persona} ({PERSONAS[args.persona]['desc']})")
    print(f"   - 기간: {data[0]['date']} ~ {data[-1]['date']}")
    print(f"   - 총 거래: {len(data)}건")
    print(f"   - 최종 잔액: {data[-1]['balance']:,}원")

if __name__ == "__main__":
    main()