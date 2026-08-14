"""LLM 萃取器 — 將 FDA drug_interactions 原文結構化為實體關係 JSON。"""

import asyncio
import json
import logging
from typing import List, Optional

from openai import AsyncOpenAI

from graphrag.config import GraphRAGConfig

logger = logging.getLogger(__name__)

# 單次送進 LLM 的原文上限。原文超過此長度時分段處理，**不截斷**。
#
# 為什麼要分段而不是截斷（2026-08-14 修正）
# ------------------------------------------
# 原本的做法是 `interaction_text[:4000]`，直接丟掉超出部分。實測 16 個常見藥品的
# FDA 原文長度：平均 6,377 字元，**10 個（63%）超過 4,000**，最長的
# Sertraline 有 23,937 字元 —— 等於 83% 的內容從未進到 LLM。
#
# 這不是理論問題。Digoxin 的 `St. John's Wort`（強效 P-gp 誘導劑，會顯著降低血中
# 濃度）出現在原文第 ~4,400 字元處，永遠讀不到；`Alprazolam`／`Atorvastatin` 的
# 圖譜對象數是 0，兩者原文都超過 4,000。
#
# 段落大小另有輸出面的考量，見 LLM_MAX_TOKENS。
CHUNK_CHARS = 2200

# 分段時前後重疊的字元數，避免一組交互作用剛好被切在邊界上而兩段都讀不完整。
CHUNK_OVERLAP = 300

# 分段之間的併發上限。萃取走 LiteLLM，過高的併發會排擠線上請求。
MAX_CONCURRENT_CHUNKS = 3

# 單次回應的輸出上限。
#
# 這裡的關鍵事實是**輸出可能比輸入長**：仿單常有「以下藥物皆會影響本藥」後面接
# 一長串藥名（Digoxin 的 P-gp inducer 清單有數十個），每個名字都展開成一筆帶
# evidence 的 JSON 物件。實測 3,500 字元的原文段落產生的 JSON 超過 4,096 tokens
# 而被硬切斷，St. John's Wort 就落在被切掉的部分。
#
# 因此兩邊一起調：段落縮小到 2,200 字元（單段關係數變少），輸出上限提高到 8,192。
# 代價是段數增加約 40%，換取的是不再靜默漏掉整段尾巴的內容。
LLM_MAX_TOKENS = 8192

# 輸出仍被截斷時，把該段對半切開重跑幾次。
#
# 為什麼不直接把 CHUNK_CHARS 再調小：截斷是少數段落的問題（Top 20 實測 20 支藥中
# 9 支出現，且集中在關係密度特別高的段落），全面縮小會讓每一支藥都付出更多呼叫。
# 遞迴細分只對真正出問題的段落付這個成本。
MAX_SPLIT_RETRIES = 2

# 小於此長度就不再細分——再切下去只會把一句話切成兩半，反而讓兩邊都萃不出完整關係。
MIN_SPLIT_CHARS = 600

EXTRACTION_SYSTEM_PROMPT = """你是一位藥物交互作用資料萃取專家。
你的任務是將 FDA 藥品仿單中的 drug_interactions 原文，萃取成結構化的 JSON 格式。

輸出格式（JSON only，不要有任何其他文字）：
{
  "interactions": [
    {
      "drug_1": "被查詢的主藥品英文名（generic name）",
      "drug_2": "與其產生交互作用的另一個物質名稱",
      "entity_type": "drug / supplement / food / class",
      "relation": "關係類型（從以下選一）：interacts_with / contraindicated / increases_effect / decreases_effect / monitor_closely",
      "severity": "嚴重程度：major / moderate / minor / unknown",
      "evidence": "支持此關係的簡短說明（100字以內英文）"
    }
  ]
}

**drug_2 的範圍（重要）**：不限於處方藥。仿單的交互作用段落也會記載
膳食補充劑、草藥、維生素礦物質與食物，這些對臨床同樣重要，**必須一併萃取**。
用 entity_type 標示類別：

- `drug`：處方藥或成藥（如 warfarin、ciprofloxacin）
- `supplement`：膳食補充劑、草藥、維生素、礦物質
  （如 St. John's Wort、Ginkgo、Ginseng、Ashwagandha、fish oil、
   calcium、iron、magnesium、vitamin K、niacin、ascorbic acid、bromelain）
- `food`：食物或飲品（如 grapefruit juice、alcohol、high-bran meals、dairy）
- `class`：藥理分類或群組（如 Antacids、Proton Pump Inhibitors、NSAIDs、
   Anticoagulants、Sympathomimetics）

規則：
1. 每個交互作用組合對應一個 JSON 物件
2. drug_2 若為處方藥，優先使用提供的本地藥品白名單中的英文名稱
3. 白名單只涵蓋藥品；**補充劑、草藥、食物不在白名單中屬正常**，
   直接使用 FDA 原文中的名稱，不要因為不在白名單就略過
4. 若無明確的物質名稱（例如只寫「其他藥物」這種泛稱），才略過
5. severity=unknown 用於原文未明確標示嚴重程度的情況
6. 只輸出 JSON，不要有 markdown code fence 或說明文字"""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=GraphRAGConfig.LLM_BASE_URL,
        api_key=GraphRAGConfig.LLM_API_KEY or "dummy",
        timeout=GraphRAGConfig.LLM_TIMEOUT,
    )


