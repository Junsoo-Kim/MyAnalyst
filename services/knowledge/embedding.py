# embedding.py — KLUE-BERT 임베딩. 모델은 knowledge 서비스에만 올라간다(생성 워커는 torch 없이 동작).
from typing import Optional

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

import config

tokenizer: Optional[AutoTokenizer] = None
embedding_model: Optional[AutoModel] = None
device: Optional[torch.device] = None


def initialize_models():
    """Initializes the tokenizer and embedding model."""
    global tokenizer, embedding_model, device
    if tokenizer is None or embedding_model is None:
        print("Initializing embedding model and tokenizer...")
        try:
            tokenizer = AutoTokenizer.from_pretrained(config.EMBEDDING_MODEL_NAME)
            embedding_model = AutoModel.from_pretrained(config.EMBEDDING_MODEL_NAME)
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            embedding_model.to(device)
            embedding_model.eval() # Set to evaluation mode
            print(f"Embedding models initialized on device: {device}")
        except Exception as e:
            print(f"Fatal Error initializing embedding models: {e}")
            raise RuntimeError(f"Could not initialize embedding models: {e}")


def get_tokenizer() -> Optional[AutoTokenizer]:
    """초기화 전이면 None. BM25 토큰화는 이 경우 공백 분리로 폴백한다(단위 테스트에서 모델 없이 동작)."""
    return tokenizer


def mean_pooling(model_output, attention_mask):
    """Mean Pooling helper function."""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    return sum_embeddings / sum_mask


def get_embedding(text: str) -> Optional[np.ndarray]:
    """Generates an embedding vector for the given text."""
    initialize_models()
    try:
        encoded_input = tokenizer(
            text, padding=True, truncation=True, max_length=512, return_tensors='pt'
        ).to(device)
        with torch.no_grad():
            model_output = embedding_model(**encoded_input)
        embedding = mean_pooling(model_output, encoded_input['attention_mask'])
        return embedding.cpu().numpy().flatten() # Return as NumPy array
    except Exception as e:
        print(f"Error generating embedding for text '{text[:50]}...': {e}")
        return None
