"""Pydantic schemas for structured event extraction from news articles."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---- Type definitions for standardization ----

HomicideType = Literal[
    "Homicídio",
    "Homicídio Qualificado",
    "Homicídio Culposo",
    "Tentativa de Homicídio",
    "Latrocínio",
    "Feminicídio",
    "Infanticídio",
    "Outro",
]

MethodOfDeath = Literal[
    "Arma de fogo",
    "Arma branca",
    "Estrangulamento",
    "Asfixia",
    "Espancamento",
    "Atropelamento",
    "Envenenamento",
    "Objeto contundente",
    "Incêndio",
    "Queda",
    "Outro",
    "Não especificado",
]


# ---- Classes for Structured Extraction ----


class Location(BaseModel):
    """Estrutura de dados de localização extraída da notícia."""

    neighborhood: Optional[str] = Field(
        None,
        description="Nome do bairro onde ocorreu a morte violenta. Use apenas se explicitamente mencionado.",
    )
    street: Optional[str] = Field(
        None,
        description="Nome da rua, avenida ou logradouro. Exemplo: 'Rua das Flores', 'Avenida Paulista'",
    )
    establishment: Optional[str] = Field(
        None,
        description="Nome do estabelecimento ou tipo de local. Exemplo: 'Residência', 'Via pública', 'Bar e Restaurante', 'Terreno baldio'",
    )
    city: Optional[str] = Field(None, description="Cidade onde ocorreu a morte violenta")
    state: Optional[str] = Field(
        None,
        description="Estado em sigla para Brasil (RJ, SP, MG, etc.) ou nome completo para outros países",
    )
    country: Optional[str] = Field(
        None,
        description="País onde ocorreu a morte violenta. Use as informações do texto para inferir o país.",
    )
    full_location_description: Optional[str] = Field(
        None, description="Descrição completa e precisa do local."
    )


class IdentifiablePerpetrator(BaseModel):
    """Dados estruturados do autor/suspeito de morte violenta identificável."""

    name: Optional[str] = Field(None, description="Nome completo do autor, se identificado.")
    age: Optional[int] = Field(None, description="Idade do autor.")
    gender: Optional[Literal["masculino", "feminino", "outro", "não informado"]] = Field(
        None, description="Gênero do autor."
    )
    occupation: Optional[str] = Field(
        None, description="Profissão ou ocupação do autor, se mencionada."
    )
    relationship_to_victim: Optional[str] = Field(
        None,
        description="Relação do autor com a vítima, se mencionada. Exemplo: 'cônjuge', 'desconhecido', 'colega', 'familiar'",
    )
    is_security_force: Optional[bool] = Field(
        None,
        description="Indica se o autor é integrante das forças de segurança pública (Ex: policial militar, policial civil, etc.). True se for, False se não for, None se não mencionado.",
    )
    description: Optional[str] = Field(
        None, description="Descrição física ou características do autor mencionadas"
    )


class UnidentifiedPerpetratorGroup(BaseModel):
    """Grupo de autores/suspeitos não identificados individualmente."""

    count: int = Field(..., description="Número de autores neste grupo")
    description: str = Field(
        ...,
        description='Descrição do grupo conforme texto. Ex: "criminosos", "suspeitos", "policiais", "traficantes", "homens armados"',
    )
    is_security_force: Optional[bool] = Field(
        None, description="Este grupo é de forças de segurança?"
    )
    is_civilian: Optional[bool] = Field(None, description="Este grupo é de civis?")
    context: Optional[str] = Field(
        None,
        description="Contexto adicional sobre este grupo (ex: 'fugiram do local', 'presos durante operação X')",
    )


class Perpetrators(BaseModel):
    """Dados sobre os autores/suspeitos de morte violenta."""

    identifiable_perpetrators: list[IdentifiablePerpetrator] = Field(
        ...,
        description="Lista de autores/suspeitos de morte violenta. Crie uma entrada para cada autor mencionado somente quando houver informações suficientes para identificar o autor.",
    )
    number_of_identifiable_perpetrators: int = Field(
        ..., description="Número de autores/suspeitos identificados"
    )
    unidentified_groups: Optional[list[UnidentifiedPerpetratorGroup]] = Field(
        None, description="Lista de autores/suspeitos não identificados"
    )
    number_of_unidentified_perpetrators: Optional[int] = Field(
        None, description="Número de autores/suspeitos não identificados"
    )
    number_of_perpetrators: int = Field(
        ...,
        description="Número total de autores/suspeitos de morte violenta mencionados na notícia",
    )


class IdentifiableVictim(BaseModel):
    """Dados estruturados da vítima de morte violenta."""

    name: Optional[str] = Field(
        None,
        description="Nome completo da vítima. Se apenas primeiro nome ou apelido, registrar o que foi informado.",
    )
    age: Optional[int] = Field(None, description="Idade da vítima em anos")
    gender: Optional[Literal["masculino", "feminino", "outro", "não informado"]] = Field(
        None, description="Gênero da vítima inferido do texto"
    )
    occupation: Optional[str] = Field(
        None, description="Profissão ou ocupação da vítima, se mencionada"
    )
    relationship_to_perpetrator: Optional[str] = Field(
        None,
        description="Relação com o autor do crime, se mencionada. Exemplo: 'cônjuge', 'desconhecido', 'colega', 'familiar'",
    )
    is_security_force: Optional[bool] = Field(
        None,
        description="Indica se a vítima é integrante das forças de segurança pública (Ex: policial militar, policial civil, guarda municipal, etc.). True se for, False se não for, None se não mencionado.",
    )
    description: Optional[str] = Field(
        None, description="Descrição física ou características mencionadas"
    )


class UnidentifiedVictimGroup(BaseModel):
    """Grupo de vítimas não identificadas individualmente."""

    count: int = Field(..., description="Número de vítimas neste grupo")
    description: str = Field(
        ...,
        description='Descrição do grupo conforme texto. Ex: "moradores", "suspeitos", "policiais", "pessoas", "civis", "criminosos"',
    )
    is_security_force: Optional[bool] = Field(
        None, description="Este grupo é de forças de segurança?"
    )
    is_civilian: Optional[bool] = Field(None, description="Este grupo é de civis?")
    context: Optional[str] = Field(
        None,
        description="Contexto adicional sobre este grupo (ex: 'mortos durante operação X')",
    )


class Victims(BaseModel):
    """Dados sobre as vítimas de morte violenta."""

    identifiable_victims: list[IdentifiableVictim] = Field(
        ...,
        description="Lista de vítimas de morte violenta. Crie uma entrada para cada vítima mencionada somente quando houver informações suficientes para identificar a vítima.",
    )
    number_of_identifiable_victims: int = Field(
        ..., description="Número de vítimas identificadas"
    )
    unidentified_groups: Optional[list[UnidentifiedVictimGroup]] = Field(
        None, description="Lista de vítimas não identificadas"
    )
    number_of_unidentified_victims: Optional[int] = Field(
        None, description="Número de vítimas não identificadas"
    )
    number_of_victims: int = Field(
        ..., description="Número total de vítimas de morte violenta mencionadas na notícia"
    )


class DateVerification(BaseModel):
    """Verificação rigorosa da data antes de extrair."""

    has_explicit_date: bool = Field(
        ...,
        description="""
        Você consegue determinar a data COMPLETA (dia/mês/ano) do evento?
        
        TRUE se:
        - Data completa explícita no texto: "15 de dezembro de 2025", "15/12/2025"
        - Data relativa que pode ser resolvida usando a DATA DE PUBLICAÇÃO fornecida nos metadados:
          * "ontem" + publicação em 21/12/2025 → 20/12/2025
          * "na sexta-feira" + publicação conhecida → calcular a sexta-feira mais recente
          * "há três dias" + publicação em 21/12/2025 → 18/12/2025
        
        FALSE se:
        - Termos vagos sem referência: "recentemente", "há alguns dias"
        - Nenhuma data de publicação disponível E apenas termos relativos no texto
        - Ambiguidade impossível de resolver
        """,
    )

    date_source: Literal["explicit", "inferred_from_publication", "none"] = Field(
        ...,
        description="""
        Como a data foi determinada:
        - "explicit": Data completa (dia/mês/ano) está literalmente no texto da notícia
        - "inferred_from_publication": Data calculada a partir de termo relativo ("ontem", "sexta-feira") 
          usando a data de publicação da notícia como referência
        - "none": Não foi possível determinar a data
        """,
    )

    date_text_quote: Optional[str] = Field(
        None,
        description="""
        Copie EXATAMENTE o trecho do texto que menciona a data ou termo temporal.
        
        Exemplos:
        - "15 de dezembro de 2025" (explícita)
        - "ontem à noite" (relativa, requer data de publicação)
        - "na sexta-feira passada" (relativa, requer data de publicação)
        
        Deixe null apenas se não houver menção temporal alguma.
        """,
    )

    year_explicitly_mentioned: bool = Field(
        ...,
        description="""
        O ANO está explicitamente mencionado no texto?
        
        TRUE: "15 de dezembro de 2025", "12/03/2024"
        FALSE: "ontem", "sexta-feira (12)", "no dia 15", "em março"
        
        Nota: Mesmo com FALSE, se has_explicit_date é TRUE (via inferência), a data pode ser válida.
        """,
    )

    verification_reasoning: str = Field(
        ...,
        description="""
        Explique detalhadamente seu raciocínio sobre a data:
        - O que o texto diz exatamente sobre quando ocorreu o evento?
        - Se usou data de publicação para inferir: qual era a data de publicação e como calculou?
        - Por que marcou has_explicit_date como TRUE ou FALSE?
        - Se FALSE, por que não foi possível determinar a data?
        """,
    )


class DateTime(BaseModel):
    """Dados estruturados de data e hora."""

    date_verification: DateVerification = Field(
        ..., description="Verificação rigorosa se há data explícita no texto"
    )

    date: Optional[str] = Field(
        None,
        description="""
        Data da morte violenta no formato AAAA-MM-DD.
        
        REGRA: Este campo DEVE ser null se date_verification.has_explicit_date é FALSE.
        
        Use data quando:
        1. date_verification.has_explicit_date é TRUE, E
        2. date_source é "explicit" (data completa no texto), OU
        3. date_source é "inferred_from_publication" (calculada a partir de "ontem", "sexta-feira", etc. 
           usando a data de publicação fornecida nos metadados)
        
        NUNCA invente datas sem base textual ou sem data de publicação para calcular.
        """,
    )

    date_precision: Optional[Literal["exata", "parcial", "não informada"]] = Field(
        None,
        description="""
        - "exata": data completa (dia/mês/ano) explícita no texto
        - "parcial": apenas dia da semana ou mês mencionado, sem ano
        - "não informada": sem data ou apenas termos relativos
        """,
    )

    time: Optional[str] = Field(
        None,
        description="""
        Horário específico se explicitamente mencionado no texto.
        
        FORMATOS ACEITOS:
        - Horário exato: "20h30", "15:45", "às 23h"
        - Aproximação explícita: "por volta das 20h", "cerca de 15h"
        
        NÃO USE se apenas período do dia for mencionado ("à noite", "de manhã").
        """,
    )

    time_of_day: Optional[Literal["madrugada", "manhã", "tarde", "noite", "não informado"]] = (
        Field(
            None,
            description="""
        Período do dia quando ocorreu a morte violenta, baseado no texto.
        
        Use APENAS se explicitamente mencionado ou se houver horário específico.
        """,
        )
    )

    @model_validator(mode="after")
    def validate_date_consistency(self):
        """Valida que a data só existe se a verificação permitir."""
        if self.date is not None:
            if not self.date_verification.has_explicit_date:
                raise ValueError(
                    f"ERRO: Campo 'date' está preenchido mas date_verification.has_explicit_date é FALSE. "
                    f"Raciocínio: {self.date_verification.verification_reasoning}"
                )
            # Allow dates inferred from publication date (year not explicitly mentioned in article)
            if self.date_verification.date_source == "none":
                raise ValueError(
                    f"ERRO: Campo 'date' está preenchido mas date_source é 'none'. "
                    f"Raciocínio: {self.date_verification.verification_reasoning}"
                )
        return self


class HomicideDynamic(BaseModel):
    """Dinâmica da morte violenta estruturada."""

    title: str = Field(
        ...,
        description="""
        Título técnico da ocorrência seguindo o formato:
        [TIPO DE HOMICÍDIO] - [LOCAL] - [DATA OU "DATA NÃO INFORMADA"]
        
        IMPORTANTE: Se não houver data completa verificada, use "DATA NÃO INFORMADA" no lugar da data.
        
        Exemplos:
        - "HOMICÍDIO QUALIFICADO - VIA PÚBLICA BAIRRO CENTRO - 15/12/2025"
        - "FEMINICÍDIO - RESIDÊNCIA SANTA CRUZ - DATA NÃO INFORMADA"
        - "LATROCÍNIO - ESTABELECIMENTO COMERCIAL - 10/01/2025"
        """,
    )

    homicide_type: HomicideType = Field(
        ...,
        description="""
        Classificação do tipo de homicídio segundo terminologia jurídica brasileira.
        Valores permitidos:
        - "Homicídio"
        - "Homicídio Qualificado"
        - "Homicídio Culposo"
        - "Tentativa de Homicídio"
        - "Latrocínio"
        - "Feminicídio"
        - "Infanticídio"
        - "Outro"
        """,
    )

    method: Optional[MethodOfDeath] = Field(
        None,
        description="""
        Método utilizado para causar a morte violenta.
        Valores permitidos:
        - "Arma de fogo"
        - "Arma branca"
        - "Estrangulamento"
        - "Asfixia"
        - "Espancamento"
        - "Atropelamento"
        - "Envenenamento"
        - "Objeto contundente"
        - "Incêndio"
        - "Queda"
        - "Outro"
        - "Não especificado"
        """,
    )

    chronological_description: str = Field(
        ...,
        description="""
        Descrição cronológica OBJETIVA dos fatos em linguagem técnica policial.
        
        DEVE:
        - Usar terceira pessoa e voz passiva
        - Linguagem formal, técnica e impessoal
        - Ordem cronológica clara dos eventos
        - Apenas fatos verificáveis no texto
        - Terminologia jurídica adequada
        - Identificar claramente: vítima(s), autor(es), testemunha(s)
        - Se data completa não disponível, use "em data não especificada" ou "em [dia da semana/período mencionado]"
        
        NÃO DEVE:
        - Incluir opiniões ou juízos de valor
        - Usar adjetivos sensacionalistas ("brutal", "covarde", etc.)
        - Especular sobre motivações não declaradas
        - Usar linguagem coloquial ou emotiva
        - Incluir informações não verificadas no texto
        - Inventar datas completas
        """,
    )


class ViolentDeathEvent(BaseModel):
    """Informações estruturadas completas sobre morte violenta extraída de notícia."""

    location_info: Location = Field(
        ..., description="Informações estruturadas do local onde ocorreu a morte violenta"
    )

    date_time: DateTime = Field(
        ..., description="Informações de data e hora da morte violenta COM VERIFICAÇÃO RIGOROSA"
    )

    victims: Victims = Field(..., description="Dados sobre as vítimas de morte violenta.")

    perpetrators: Optional[Perpetrators] = Field(
        None, description="Lista de autores/suspeitos da morte violenta, se identificados"
    )

    homicide_dynamic: HomicideDynamic = Field(
        ...,
        description="Dinâmica completa da morte violenta incluindo título, classificação e descrição técnica",
    )

    additional_context: Optional[str] = Field(
        None, description="Contexto adicional relevante que não se enquadra nas categorias acima"
    )

