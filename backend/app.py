# =============================================================================
# app.py — Ponto de Entrada da API EpiRaws
# =============================================================================
# Configura e inicializa a aplicação FastAPI com:
#   - CORS seguro (origens explícitas, sem wildcard)
#   - Handler global de exceções
#   - Registro dos roteadores
#   - Middleware de logging de requisições
#   - Documentação OpenAPI customizada
# =============================================================================

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from routes.risk_routes import router as risk_router

# =============================================================================
# CONFIGURAÇÃO DE LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("epiraws.app")


# =============================================================================
# LIFESPAN — eventos de inicialização e desligamento
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gerencia o ciclo de vida da aplicação.
    Código antes do `yield` executa na inicialização;
    código após o `yield` executa no desligamento.
    """
    logger.info("=" * 60)
    logger.info("  EpiRaws API — Iniciando servidor...")
    logger.info("  Motor SEIR:          ATIVO")
    logger.info("  Motor Heurístico:    ATIVO")
    logger.info("  Documentação:        http://localhost:8000/docs")
    logger.info("=" * 60)
    yield
    logger.info("EpiRaws API — Servidor encerrado.")


# =============================================================================
# INSTÂNCIA FASTAPI
# =============================================================================

app = FastAPI(
    title="EpiRaws — Calculadora Epidemiológica Inteligente",
    description=(
        "API REST para cálculo de risco individual de infecção e simulação "
        "epidemiológica baseada no modelo SEIR, resolvido pelo Método de Euler. "
        "\n\n"
        "**Modelos matemáticos implementados:**\n"
        "- Motor Heurístico de Risco Individual (soma ponderada normalizada)\n"
        "- Simulador SEIR com integração numérica de Euler (30 dias)\n\n"
        "Desenvolvido com FastAPI + Pydantic v2 + Uvicorn."
    ),
    version="1.0.0",
    contact={
        "name": "EpiRaws Team",
        "email": "contato@epiraws.dev",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# =============================================================================
# CORS — CONFIGURAÇÃO SEGURA
# =============================================================================
# IMPORTANTE: NÃO usamos allow_origins=["*"].
# As origens permitidas são listadas explicitamente.
# Em produção, substitua pelos domínios reais do frontend.

ALLOWED_ORIGINS: list[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5500",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8080",
    # Adicione aqui o domínio de produção do frontend:
    # "https://epiraws.seudominio.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Request-ID"],
)


# =============================================================================
# MIDDLEWARE — LOGGING DE REQUISIÇÕES
# =============================================================================

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Registra cada requisição com: método, path, status code e latência.
    Não registra o corpo da requisição (proteção de dados do usuário).
    """
    start_time = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "%s %s → %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )

    return response


# =============================================================================
# HANDLERS GLOBAIS DE EXCEÇÃO
# =============================================================================

@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """
    Captura erros de validação do Pydantic que eventualmente escapem
    do fluxo normal (ex.: erros em dependências ou conversões internas).
    Retorna um JSON padronizado e legível com os detalhes do erro.
    """
    logger.warning("Erro de validação Pydantic: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Dados de entrada inválidos.",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """
    Captura ValueErrors não tratados nos serviços.
    Evita que erros matemáticos internos exponham stack traces ao cliente.
    """
    logger.warning("ValueError não tratado: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": f"Parâmetro inválido: {str(exc)}"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler de último recurso para exceções inesperadas.
    Retorna 500 sem expor detalhes internos sensíveis ao cliente.
    """
    logger.exception("Exceção inesperada em %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": (
                "Erro interno do servidor. Por favor, tente novamente. "
                "Se o problema persistir, contate o suporte."
            )
        },
    )


# =============================================================================
# REGISTRO DE ROTEADORES
# =============================================================================

app.include_router(risk_router)


# =============================================================================
# ENDPOINT RAIZ
# =============================================================================

@app.get(
    "/",
    tags=["Sistema"],
    summary="Informações da API",
    description="Retorna informações básicas sobre a API EpiRaws.",
)
async def root() -> dict:
    return {
        "name": "EpiRaws — Calculadora Epidemiológica Inteligente",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "POST /calculate_risk": "Calcular risco individual + simulação SEIR",
            "GET  /health":         "Health check da API",
        },
    }


# =============================================================================
# ENTRYPOINT (execução direta: python app.py)
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,            # Recarregamento automático em desenvolvimento
        log_level="info",
        access_log=True,
    )