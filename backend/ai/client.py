import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_json(system_prompt: str, user_prompt: str, temperature=0.7):
    """
    JSON 응답을 보장하는 공통 함수
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=temperature
        )
        return response
    except Exception as e:
        print(f"AI 호출 에러: {e}")
        # 에러 발생 시 None 반환 또는 커스텀 예외 발생
        return None