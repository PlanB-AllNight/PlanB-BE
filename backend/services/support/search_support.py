import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime

from functools import lru_cache

from sqlmodel import Session, select

from backend.models.support import SupportPolicy, SupportCategory

# -------------------------------------------------------------------
# (옵션) BERT 기반 유사도 모델 로딩
# -------------------------------------------------------------------
@lru_cache()
def get_bert_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    except Exception:
        return None


# -------------------------------------------------------------------
# 1. NEGATION (제외 조건) 추출
# -------------------------------------------------------------------
def extract_negative_filters(query: str) -> Dict[str, List[str]]:
    """
    자연어에서 '국가장학금 말고', '월세 제외하고', '대출 빼고' 등을 감지.
    title/keywords에서 제외해야 할 단어 리스트 생성
    """
    negative = {"titles": [], "keywords": []}
    if not query:
        return negative

    q = query.lower().strip()

    NEG_PATTERNS = ["말고", "빼고", "제외", "말고는", "말곤", "말구", "제외하고"]

    for pat in NEG_PATTERNS:
        if pat in q:
            # 예: "국가장학금 말고" → "국가장학금"
            before = q.split(pat)[0].strip()
            if before:
                negative["titles"].append(before)
                negative["keywords"].append(before)

    return negative


# -------------------------------------------------------------------
# 2. 토픽 → 키워드 매핑 (의미 토픽을 실제 키워드들로 확장)
# -------------------------------------------------------------------
TOPIC_KEYWORD_MAP: Dict[str, List[str]] = {
    # 소득/알바/근로 관련
    "근로소득": ["알바", "아르바이트", "근로", "근로장학금", "교내근로", "국가근로", "학교알바", "일자리", "시급", "용돈벌기"],
    "생활비": ["생활비", "용돈", "생계비", "식비", "교통비", "주거비"],
    # 주거/월세 관련
    "주거": ["월세", "전세", "보증금", "자취", "원룸", "주거지원", "임대주택", "행복주택"],
    # 장학금/등록금
    "등록금": ["등록금", "학비", "수업료", "장학금", "국가장학금", "교내장학금"],
    # 취업/취준
    "취업": ["취업", "취준생", "구직", "면접", "정장대여", "정장", "취업지원", "일자리도약"],
    # 자격증/어학시험
    "자격증": ["자격증", "시험비", "응시료", "토익", "토플", "OPIC", "어학시험", "한국사시험"],
    # 창업
    "창업": ["창업", "스타트업", "사업", "사업화자금", "창업사관학교", "공간"],
    # 자산형성/적금/투자
    "자산형성": ["적금", "저축", "통장", "청약", "ISA", "소득공제", "내일저축", "자산형성", "청년통장"],
    # 정신건강/상담
    "멘탈": ["심리상담", "상담", "우울", "불안", "마음건강", "바우처", "멘탈케어"],
    # 문화/여가
    "문화": ["문화생활", "공연", "전시", "문화패스", "예술", "티켓", "공연관람", "문화예술패스"],
}

# -------------------------------------------------------------------
# 3. 생일 기반 나이 계산
# -------------------------------------------------------------------
def calculate_age_from_birth(birth_str: str) -> int:
    if not birth_str:
        return None

    try:
        # YYYYMMDD 형태로 파싱
        birth = datetime.strptime(birth_str, "%Y%m%d").date()
    except ValueError:
        return None

    today = date.today()
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age

# -------------------------------------------------------------------
# 4. 쿼리에서 토픽 후보 추출 (매우 가벼운 규칙 기반)
# -------------------------------------------------------------------
def extract_topics_from_query(query: str) -> List[str]:
    query = query or ""
    topics: List[str] = []

    # 학생/대학 관련 → 등록금/장학금 축
    if any(k in query for k in ["대학생", "재학생", "학비", "등록금", "장학금"]):
        topics.append("등록금")

    # 알바/근로 관련
    if any(k in query for k in ["알바", "아르바이트", "근로", "시급", "용돈"]):
        topics.append("근로소득")

    # 생활비
    if any(k in query for k in ["생활비", "생계비", "용돈", "교통비", "식비"]):
        topics.append("생활비")

    # 주거
    if any(k in query for k in ["월세", "전세", "보증금", "원룸", "자취", "전세자금", "주거"]):
        topics.append("주거")

    # 취업
    if any(k in query for k in ["취업", "취준", "면접", "정장", "이력서"]):
        topics.append("취업")

    # 자격증/시험
    if any(k in query for k in ["자격증", "토익", "토플", "오픽", "한국사", "시험비", "응시료"]):
        topics.append("자격증")

    # 창업
    if any(k in query for k in ["창업", "사업", "스타트업"]):
        topics.append("창업")

    # 자산형성
    if any(k in query for k in ["적금", "청약", "저축", "통장", "ISA", "소득공제", "청년통장"]):
        topics.append("자산형성")

    # 멘탈/상담
    if any(k in query for k in ["우울", "불안", "상담", "멘탈", "마음"]):
        topics.append("멘탈")

    # 문화
    if any(k in query for k in ["뮤지컬", "공연", "전시", "문화생활", "콘서트", "티켓"]):
        topics.append("문화")

    # 중복 제거 (순서 유지)
    return list(dict.fromkeys(topics))


