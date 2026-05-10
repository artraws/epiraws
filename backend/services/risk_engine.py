# =============================================================================
# services/risk_engine.py
# =============================================================================
# Motor heurístico de risco individual do EpiRaws.
#
# MODELO MATEMÁTICO
# -----------------
# O risco é calculado por uma soma ponderada linear de fatores clínicos,
# comportamentais e epidemiológicos. O escore bruto é então normalizado
# para o intervalo [0, 100] via min-max scaling implícito (divisão pelo
# máximo teórico possível).
#
# Fórmula:
#   raw_score = Σ (weight_i × factor_i)
#
#   risk_pct  = clamp( (raw_score / MAX_THEORETICAL_SCORE) × 100, 0, 100 )
#
# Onde clamp(x, 0, 100) = max(0, min(100, x))
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass


# =============================================================================
# PESOS DOS FATORES (calibrados epidemiologicamente)
# =============================================================================
# Cada peso reflete a magnitude do impacto do fator correspondente no risco
# real de infecção, baseado em literatura epidemiológica simplificada.
# Todos os pesos são positivos; fatores de proteção são expressos como
# multiplicadores negativos no cálculo do fator.

WEIGHTS = {
    # Contatos: cada contato próximo aumenta linearmente a chance de exposição.
    # Capped internamente para evitar overflow com valores extremos.
    "contact":     2.5,

    # Febre: temperatura acima de 37.5 °C sinaliza resposta imune ativa —
    # pode indicar infecção em curso. Impacto alto.
    "temperature": 18.0,

    # Sintomas: presença de sintomas respiratórios é o indicador clínico
    # mais forte de infecção ativa.
    "symptom":     25.0,

    # Máscara: uso consistente reduz a transmissão em ~70-80% (estudos de
    # eficácia). Representado como penalidade quando mask == False.
    "mask":        12.0,

    # Vacinação: imunidade vacinal reduz significativamente tanto a
    # probabilidade de infecção quanto a gravidade.
    "vaccination": 20.0,

    # Exposição: dias recentes de exposição aumentam a janela de risco.
    "exposure":    3.0,

    # Infectados próximos: contato com casos confirmados é fator de risco direto.
    "infected":    1.5,
}

# Escore máximo teórico possível (usado na normalização).
# Calculado para:
#   contacts=20, temperatura alta, sintomas, sem máscara,
#   sem vacina, 14 dias exposição, 50 infectados próximos.
_MAX_THEORETICAL_SCORE: float = (
    WEIGHTS["contact"]     * 20    # 20 contatos (capped)
    + WEIGHTS["temperature"] * 1.0  # fator máximo de febre = 1.0
    + WEIGHTS["symptom"]   * 1.0    # sintomas presentes
    + WEIGHTS["mask"]      * 1.0    # sem máscara
    + WEIGHTS["vaccination"]* 0.0   # sem vacinação (penalidade = 0 aqui; ver abaixo)
    + WEIGHTS["exposure"]  * 14.0   # 14 dias de exposição (capped)
    + WEIGHTS["infected"]  * 50.0   # 50 infectados próximos (capped)
)
# Ajustamos para refletir que a ausência de vacinação NÃO reduz o escore,
# mas a PRESENÇA reduz. Portanto o máximo não inclui redução vacinal.
# O valor abaixo é usado apenas como denominador de normalização; se o
# escore bruto ultrapassar (por alguma combinação extrema), clamp garante 100%.


# =============================================================================
# DATACLASS DE RESULTADO
# =============================================================================

@dataclass(frozen=True)
class RiskResult:
    """Resultado completo do motor heurístico."""
    risk_percentage: float   # [0, 100]
    risk_level: str          # "Baixo Risco" | "Médio Risco" | "Alto Risco"
    message: str             # Recomendação personalizada


# =============================================================================
# FUNÇÕES AUXILIARES (FATORES INDIVIDUAIS)
# =============================================================================

def _contact_factor(contacts: int) -> float:
    """
    Fator de contatos: cresce de forma sub-linear (raiz quadrada) para
    refletir que o risco marginal de cada contato adicional diminui após
    um número razoável (lei dos grandes números de exposição).

    Cap em 20 contatos para evitar overflow no escore.
    """
    capped = min(contacts, 20)
    return math.sqrt(capped)  # ∈ [0, √20 ≈ 4.47]


def _temperature_factor(temperature: float) -> float:
    """
    Fator de temperatura baseado em limiar clínico:

    - < 37.5 °C  → sem febre         → fator 0.0
    - 37.5–38.4  → febre baixa       → fator 0.4
    - 38.5–39.4  → febre moderada    → fator 0.7
    - ≥ 39.5     → febre alta        → fator 1.0
    """
    if temperature < 37.5:
        return 0.0
    elif temperature < 38.5:
        return 0.4
    elif temperature < 39.5:
        return 0.7
    else:
        return 1.0


def _symptom_factor(symptoms: bool) -> float:
    """Binário: sintomas presentes = 1.0, ausentes = 0.0."""
    return 1.0 if symptoms else 0.0


def _mask_penalty(mask: bool) -> float:
    """
    Ausência de máscara gera penalidade máxima (1.0).
    Uso de máscara elimina a penalidade (0.0).
    """
    return 0.0 if mask else 1.0


def _vaccination_reduction(vaccinated: bool, base_score: float) -> float:
    """
    A vacinação reduz o escore bruto acumulado em 35%.
    Retorna o valor a ser SUBTRAÍDO do escore.
    Nunca retorna valor negativo.
    """
    if vaccinated:
        return base_score * 0.35
    return 0.0


def _exposure_factor(days_exposed: int) -> float:
    """
    Dias de exposição contribuem linearmente, com cap em 14 dias
    (equivalente ao período máximo de incubação da maioria dos vírus
    respiratórios estudados).
    """
    return float(min(days_exposed, 14))


