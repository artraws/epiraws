# =============================================================================
# services/seir_model.py
# =============================================================================
# Implementação do modelo epidemiológico SEIR resolvido numericamente
# pelo Método de Euler.
#
# MODELO SEIR — TEORIA
# --------------------
# O modelo SEIR divide a população N em quatro compartimentos mutuamente
# exclusivos e coletivamente exaustivos:
#
#   S(t) — Suscetíveis:  indivíduos que podem ser infectados.
#   E(t) — Expostos:     indivíduos que foram expostos mas ainda não
#                        são infecciosos (período de incubação).
#   I(t) — Infectados:   indivíduos infecciosos capazes de transmitir.
#   R(t) — Recuperados:  indivíduos que se recuperaram ou morreram
#                        (removidos da cadeia de transmissão).
#
# Invariante conservado: S(t) + E(t) + I(t) + R(t) = N  ∀ t
#
# SISTEMA DE EDOs
# ---------------
#   dS/dt = -β · S · I / N
#   dE/dt =  β · S · I / N  - σ · E
#   dI/dt =  σ · E           - γ · I
#   dR/dt =  γ · I
#
# Parâmetros:
#   β (beta)  — Taxa de transmissão: número médio de contatos infecciosos
#               por indivíduo infectado por dia.
#   γ (gamma) — Taxa de recuperação: fração dos infectados que se recuperam
#               por dia. Período infeccioso médio = 1/γ dias.
#   σ (sigma) — Taxa de incubação: fração dos expostos que se tornam
#               infecciosos por dia. Período de incubação médio = 1/σ dias.
#
# NÚMERO DE REPRODUÇÃO BÁSICO
#   R₀ = β / γ
#   R₀ > 1 → epidemia cresce; R₀ < 1 → epidemia declina.
#
# MÉTODO NUMÉRICO: EULER EXPLÍCITO
# ----------------------------------
# Aproximação de primeira ordem para EDOs:
#   X(t + Δt) = X(t) + Δt · f(X(t))
#
# Com Δt = 1 (passo diário), temos:
#   S(t+1) = S(t) + dS/dt
#   E(t+1) = E(t) + dE/dt
#   I(t+1) = I(t) + dI/dt
#   R(t+1) = R(t) + dR/dt
#
# Limitações: Euler explícito pode acumular erro para passos grandes.
# Para Δt = 1 dia e parâmetros epidemiológicos típicos (β < 1, γ < 1),
# a precisão é satisfatória para projeções de curto prazo (30 dias).
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


# =============================================================================
# CONSTANTES
# =============================================================================

SIMULATION_DAYS: int = 30   # Horizonte de simulação
DT: float = 1.0             # Passo de tempo (Δt = 1 dia)

# Proteção contra overflow numérico: se qualquer compartimento ultrapassar
# este valor, algo está matematicamente errado (população > 10 bilhões).
_MAX_POPULATION: float = 1e10

# Limiar mínimo para evitar log(0) ou divisão por zero em análises futuras.
_EPSILON: float = 1e-9


# =============================================================================
# DATACLASS DE RESULTADO
# =============================================================================

@dataclass
class SEIRResult:
    """
    Resultado completo da simulação SEIR.

    Cada lista contém SIMULATION_DAYS + 1 elementos (dias 0 a 30),
    representando o estado de cada compartimento em cada instante.
    """

    susceptible: List[float] = field(default_factory=list)
    exposed: List[float]     = field(default_factory=list)
    infected: List[float]    = field(default_factory=list)
    recovered: List[float]   = field(default_factory=list)

    # Metadados calculados
    peak_infected: float = 0.0        # Pico de infectados
    peak_day: int = 0                 # Dia do pico
    total_infected: float = 0.0       # Total que passou por I (≈ R[30])
    r0: float = 0.0                   # Número de reprodução básico


# =============================================================================
# FUNÇÕES AUXILIARES DE SEGURANÇA NUMÉRICA
# =============================================================================

def _safe_clamp(value: float, min_val: float = 0.0, max_val: float = _MAX_POPULATION) -> float:
    """Garante que um valor permaneça dentro dos limites numéricos válidos."""
    if math.isnan(value) or math.isinf(value):
        return min_val
    return max(min_val, min(max_val, value))


def _normalize_compartments(S: float, E: float, I: float, R: float, N: float) -> tuple[float, float, float, float]:
    """
    Após cada passo de Euler, re-normaliza os compartimentos para garantir
    S + E + I + R = N (conservação da população).

    Esta correção é necessária porque erros de arredondamento flutuante
    podem violar o invariante de conservação ao longo de 30 iterações.
    """
    total = S + E + I + R
    if total <= 0:
        return N, 0.0, 0.0, 0.0

    # Escala proporcional para manter a soma exata
    factor = N / total
    return S * factor, E * factor, I * factor, R * factor


# =============================================================================
# DERIVADAS DO SISTEMA DE EDOs SEIR
# =============================================================================

