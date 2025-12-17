import os
import sys
import json

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
    print("Testing Keyword Extraction and LLM Structured Extraction...")
    
    samples = [
        ("True Positive (Murder)", SAMPLE_TRUE_POSITIVE, True),
        ("False Positive (Stats)", SAMPLE_FALSE_POSITIVE, False),
        ("False Positive (Accident)", SAMPLE_ACCIDENT, False)
    ]
    
    for label, text, expected in samples:
        print(f"\n--- Testing: {label} ---")
        matches = check_keywords_fast(text)
        print(f"Keywords: {matches}")
        
        if not matches:
            print("No keywords found (Fast Filter).")
            continue
            
        data, status = extract_with_llm(text, matches)
        print(f"LLM Status: {status}")
        try:
            print(f"Extracted Data:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        except:
            print(f"Extracted Data: {data}")
        
        is_valid = data.get("is_valid", False)
        
        if is_valid == expected:
            print("✅ PASS")
        else:
            print(f"❌ FAIL (Expected {expected})")

if __name__ == "__main__":
    test_extraction()
