import os
import sys
import json
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.extraction import check_keywords_fast, extract_with_llm

SAMPLE_TRUE_POSITIVE = """
Na noite de ontem, um homem foi morto a tiros na Zona Norte do Rio de Janeiro. 
A vítima, identificada como João da Silva, foi alvejada por disparos de arma de fogo.
A polícia militar isolou a área e a Delegacia de Homicídios investiga o caso.
"""

SAMPLE_FALSE_POSITIVE = """
O índice de violência no Rio de Janeiro caiu 10% este ano. 
O governo anunciou novas medidas de segurança. Não houve mortes neste final de semana.
A polícia militar realizou operações de conscientização.
"""

SAMPLE_ACCIDENT = """
Um grave acidente de trânsito deixou um morto na Avenida Brasil. 
O motorista perdeu o controle e colidiu com um poste. A vítima morreu no local.
"""

def test_extraction():
    logger.info("Testing Keyword Extraction and LLM Structured Extraction...")
    
    samples = [
        ("True Positive (Murder)", SAMPLE_TRUE_POSITIVE, True),
        ("False Positive (Stats)", SAMPLE_FALSE_POSITIVE, False),
        ("False Positive (Accident)", SAMPLE_ACCIDENT, False)
    ]
    
    for label, text, expected in samples:
        logger.info(f"\n--- Testing: {label} ---")
        matches = check_keywords_fast(text)
        logger.info(f"Keywords: {matches}")
        
        if not matches:
            logger.info("No keywords found (Fast Filter).")
            continue
            
        data, status = extract_with_llm(text, matches)
        logger.info(f"LLM Status: {status}")
        try:
            logger.info(f"Extracted Data:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        except:
            logger.info(f"Extracted Data: {data}")
        
        is_valid = data.get("is_valid", False)
        
        if is_valid == expected:
            logger.info("✅ PASS")
        else:
            logger.warning(f"❌ FAIL (Expected {expected})")

if __name__ == "__main__":
    test_extraction()
