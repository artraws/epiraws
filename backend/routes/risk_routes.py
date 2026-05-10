# =============================================================================
# routes/risk_routes.py
# =============================================================================
# Define os endpoints REST da API EpiRaws.
#
# Rota principal:
#   POST /calculate_risk
#       - Valida os dados de entrada (via Pydantic, no schema)
#       - Executa o motor heurístico de risco individual
#       - Executa o simulador SEIR
#       - Retorna um JSON padronizado com resultados e projeção
# =============================================================================

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from schemas.request_models import RiskRequest, RiskResponse, SEIRProjection
from services.risk_engine import calculate_individual_risk
from services.seir_model import run_seir_simulation

# Configura logger para este módulo
logger = logging.getLogger("epiraws.routes")

# Cria o roteador (será registrado no app principal com prefixo vazio ou /api)
router = APIRouter(tags=["Epidemiologia"])


# =============================================================================
# POST /calculate_risk
# =============================================================================

@router.post(
    "/calculate_risk",
    response_model=RiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Calcular risco individual e simular propagação SEIR",
    description=(
        "Recebe dados clínicos, comportamentais e epidemiológicos do usuário. "
        "Retorna a probabilidade de infecção individual (0–100%) e a projeção "
        "SEIR para os próximos 30 dias resolvida pelo Método de Euler."
    ),
    responses={
        200: {"description": "Cálculo realizado com sucesso."},
        422: {"description": "Dados de entrada inválidos (validação Pydantic)."},
        500: {"description": "Erro interno inesperado no motor matemático."},
    },
)
async def calculate_risk(payload: RiskRequest) -> JSONResponse:
    """
    Handler do endpoint POST /calculate_risk.

    Fluxo de execução:
    1. Pydantic já validou `payload` antes de chegar aqui.
    2. Chama o motor heurístico com os dados individuais.
    3. Chama o simulador SEIR com os dados comunitários.
    4. Compõe e retorna a resposta padronizada.
    """

    # ── Passo 1: Motor de Risco Individual ───────────────────────────────────

    try:
        risk_result = calculate_individual_risk(
            contacts=payload.contacts,
            days_exposed=payload.days_exposed,
            temperature=payload.temperature,
            symptoms=payload.symptoms,
            mask=payload.mask,
            vaccinated=payload.vaccinated,
            # nearby_infected: usamos o número inicial de infectados como proxy
            # para quantos casos confirmados existem na comunidade próxima.
            nearby_infected=payload.infected,
        )
    except Exception as exc:
        logger.exception("Erro no motor heurístico de risco: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Erro interno ao calcular o risco individual. "
                f"Detalhes: {str(exc)}"
            ),
        )

    # ── Passo 2: Simulação SEIR ──────────────────────────────────────────────

    try:
        seir_result = run_seir_simulation(
            population=payload.population,
            infected=payload.infected,
            exposed=payload.exposed,
            beta=payload.beta,
            gamma=payload.gamma,
            sigma=payload.sigma,
            days=30,
        )
    except ValueError as exc:
        # Erros de domínio matemático (parâmetros inválidos)
        logger.warning("Parâmetros SEIR inválidos: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parâmetros epidemiológicos inválidos: {str(exc)}",
        )
    except Exception as exc:
        logger.exception("Erro no simulador SEIR: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Erro interno na simulação epidemiológica. "
                f"Detalhes: {str(exc)}"
            ),
        )

    # ── Passo 3: Composição da resposta ─────────────────────────────────────

    projection = SEIRProjection(
        susceptible=seir_result.susceptible,
        exposed=seir_result.exposed,
        infected=seir_result.infected,
        recovered=seir_result.recovered,
    )

    response = RiskResponse(
        risk_percentage=risk_result.risk_percentage,
        risk_level=risk_result.risk_level,
        message=risk_result.message,
        projection=projection,
    )

    logger.info(
        "Risco calculado: %.2f%% (%s) | R₀=%.2f | Pico I: dia %d",
        risk_result.risk_percentage,
        risk_result.risk_level,
        seir_result.r0,
        seir_result.peak_day,
    )

    return JSONResponse(
        content=response.model_dump(),
        status_code=status.HTTP_200_OK,
    )


# =============================================================================
# GET /health  — endpoint de saúde da API
# =============================================================================

@router.get(
    "/health",
    tags=["Sistema"],
    summary="Verificação de saúde da API",
    description="Retorna status 200 se a API estiver operacional.",
)
async def health_check() -> dict:
    """Endpoint de health check para monitoramento e load balancers."""
    return {
        "status": "ok",
        "service": "EpiRaws API",
        "version": "1.0.0",
    }