# -------------------------------------------------------------------
# 5. (옵션) BERT 기반 키워드 확장
# -------------------------------------------------------------------
def expand_keywords_with_bert(
    base_keywords: List[str],
    all_keywords: List[str],
    threshold: float = 0.6,
    top_k: int = 5,
) -> List[str]:
    model = get_bert_model()
    if model is None:
        return base_keywords

    # util import (BERT 설치 안 된 환경 대응)
    try:
        from sentence_transformers import util
    except Exception:
        return base_keywords

    if not base_keywords or not all_keywords:
        return base_keywords

    base_emb = model.encode(base_keywords, convert_to_tensor=True)
    kw_emb = model.encode(all_keywords, convert_to_tensor=True)

    cos_scores = util.cos_sim(base_emb, kw_emb)

    expanded = set(base_keywords)

    for i in range(len(base_keywords)):
        scores = cos_scores[i]
        k = min(top_k, len(all_keywords))
        top_idx = scores.topk(k).indices.tolist()
        for idx in top_idx:
            if scores[idx] >= threshold:
                expanded.add(all_keywords[idx])

    return list(expanded)


# -------------------------------------------------------------------
# 6. 개별 정책에 점수 부여
# -------------------------------------------------------------------
def score_policy(
    policy: SupportPolicy,
    query_keywords: List[str],
    raw_query: str,
    negative_filters: Dict[str, List[str]],
) -> float:
    score = 0.0

    title = (policy.title or "").lower()
    subtitle = (policy.subtitle or "").lower()
    kw_text = (policy.keywords or "").lower()

    for banned in negative_filters["titles"]:
        if banned and (
            banned in title or
            banned in subtitle or
            banned in kw_text
        ):
            return 0.0

    # 1) 정책 keywords 파싱
    policy_keywords: List[str] = []
    if policy.keywords:
        try:
            loaded = json.loads(policy.keywords)
            if isinstance(loaded, list):
                policy_keywords = [str(k).strip() for k in loaded if str(k).strip()]
        except Exception:
            if isinstance(policy.keywords, str):
                policy_keywords = [
                    k.strip() for k in policy.keywords.split(",") if k.strip()
                ]

    # 2) 키워드 매칭 점수
    for qk in query_keywords:
        for pk in policy_keywords:
            if not pk:
                continue
            # 부분 일치 허용
            if qk in pk or pk in qk:
                score += 1.0

    # 3) raw query가 제목/부제에 직접 포함되면 가산점
    if raw_query:
        q = raw_query.strip()
        if q and q in (policy.title or ""):
            score += 1.0
        if q and q in (policy.subtitle or ""):
            score += 0.5

    return score

def compute_category_weights(query: str) -> Dict[str, float]:
    query = query.lower()

    weights = {
        "장학금/지원금": 1.0,
        "생활/복지": 1.0,
        "취업/진로": 1.0,
        "자산 형성": 1.0,
        "대출 상품": 1.0,
    }

    MAPPING = {
        # 취업 계열
        "취업": ("취업/진로", 4),
        "취준": ("취업/진로", 4),
        "면접": ("취업/진로", 4),
        "구직": ("취업/진로", 4),
        "자격증": ("취업/진로", 3),

        # 주거/월세
        "월세": ("장학금/지원금", 4),
        "전세": ("장학금/지원금", 4),
        "보증금": ("장학금/지원금", 4),

        # 장학금/등록금
        "장학금": ("장학금/지원금", 4),
        "등록금": ("장학금/지원금", 4),

        # 복지
        "교통비": ("생활/복지", 3),
        "식비": ("생활/복지", 3),

        # 자산 형성
        "저축": ("자산 형성", 3),
        "적금": ("자산 형성", 3),
        "투자": ("자산 형성", 3),

        # 대출
        "대출": ("대출 상품", 3),
        "학자금대출": ("대출 상품", 3),
        "월세": ("대출 상품", 2),
        "전세": ("대출 상품", 2),
        "보증금": ("대출 상품", 2),
    }

    for k, (cat, w) in MAPPING.items():
        if k in query:
            weights[cat] += w

    return weights


