import os

from openai import OpenAI


def get_openai_client() -> OpenAI:
    """OPENAI_BASE_URL을 지정하면 OpenAI 호환 엔드포인트(프록시, 로컬 스텁 등)로 보낸다."""
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL") or None)