def split_text(text: str) -> List[str]:
    """把原文切成帶重疊的片段；短文回傳單一片段。

    重疊是為了處理「交互作用寫在句子邊界上」的情況 —— 例如
    「...與 St. John's Wort 併用時 / 應監測血中濃度」被切開後，
    前段有藥名沒有後果、後段有後果沒有藥名，兩段都萃不出完整關係。
    """
    if len(text) <= CHUNK_CHARS:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_CHARS])
        start += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def _salvage(raw: str) -> List[dict]:
    """從被截斷的 JSON 中救回已完整的 interaction 物件。

    `response_format=json_object` 保證格式，但保證不了長度——超過輸出上限時
    字串會在任意位置斷掉。用堆疊記錄每個 `{` 的位置，遇到配對的 `}` 就取出該段
    嘗試解析：**任何巢狀深度**的完整物件都會被檢查，因為外層 wrapper 的大括號
    在截斷時永遠不會閉合，只看最外層會一筆都救不到。被切掉的那個物件自然落空。
    """
    items: List[dict] = []
    stack: List[int] = []
    in_str = False
    escape = False
    for i, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            try:
                obj = json.loads(raw[start:i + 1])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("drug_2"):
                items.append(obj)
    return items


def _dedupe(interactions: List[dict]) -> List[dict]:
    """依 (drug_2, relation) 去重 —— 重疊區段會讓同一組關係被萃取兩次。

    保留先出現者，但若後者有 evidence 而前者沒有，改用後者：分段邊界上
    較完整的那一段通常出現在後面。
    """
    out: List[dict] = []
    index: dict = {}
    for item in interactions:
        d2 = str(item.get("drug_2") or "").strip()
        if not d2:
            continue
        key = (d2.upper(), str(item.get("relation") or "").lower())
        if key not in index:
            index[key] = len(out)
            out.append(item)
        elif not (out[index[key]].get("evidence") or "").strip():
            out[index[key]] = item
    return out


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
        List of interaction dicts，每個包含
        drug_1/drug_2/entity_type/relation/severity/evidence。
        萃取失敗時回傳 [] 並記錄 warning；**分段中只要有一段成功就回傳該段結果**，
        不因單段失敗而丟棄全部。
    """
    if not (interaction_text or "").strip():
        return []

    whitelist_hint = ""
    if local_whitelist:
        sample = local_whitelist[:200]
        whitelist_hint = (
            "\n\n本地合法藥品清單（drug_2 為處方藥時優先對齊；"
            f"補充劑／草藥／食物不在此清單中屬正常）：\n{', '.join(sample)}"
        )

    chunks = split_text(interaction_text)
    client = _get_client()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

    async def call_llm(chunk: str) -> str:
        """實際的 LLM 呼叫。

        semaphore 只包住這裡，**不包住遞迴** —— 若在遞迴外層持有，細分時的子呼叫
        會等待一個永遠不會被釋放的名額而死鎖。
        """
        async with semaphore:
            resp = await client.chat.completions.create(
                model=GraphRAGConfig.LLM_MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": chunk},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=LLM_MAX_TOKENS,
            )
            return resp.choices[0].message.content or "{}"

    def build_prompt(chunk: str, label: str) -> str:
        return (
            f"主藥品: {drug_name}\n\n"
            f"FDA drug_interactions 原文{label}:\n{chunk}"
            f"{whitelist_hint}"
        )

    async def extract_chunk(chunk: str, label: str, depth: int = 0) -> List[dict]:
        try:
            raw = await call_llm(build_prompt(chunk, label))
        except Exception as e:
            logger.warning(f"LLM 萃取失敗 ({drug_name} {label}): {e}")
            return []

        try:
            return json.loads(raw).get("interactions", []) or []
        except json.JSONDecodeError:
            pass

        # 輸出被截斷。先試著細分重跑 —— 較短的原文會產生較短的 JSON。
        if depth < MAX_SPLIT_RETRIES and len(chunk) >= MIN_SPLIT_CHARS:
            mid = len(chunk) // 2
            left, right = chunk[:mid + CHUNK_OVERLAP], chunk[mid - CHUNK_OVERLAP:]
            logger.info(
                f"輸出被截斷 ({drug_name} {label})，細分重跑（第 {depth + 1} 次）"
            )
            halves = await asyncio.gather(
                extract_chunk(left, f"{label}a", depth + 1),
                extract_chunk(right, f"{label}b", depth + 1),
            )
            merged = [item for part in halves for item in part]
            if merged:
                return merged

        # 已經切到不能再切，或細分後仍無所獲：從截斷的輸出救回完整的物件。
        rescued = _salvage(raw)
        if rescued:
            logger.warning(
                f"LLM 輸出被截斷 ({drug_name} {label})，細分後仍不足，"
                f"救回 {len(rescued)} 筆"
            )
        else:
            logger.warning(f"LLM 輸出非 JSON 且無法救回 ({drug_name} {label})")
        return rescued

    results = await asyncio.gather(*(
        extract_chunk(c, f"（第 {i + 1}/{len(chunks)} 段）" if len(chunks) > 1 else "")
        for i, c in enumerate(chunks)
    ))
    merged = _dedupe([item for part in results for item in part])

    supplements = sum(
        1 for i in merged if str(i.get("entity_type", "")).lower() in ("supplement", "food")
    )
    logger.info(
        f"萃取成功: {drug_name} → {len(merged)} 筆關係"
        f"（原文 {len(interaction_text)} 字元／{len(chunks)} 段，"
        f"其中補充劑或食物 {supplements} 筆）"
    )
    return merged
