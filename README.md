# 🧬 EpiRaws — Plataforma Inteligente de Simulação Epidemiológica

> Calculadora Epidemiológica Inteligente — Motor matemático, API REST e Dashboard Científico

---

## 📖 Visão Geral

O **EpiRaws** é uma plataforma web científica desenvolvida para análise epidemiológica, cálculo de risco individual e projeções populacionais utilizando modelagem matemática baseada no modelo **SEIR**.

O sistema combina:

- Modelagem matemática;
- Simulação computacional;
- Visualização científica de dados;
- Arquitetura moderna de APIs;
- Dashboard epidemiológico interativo.

A plataforma é composta por dois motores principais:

1. **Motor Heurístico de Risco Individual** — calcula a probabilidade percentual de infecção de um indivíduo com base em fatores clínicos e comportamentais.
2. **Simulador SEIR** — simula a propagação epidemiológica utilizando o modelo matemático SEIR resolvido pelo Método de Euler.

---



## 🏗️ Estrutura do Projeto

```bash
EpiRaws/
│
├── backend/
│   ├── app.py                    # Ponto de entrada FastAPI
│   ├── routes/
│   │   └── risk_routes.py        # Endpoints REST
│   ├── services/
│   │   ├── risk_engine.py        # Motor heurístico de risco
│   │   └── seir_model.py         # Simulador SEIR + Euler
│   ├── schemas/
│   │   └── request_models.py     # Schemas Pydantic
│   ├── utils/
│   ├── requirements.txt
│   
│
├── frontend/
│   ├── index.html                # Estrutura principal
│   ├── style.css                 # Interface e animações
│   └── script.js                 # Integração frontend/backend
│   
└── README.md
```

---

# ⚙️ Tecnologias Utilizadas

## Backend

| Tecnologia | Função |
|---|---|
| Python | Linguagem principal |
| FastAPI | API REST assíncrona |
| Uvicorn | Servidor ASGI |
| Pydantic | Validação de dados |

---

## Frontend

| Tecnologia | Função |
|---|---|
| HTML5 | Estrutura |
| CSS3 | Interface e animações |
| JavaScript | Integração dinâmica |
| Chart.js | Visualização gráfica |

---

# 🚀 Instalação

## 📦 Pré-requisitos

- Python 3.11+
- pip

---

# 🔧 Executando o Backend

```bash
# Navegue até a pasta backend
cd backend

# Crie e ative um ambiente virtual
python -m venv venv

source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Instale as dependências
pip install -r requirements.txt

# Execute o servidor
python app.py

# ou diretamente com uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Servidor disponível em:

```bash
http://localhost:8000
```

Swagger/OpenAPI:

```bash
http://localhost:8000/docs
```

---

# 🌐 Executando o Frontend

Abra:

```bash
frontend/
```

Depois:

- abra o arquivo `index.html`;
- ou utilize Live Server no VS Code.

O frontend realiza requisições para:

```bash
http://localhost:8000/calculate_risk
```

---

# 🔌 Endpoints

## `POST /calculate_risk`

Calcula:
- risco individual;
- classificação epidemiológica;
- projeção SEIR;
- curvas epidemiológicas.

---

## 📥 Corpo da Requisição (JSON)

```json
{
  "contacts": 10,
  "days_exposed": 3,
  "temperature": 38.2,
  "symptoms": true,
  "mask": false,
  "vaccinated": false,
  "population": 10000,
  "infected": 20,
  "exposed": 15,
  "beta": 0.35,
  "gamma": 0.12,
  "sigma": 0.20
}
```

---

## 📤 Resposta (200 OK)

```json
{
  "risk_percentage": 82.5,
  "risk_level": "Alto Risco",
  "message": "ATENÇÃO: Alto risco detectado com presença de sintomas...",
  "projection": {
    "susceptible": [9965.0, 9960.2],
    "exposed":     [15.0, 17.8],
    "infected":    [20.0, 22.1],
    "recovered":   [0.0, 2.4]
  }
}
```

---

## `GET /health`

Retorna:

```json
{
  "status": "ok"
}
```

Utilizado para:
- monitoramento;
- health checks;
- load balancers.

---

## `GET /docs`

Documentação Swagger/OpenAPI.

---

## `GET /redoc`

Documentação alternativa ReDoc.

---

# 📐 Modelo Matemático — Motor Heurístico

O risco individual é calculado por uma **soma ponderada normalizada**:

```text
raw_score = Σ (weight_i × factor_i)

risk_pct = clamp(raw_score / MAX_SCORE × 100, 0, 100)
```

---

## 📊 Pesos Utilizados

| Fator | Peso | Tipo |
|---|---|---|
| Contatos recentes | 2.5 | Sub-linear (√contacts) |
| Temperatura | 18.0 | Escalonada por limiar |
| Sintomas | 25.0 | Binário |
| Sem máscara | 12.0 | Penalidade |
| Vacinação | −35% | Redução proporcional |
| Dias de exposição | 3.0 | Linear |
| Infectados próximos | 1.5 | Linear |

---

## 🚨 Classificação de Risco

- **0–33%** → Baixo Risco
- **34–66%** → Médio Risco
- **67–100%** → Alto Risco

---

# 🦠 Modelo Matemático — SEIR + Euler

## Sistema de Equações Diferenciais

```text
dS/dt = -β · S · I / N

dE/dt = β · S · I / N − σ · E

dI/dt = σ · E − γ · I

dR/dt = γ · I
```

---

## 🔢 Integração Numérica — Método de Euler

```text
X(t+1) = X(t) + Δt · dX/dt(t)
```

---

## 📌 Conservação Populacional

```text
S + E + I + R = N
```

---

## 📈 Número Básico de Reprodução

```text
R₀ = β / γ
```

---

# 🔐 Segurança

- CORS explícito — sem `allow_origins=["*"]`
- Toda lógica matemática permanece no backend
- Validação Pydantic v2
- Validação cruzada:

```text
infected + exposed ≤ population
```

- Tratamento global de exceções
- Clamp numérico em todos os compartimentos SEIR
- Re-normalização para preservar:

```text
S + E + I + R = N
```

---

# 🎯 Diferenciais do Projeto

## 📚 Matemática Aplicada

- Modelo SEIR completo;
- Método de Euler;
- Simulação temporal;
- Projeções epidemiológicas.

---

## 💻 Engenharia de Software

- API REST modular;
- Frontend desacoplado;
- Arquitetura escalável;
- Código organizado.

---

## 🎨 Dashboard Científico

- Interface futurista;
- Visual cyber/neon;
- Curvas epidemiológicas;
- Métricas em tempo real;
- Interpretação matemática integrada.

---

# 🎓 Objetivo Científico

O EpiRaws demonstra como:

- Sistemas de Informação;
- Modelagem Matemática;
- APIs modernas;
- Simulações computacionais;
- Visualização científica;

podem auxiliar:
- análises epidemiológicas;
- sustentabilidade tecnológica;
- tomada de decisão;
- apoio computacional à saúde pública.

---

# 🏛️ Instituição

Projeto acadêmico desenvolvido na Universidade Federal Rural de Pernambuco (UFRPE).

Curso de **Sistemas de Informação** — 2026.

---

# 👨‍💻 Autor

**Arthur Ricardo da Silva**

Orientação:
**Prof. Jones Alburqueque**

---

# 📄 Licença

Projeto acadêmico e científico desenvolvido para fins educacionais e de pesquisa.
