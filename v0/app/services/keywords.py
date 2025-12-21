# Keywords related to violent deaths and homicides in Portuguese

MURDER_KEYWORDS = [
    # Ações / Verbos (Actions/Verbs)
    "matou", "mataram", "assassinou", "assassinaram", "executou", "executaram",
    "atirou", "atiraram", "baleou", "balearam", "esfaqueou", "esfaquearam",
    "disparou", "dispararam", "apontou arma", "alvejaram", "alvejado",
    "linchou", "lincharam", "estrangulou", "estrangularam", "degolou", "degolaram",
    "carbonizou", "carbonizaram", "desovou", "desovaram",

    # Resultados / Substantivos (Outcomes/Nouns)
    "homicídio", "assassinato", "latrocínio", "feminicídio", "chacina", "massacre",
    "execução", "crime", "morte", "morto", "morta", "mortos", "mortas",
    "óbito", "cadáver", "corpo", "ossada", "vítima fatal", "vítimas fatais",
    "atentado", "baleado", "baleada", "esfaqueado", "esfaqueada",
    "troca de tiros", "tiroteio", "confronto", "emboscada",

    # Métodos / Armas (Methods/Weapons)
    "tiro", "tiros", "bala", "balas", "arma de fogo", "revólver", "pistola", "fuzil",
    "faca", "facada", "facadas", "arma branca", "golpes", "projétil", "projéteis",
    "queima-roupa", "disparo", "disparos",

    # Contexto / Agentes (Context/Agents)
    "polícia militar", "polícia civil", "pm", "bope", "choque", "traficante", "tráfico",
    "milícia", "miliciano", "facção", "comando vermelho", "tcp", "ada",
    "operação policial", "intervenção policial", "bala perdida",
    "encontrado morto", "encontrada morta", "corpo encontrado",
    "local do crime", "cena do crime", "iml", "instituto médico legal",
    "dh", "divisão de homicídios", "delegacia de homicídios"
]

# Keywords that might indicate non-murder violence (for exclusion or careful checking if needed separately)
# Keeping this separate for now, filtering logic will typically look for at least one MURDER_KEYWORD
NON_LETHAL_VIOLENCE = [
    "agrediu", "agressão", "ferido", "ferida", "lesão corporal", "roubo", "furto", "assalto"
]
