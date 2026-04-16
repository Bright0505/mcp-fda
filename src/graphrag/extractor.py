"""LLM 萃取器 — 將 FDA drug_interactions 原文結構化為實體關係 JSON。"""

import json
import logging
from typing import List, Optional

from openai import AsyncOpenAI

from graphrag.config import GraphRAGConfig

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """你是一位藥物交互作用資料萃取專家。
你的任務是將 FDA 藥品仿單中的 drug_interactions 原文，萃取成結構化的 JSON 格式。

輸出格式（JSON only，不要有任何其他文字）：
{
  "interactions": [
    {
      "drug_1": "被查詢的主藥品英文名（generic name）",
      "drug_2": "交互作用的另一種藥品名",
      "relation": "關係類型（從以下選一）：interacts_with / contraindicated / increases_effect / decreases_effect / monitor_closely",
      "severity": "嚴重程度：major / moderate / minor / unknown",
      "evidence": "支持此關係的簡短說明（100字以內英文）"
    }
  ]
}

規則：
1. 每個交互作用藥物組合對應一個 JSON 物件
2. drug_2 優先使用提供的本地藥品白名單中的英文名稱
3. 若對方藥品不在白名單，使用 FDA 原文中的名稱
4. 若無明確藥品名，略過（不要生成空白 drug_2）
5. severity=unknown 用於原文未明確標示嚴重程度的情況
6. 只輸出 JSON，不要有 markdown code fence 或說明文字"""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=GraphRAGConfig.LLM_BASE_URL,
        api_key=GraphRAGConfig.LLM_API_KEY or "dummy",
        timeout=GraphRAGConfig.LLM_TIMEOUT,
    )


async def extract_interactions(
    drug_name: str,
    interaction_text: str,
    local_whitelist: Optional[List[str]] = None,
) -> List[dict]:
    """呼叫 LLM 萃取交互作用關係。

    Args:
        drug_name: 主藥品英文名
        interaction_text: FDA drug_interactions 原文
        local_whitelist: 本地 drug_permits.name_en 列表（最多 200 筆）

    Returns:
        List of interaction dicts，每個包含 drug_1/drug_2/relation/severity/evidence
        萃取失敗時回傳 [] 並記錄 warning
    """
    whitelist_hint = ""
    if local_whitelist:
        sample = local_whitelist[:200]
        whitelist_hint = f"\n\n本地合法藥品清單（優先對齊 drug_2）：\n{', '.join(sample)}"

    user_content = (
        f"主藥品: {drug_name}\n\n"
        f"FDA drug_interactions 原文:\n{interaction_text[:4000]}"
        f"{whitelist_hint}"
    )

    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=GraphRAGConfig.LLM_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        interactions = data.get("interactions", [])
        logger.info(f"萃取成功: {drug_name} → {len(interactions)} 筆關係")
        return interactions
    except json.JSONDecodeError as e:
        logger.warning(f"LLM 輸出非 JSON ({drug_name}): {e}")
        return []
    except Exception as e:
        logger.warning(f"LLM 萃取失敗 ({drug_name}): {e}")
        return []