def _infected_nearby_factor(nearby_infected: int) -> float:
    """
    Número de infectados próximos, capped em 50 para normalização.
    Crescimento linear: cada caso confirmado próximo aumenta o risco.
    """
    return float(min(nearby_infected, 50))


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def calculate_individual_risk(
    contacts: int,
    days_exposed: int,
    temperature: float,
    symptoms: bool,
    mask: bool,
    vaccinated: bool,
    nearby_infected: int = 0,
) -> RiskResult:
    """
    Calcula o risco individual de infecção.

    Parâmetros
    ----------
    contacts         : Número de contatos recentes
    days_exposed     : Dias desde a possível exposição
    temperature      : Temperatura corporal em °C
    symptoms         : Presença de sintomas (True/False)
    mask             : Uso de máscara (True/False)
    vaccinated       : Vacinação (True/False)
    nearby_infected  : Número de infectados conhecidos nas proximidades

    Retorna
    -------
    RiskResult com porcentagem, nível e mensagem preventiva.
    """

    # ── Passo 1: calcular fatores individuais ────────────────────────────────

    f_contact     = _contact_factor(contacts)
    f_temperature = _temperature_factor(temperature)
    f_symptom     = _symptom_factor(symptoms)
    f_mask        = _mask_penalty(mask)
    f_exposure    = _exposure_factor(days_exposed)
    f_infected    = _infected_nearby_factor(nearby_infected)

    # ── Passo 2: soma ponderada (escore bruto sem vacinação) ─────────────────
    #
    # raw_score = Σ weight_i × factor_i
    #
    raw_score = (
        WEIGHTS["contact"]     * f_contact
        + WEIGHTS["temperature"] * f_temperature
        + WEIGHTS["symptom"]   * f_symptom
        + WEIGHTS["mask"]      * f_mask
        + WEIGHTS["exposure"]  * f_exposure
        + WEIGHTS["infected"]  * f_infected
    )

    # ── Passo 3: redução por vacinação ───────────────────────────────────────
    #
    # A vacinação é aplicada APÓS a soma bruta para garantir que ela
    # sempre reduza proporcionalmente ao risco acumulado.
    #
    reduction = _vaccination_reduction(vaccinated, raw_score)
    adjusted_score = raw_score - reduction

    # ── Passo 4: normalização → [0, 100] ────────────────────────────────────
    #
    # Divide pelo escore máximo teórico e escala para porcentagem.
    # clamp impede valores negativos ou acima de 100.
    #
    if _MAX_THEORETICAL_SCORE > 0:
        risk_pct = (adjusted_score / _MAX_THEORETICAL_SCORE) * 100.0
    else:
        risk_pct = 0.0

    risk_pct = max(0.0, min(100.0, risk_pct))

    # ── Passo 5: classificação e mensagem ───────────────────────────────────

    risk_level, message = _classify(risk_pct, symptoms, vaccinated, temperature)

    return RiskResult(
        risk_percentage=round(risk_pct, 2),
        risk_level=risk_level,
        message=message,
    )


# =============================================================================
# CLASSIFICAÇÃO E MENSAGENS PREVENTIVAS
# =============================================================================

def _classify(
    risk_pct: float,
    symptoms: bool,
    vaccinated: bool,
    temperature: float,
) -> tuple[str, str]:
    """
    Classifica o risco e retorna mensagem preventiva personalizada.

    Limites:
        0–33%  → Baixo Risco
        34–66% → Médio Risco
        67–100%→ Alto Risco
    """

    if risk_pct <= 33.0:
        level = "Baixo Risco"
        if vaccinated:
            msg = (
                "Seu risco está baixo — ótimo! A vacinação está contribuindo "
                "para sua proteção. Continue usando máscara em locais fechados "
                "e mantenha a higiene das mãos regularmente."
            )
        else:
            msg = (
                "Seu risco está baixo no momento. Considere se vacinar para "
                "reforçar sua proteção. Evite aglomerações e mantenha distância "
                "social sempre que possível."
            )

    elif risk_pct <= 66.0:
        level = "Médio Risco"
        if symptoms:
            msg = (
                "Você apresenta sintomas e risco moderado de infecção. "
                "Recomendamos isolamento imediato, uso rigoroso de máscara "
                "e consulta médica para avaliação e possível testagem."
            )
        elif temperature >= 37.5:
            msg = (
                "Sua temperatura indica possível febre, elevando seu risco. "
                "Monitore sua temperatura a cada 4 horas, evite contato com "
                "pessoas vulneráveis e procure um médico se os sintomas evoluírem."
            )
        else:
            msg = (
                "Seu risco é moderado. Reduza seus contatos sociais, use máscara "
                "em ambientes fechados e acompanhe seu estado de saúde nos "
                "próximos 7–14 dias."
            )

    else:
        level = "Alto Risco"
        if symptoms and temperature >= 37.5:
            msg = (
                "ATENÇÃO: Você apresenta febre e sintomas com alto risco de infecção. "
                "Procure atendimento médico IMEDIATAMENTE. Isole-se de outros moradores, "
                "use máscara N95, e notifique seus contatos recentes."
            )
        elif symptoms:
            msg = (
                "ATENÇÃO: Alto risco detectado com presença de sintomas. "
                "Isole-se imediatamente, evite qualquer contato social e procure "
                "avaliação médica para testagem e orientação clínica."
            )
        else:
            msg = (
                "Alto risco de infecção identificado. Reduza drasticamente seus "
                "contatos, utilize máscara de alta filtragem (N95/PFF2), "
                "monitore sintomas diariamente e consulte um médico "
                "se qualquer sintoma aparecer."
            )

    return level, msg