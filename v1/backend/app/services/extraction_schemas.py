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
        "Brasil",
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
        O texto contém uma data COMPLETA e EXPLÍCITA (dia/mês/ano OU dia/mês com ano claro no contexto)?
        
        TRUE apenas se houver:
        - "15 de dezembro de 2025"
        - "15/12/2025"
        - "em 12 de março" (se o ano 2024 está claramente estabelecido no contexto)
        
        FALSE se houver apenas:
        - "ontem", "hoje", "na semana passada"
        - "sexta-feira (12)", "segunda-feira (15)" (dia da semana com número mas SEM ano explícito)
        - "há três dias", "recentemente"
        - Qualquer termo relativo
        """,
    )

    date_text_quote: Optional[str] = Field(
        None,
        description="""
        Se has_explicit_date é TRUE, copie EXATAMENTE o trecho do texto que contém a data completa.
        
        Deve ser uma citação LITERAL do texto original, palavra por palavra.
        Se has_explicit_date é FALSE, deixe como null.
        """,
    )

    year_explicitly_mentioned: bool = Field(
        ...,
        description="""
        O ANO está explicitamente mencionado no trecho da data?
        
        TRUE: "15 de dezembro de 2025", "12/03/2024"
        FALSE: "sexta-feira (12)", "no dia 15", "em março"
        """,
    )

    verification_reasoning: str = Field(
        ...,
        description="""
        Explique seu raciocínio sobre a data:
        - O que o texto diz exatamente?
        - Por que você marcou has_explicit_date como TRUE ou FALSE?
        - Se FALSE, por que não é possível extrair a data?
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
        
        REGRA ABSOLUTA: Este campo DEVE ser null se date_verification.has_explicit_date é FALSE.
        
        Use data SOMENTE se:
        1. date_verification.has_explicit_date é TRUE
        2. date_verification.year_explicitly_mentioned é TRUE
        3. Há uma data completa no formato dia/mês/ano no texto
        
        NUNCA calcule ou infira datas de termos relativos.
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
            if not self.date_verification.year_explicitly_mentioned:
                raise ValueError(
                    f"ERRO: Campo 'date' está preenchido mas date_verification.year_explicitly_mentioned é FALSE. "
                    f"Não é possível extrair data completa sem ano explícito."
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