def _compute_derivatives(
    S: float, E: float, I: float, R: float,
    N: float, beta: float, gamma: float, sigma: float,
) -> tuple[float, float, float, float]:
    """
    Calcula as quatro derivadas do sistema SEIR para um instante t.

    Retorna (dS, dE, dI, dR) — as taxas de variação instantânea
    de cada compartimento.

    Proteção contra divisão por zero: se N ≤ 0 (impossível após validação,
    mas defensivamente verificado), retorna zeros.
    """
    if N <= _EPSILON:
        return 0.0, 0.0, 0.0, 0.0

    # Força de infecção: λ = β · I / N
    # Representa a taxa per capita de novos expostos gerados pelos infectados.
    lambda_ = beta * I / N

    # dS/dt = -λ · S  (saída de Suscetíveis → Expostos)
    dS = -lambda_ * S

    # dE/dt = λ · S - σ · E  (entrada de Expostos - saída para Infectados)
    dE = lambda_ * S - sigma * E

    # dI/dt = σ · E - γ · I  (entrada de Infectados - saída para Recuperados)
    dI = sigma * E - gamma * I

    # dR/dt = γ · I  (acúmulo de Recuperados)
    dR = gamma * I

    return dS, dE, dI, dR


# =============================================================================
# SIMULADOR PRINCIPAL
# =============================================================================

def run_seir_simulation(
    population: int,
    infected: int,
    exposed: int,
    beta: float,
    gamma: float,
    sigma: float,
    days: int = SIMULATION_DAYS,
) -> SEIRResult:
    """
    Executa a simulação SEIR pelo Método de Euler para `days` dias.

    Parâmetros
    ----------
    population : Tamanho total da população (N)
    infected   : Infectados iniciais (I₀)
    exposed    : Expostos iniciais (E₀)
    beta       : Taxa de transmissão (β)
    gamma      : Taxa de recuperação (γ)
    sigma      : Taxa de incubação (σ)
    days       : Número de dias a simular (padrão: 30)

    Retorna
    -------
    SEIRResult com as séries temporais e metadados.

    Raises
    ------
    ValueError se os parâmetros violarem invariantes matemáticos.
    """

    # ── Validação de parâmetros ───────────────────────────────────────────────
    N = float(population)

    if N <= 0:
        raise ValueError("A população (N) deve ser maior que zero.")
    if beta <= 0 or gamma <= 0 or sigma <= 0:
        raise ValueError("β, γ e σ devem ser estritamente positivos.")
    if infected < 0 or exposed < 0:
        raise ValueError("Infectados e Expostos iniciais não podem ser negativos.")
    if infected + exposed > population:
        raise ValueError(
            "A soma de Infectados + Expostos não pode exceder a população total."
        )

    # ── Condições iniciais ───────────────────────────────────────────────────
    #
    # I₀ = infectados iniciais
    # E₀ = expostos iniciais
    # R₀ = 0 (nenhum recuperado no início da simulação)
    # S₀ = N - E₀ - I₀  (suscetíveis = todos os demais)
    #
    I0 = float(infected)
    E0 = float(exposed)
    R0_compartment = 0.0
    S0 = N - E0 - I0

    # Garantia: S₀ não pode ser negativo (validado no schema, mas defensivo aqui)
    S0 = max(0.0, S0)

    # ── Inicialização das séries temporais ───────────────────────────────────

    result = SEIRResult()

    # Estado corrente (atualizado a cada passo)
    S, E, I, R = S0, E0, I0, R0_compartment

    # Registrar condições iniciais (dia 0)
    result.susceptible.append(round(S, 4))
    result.exposed.append(round(E, 4))
    result.infected.append(round(I, 4))
    result.recovered.append(round(R, 4))

    # ── Loop de integração: Método de Euler ──────────────────────────────────
    #
    # Para cada dia t de 1 a `days`:
    #   1. Calcular as derivadas no instante atual.
    #   2. Avançar cada compartimento: X(t+1) = X(t) + Δt · dX/dt
    #   3. Aplicar clamp para impedir valores negativos.
    #   4. Re-normalizar para conservar N.
    #   5. Registrar o estado.
    #
    for _day in range(1, days + 1):

        # Passo 1: derivadas no tempo corrente
        dS, dE, dI, dR = _compute_derivatives(S, E, I, R, N, beta, gamma, sigma)

        # Passo 2: avanço de Euler (Δt = 1 dia)
        S_new = S + DT * dS
        E_new = E + DT * dE
        I_new = I + DT * dI
        R_new = R + DT * dR

        # Passo 3: clamp — nenhum compartimento pode ser negativo
        S_new = _safe_clamp(S_new, 0.0, N)
        E_new = _safe_clamp(E_new, 0.0, N)
        I_new = _safe_clamp(I_new, 0.0, N)
        R_new = _safe_clamp(R_new, 0.0, N)

        # Passo 4: re-normalização para conservar S + E + I + R = N
        S, E, I, R = _normalize_compartments(S_new, E_new, I_new, R_new, N)

        # Passo 5: registrar estado do dia corrente
        result.susceptible.append(round(S, 4))
        result.exposed.append(round(E, 4))
        result.infected.append(round(I, 4))
        result.recovered.append(round(R, 4))

    # ── Cálculo de metadados ─────────────────────────────────────────────────

    # Pico de infectados e dia do pico
    result.peak_infected = max(result.infected)
    result.peak_day = result.infected.index(result.peak_infected)

    # Total de indivíduos que passaram pela doença ≈ R(30) + I(30)
    result.total_infected = result.recovered[-1] + result.infected[-1]

    # Número de reprodução básico: R₀ = β / γ
    result.r0 = round(beta / gamma, 4)

    return result