# -------------------------------------------------------------------
# 7. 전체 검색 로직 (필터링 + 키워드 스코어링)
# -------------------------------------------------------------------
def search_support_policies_ranked(
    session: Session,
    *,
    query: str,
    category: Optional[str],
    age: Optional[int],
    region: Optional[str],
    is_student: Optional[bool],
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    - 필터링(카테고리, 나이, 지역, 학생여부)
    - 후보 정책 리스트 조회
    - 자연어 → 토픽 추출 & 키워드 확장
    - (옵션) SBERT 의미 확장
    - 정책별 점수 계산 후 상위순 반환
    """
    
    negative_filters = extract_negative_filters(query)

    # 1. 기본 필터링
    filters = []

    # 카테고리
    if category:
        try:
            enum_category = SupportCategory(category)
            filters.append(SupportPolicy.category == enum_category)
        except ValueError:
            # 잘못된 카테고리 값이면 무시 (필터 X)
            pass

    # 나이
    if age:
        filters.append(
            (SupportPolicy.age_min.is_(None)) | (SupportPolicy.age_min <= age)
        )
        filters.append(
            (SupportPolicy.age_max.is_(None)) | (SupportPolicy.age_max >= age)
        )

    # 지역
    if region:
        filters.append(
            (SupportPolicy.region == "전국")
            | (SupportPolicy.region.contains(region))
        )

    # 학생 여부
    if is_student is not None:
        if is_student:
            # 학생이면 학생 전용 + 일반 정책 모두 허용
            filters.append(
                (SupportPolicy.student_only.is_(None))
                | (SupportPolicy.student_only == False)
                | (SupportPolicy.student_only == True)
            )
        else:
            # 학생 아니면 학생 전용은 제외
            filters.append(
                (SupportPolicy.student_only.is_(None))
                | (SupportPolicy.student_only == False)
            )

    # 2. 후보 정책 조회
    stmt = select(SupportPolicy)
    for f in filters:
        stmt = stmt.where(f)

    candidates: List[SupportPolicy] = session.exec(stmt).all()

    if not candidates:
        return {
            "status": "empty",
            "message": "조건에 맞는 지원 정책을 찾지 못했습니다.",
            "data": [],
        }

    # 3. 쿼리 → 토픽 & 키워드 생성
    raw_query = query or ""

    # LLM에서 topics 넘겨줄 수도 있고, 없으면 쿼리 기반으로 추출
    topics_from_query = extract_topics_from_query(raw_query)
    topics = topics or []
    topics = list(dict.fromkeys(topics + topics_from_query))

    # topics → 키워드 풀로 확장
    base_keywords: List[str] = []

    for t in topics:
        if t in TOPIC_KEYWORD_MAP:
            base_keywords.extend(TOPIC_KEYWORD_MAP[t])

    # 쿼리에서 간단 키워드도 뽑아서 같이 넣기 (띄어쓰기 기반)
    for token in raw_query.replace(",", " ").split():
        token = token.strip()
        if len(token) >= 2:  # 너무 짧은 단어 제거
            base_keywords.append(token)

    # 중복 제거
    base_keywords = list(dict.fromkeys(base_keywords))

    # 4. SBERT로 의미 확장 (옵션)
    # 전체 후보 정책 keywords 풀 수집
    all_keywords: List[str] = []
    for p in candidates:
        if p.keywords:
            try:
                kws = json.loads(p.keywords)
                if isinstance(kws, list):
                    all_keywords.extend([str(k).strip() for k in kws if str(k).strip()])
            except Exception:
                continue
    all_keywords = list(dict.fromkeys(all_keywords))

    if base_keywords and all_keywords:
        query_keywords = expand_keywords_with_bert(base_keywords, all_keywords)
    else:
        query_keywords = base_keywords

    # 카테고리 가중치 계산
    category_weights = compute_category_weights(raw_query)

    # 5. 정책별 점수 계산
    scored: List[Tuple[float, SupportPolicy]] = []
    for p in candidates:
        s = score_policy(p, query_keywords, raw_query, negative_filters)

        category_name = p.category.value
        weight = category_weights.get(category_name, 1.0)
        s *= weight

        scored.append((s, p))

    # 0점 정책 컷
    scored = [item for item in scored if item[0] > 0.0]
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        # 필터 조건에는 맞지만, 키워드 매칭이 전혀 안 된 경우
        return {
            "status": "no_keyword_match",
            "message": "조건에 맞는 정책은 있지만, 질문과 직접 연관된 키워드는 찾지 못했습니다.",
            "data": [
                {
                    "id": p.id,
                    "title": p.title,
                    "subtitle": p.subtitle,
                    "pay_method": p.pay_method,
                    "category": p.category.value,
                }
                for p in candidates
            ],
        }

    # 6. 최종 결과
    result_list = []
    for s, p in scored:
        result_list.append(
            {
                "id": p.id,
                "title": p.title,
                "subtitle": p.subtitle,
                "pay_method": p.pay_method,
                "category": p.category.value,
                "score": s,
            }
        )
    
    # 상위 5개만 출력
    TOP_N = 5
    result_list = result_list[:TOP_N]

    return {
        "status": "ok",
        "message": None,
        "data": result_list,
    }