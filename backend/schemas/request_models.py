# =============================================================================
# schemas/request_models.py
# =============================================================================
# Define e valida todos os dados de entrada e saída da API usando Pydantic v2.
# A validação ocorre ANTES de qualquer cálculo, protegendo o motor matemático.
# =============================================================================

from pydantic import BaseModel, Field, model_validator
from typing import List


# -----------------------------------------------------------------------------
# REQUEST — dados enviados pelo usuário via POST /calculate_risk
# -----------------------------------------------------------------------------

class RiskRequest(BaseModel):
    """
    Schema de entrada unificado para cálculo de risco individual
    e simulação epidemiológica SEIR.

    Todos os campos possuem limites (ge/le/gt) que o Pydantic valida
    automaticamente antes de qualquer lógica de negócio ser executada.
    """

    # ── Dados individuais ────────────────────────────────────────────────────

    contacts: int = Field(
        ...,
        ge=0,
        le=10_000,
        description="Número de contatos recentes (≥ 0).",
    )

    days_exposed: int = Field(
        ...,
        ge=0,
        le=60,
        description="Dias desde a possível exposição (0 = sem exposição conhecida).",
    )

    temperature: float = Field(
        ...,
        ge=34.0,
        le=43.0,
        description="Temperatura corporal em °C. Fora de [34, 43] indica erro de medição.",
    )

    symptoms: bool = Field(
        ...,
        description="True se o indivíduo apresenta sintomas respiratórios.",
    )

    mask: bool = Field(
        ...,
        description="True se o indivíduo usa máscara consistentemente.",
    )

    vaccinated: bool = Field(
        ...,
        description="True se o indivíduo está vacinado.",
    )

    # ── Dados comunitários para o modelo SEIR ────────────────────────────────

    population: int = Field(
        ...,
        ge=1,
        le=10_000_000_000,
        description="Tamanho total da população (N > 0).",
    )

    infected: int = Field(
        ...,
        ge=0,
        description="Número inicial de indivíduos infectados (I₀ ≥ 0).",
    )

    exposed: int = Field(
        ...,
        ge=0,
        description="Número inicial de indivíduos expostos (E₀ ≥ 0).",
    )

    beta: float = Field(
        ...,
        gt=0.0,
        le=10.0,
        description=(
            "Taxa de transmissão β (beta). Representa o número médio de "
            "contatos infecciosos por dia. Deve ser > 0."
        ),
    )

    gamma: float = Field(
        ...,
        gt=0.0,
        le=1.0,
        description=(
            "Taxa de recuperação γ (gamma). Inverso do período infeccioso médio. "
            "Ex.: γ = 0.1 → período infeccioso de 10 dias."
        ),
    )

    sigma: float = Field(
        ...,
        gt=0.0,
        le=1.0,
        description=(
            "Taxa de incubação σ (sigma). Inverso do período de incubação médio. "
            "Ex.: σ = 0.2 → incubação de 5 dias."
        ),
    )

    # ── Validações cruzadas (cross-field) ────────────────────────────────────

    @model_validator(mode="after")
    def validate_epidemiological_consistency(self) -> "RiskRequest":
        """
        Valida restrições matemáticas que dependem de múltiplos campos.

        Estas regras garantem que o estado inicial do modelo SEIR seja
        epidemiologicamente coerente: infectados + expostos nunca podem
        exceder a população total.
        """
        if self.infected > self.population:
            raise ValueError(
                f"'infected' ({self.infected}) não pode ser maior que "
                f"'population' ({self.population})."
            )

        if self.exposed > self.population:
            raise ValueError(
                f"'exposed' ({self.exposed}) não pode ser maior que "
                f"'population' ({self.population})."
            )

        if self.infected + self.exposed > self.population:
            raise ValueError(
                f"A soma de 'infected' ({self.infected}) + 'exposed' ({self.exposed}) "
                f"= {self.infected + self.exposed} excede 'population' ({self.population}). "
                "Ajuste os valores iniciais."
            )

        return self


# -----------------------------------------------------------------------------
# RESPONSE — dados retornados pela API ao frontend
# -----------------------------------------------------------------------------

class SEIRProjection(BaseModel):
    """
    Arrays com a evolução diária de cada compartimento do modelo SEIR
    ao longo de 30 dias (31 pontos: dias 0 a 30).
    """

    susceptible: List[float] = Field(description="Série temporal de Suscetíveis S(t).")
    exposed: List[float] = Field(description="Série temporal de Expostos E(t).")
    infected: List[float] = Field(description="Série temporal de Infectados I(t).")
    recovered: List[float] = Field(description="Série temporal de Recuperados R(t).")


class RiskResponse(BaseModel):
    """
    Resposta padronizada da API. Contém o risco individual calculado
    e a projeção epidemiológica completa.
    """

    risk_percentage: float = Field(
        description="Probabilidade de infecção individual em % (0–100).",
    )

    risk_level: str = Field(
        description="Classificação textual: 'Baixo Risco', 'Médio Risco' ou 'Alto Risco'.",
    )

    message: str = Field(
        description="Recomendação preventiva personalizada com base no nível de risco.",
    )

    projection: SEIRProjection = Field(
        description="Projeção SEIR para os próximos 30 dias.",
    )


# -----------------------------------------------------------------------------
# RESPONSE de erro padronizado
# -----------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Estrutura de erro retornada em caso de falha na validação ou no cálculo."""

    detail: str = Field(description="Descrição legível do erro ocorrido.")