/* ============================================================================
   EpiRaws — script.js
   Responsabilidades:
     1. Coletar e validar dados do formulário
     2. Enviar requisição POST /calculate_risk ao backend FastAPI
     3. Renderizar resultados: gauge de risco, cards SEIR, gráfico Chart.js
     4. Animar o medidor circular e as transições de estado
     5. Gerenciar estados: vazio → loading → resultado | erro
   ============================================================================ */

'use strict';

/* ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────── */

const API_BASE = 'http://localhost:8000';
const API_ENDPOINT = `${API_BASE}/calculate_risk`;

/* ── REFERÊNCIAS DOM ───────────────────────────────────────────────────────── */

const form          = document.getElementById('epiForm');
const btnCalculate  = document.getElementById('btnCalculate');

// Painéis de estado
const emptyState    = document.getElementById('emptyState');
const loadingState  = document.getElementById('loadingState');
const errorState    = document.getElementById('errorState');
const resultsContent= document.getElementById('resultsContent');
const errorMessage  = document.getElementById('errorMessage');

// Temperatura
const tempInput     = document.getElementById('temperature');
const tempBarFill   = document.getElementById('tempBarFill');
const tempStatus    = document.getElementById('tempStatus');

// Risco
const riskGauge     = document.getElementById('riskGauge');
const gaugeFill     = document.getElementById('gaugeFill');
const gaugePct      = document.getElementById('gaugePct');
const riskLevelBadge= document.getElementById('riskLevelBadge');
const riskMessage   = document.getElementById('riskMessage');

// Stats SEIR
const statS         = document.getElementById('statS');
const statE         = document.getElementById('statE');
const statI         = document.getElementById('statI');
const statR         = document.getElementById('statR');
const metaR0        = document.getElementById('metaR0');
const metaPeak      = document.getElementById('metaPeak');
const metaPeakDay   = document.getElementById('metaPeakDay');
const metaInfPeriod = document.getElementById('metaInfPeriod');

// Math toggle
const mathToggle    = document.getElementById('mathToggle');
const mathContent   = document.getElementById('mathContent');

// Loading steps
const loadSteps     = [
  document.getElementById('ls1'),
  document.getElementById('ls2'),
  document.getElementById('ls3'),
  document.getElementById('ls4'),
];

/* ── ESTADO GLOBAL ─────────────────────────────────────────────────────────── */

let seirChart = null;   // instância Chart.js (reutilizada nas atualizações)
let loadingTimer = null; // timeout de steps de loading

/* ══════════════════════════════════════════════════════════════════════════════
   INDICADOR DE TEMPERATURA
   Atualiza a barra de cor e o rótulo conforme o valor digitado
══════════════════════════════════════════════════════════════════════════════ */

function updateTempIndicator(val) {
  const v = parseFloat(val);
  if (isNaN(v)) return;

  // Mapeamento: 34°C = 0%, 43°C = 100%
  const pct = Math.max(0, Math.min(100, ((v - 34) / 9) * 100));
  tempBarFill.style.width = `${pct}%`;

  // Cores e rótulos por faixa clínica
  let color, label;
  if (v < 36.0)      { color = '#4fc3f7'; label = 'Hipotermia'; }
  else if (v < 37.5) { color = '#00e676'; label = 'Normal'; }
  else if (v < 38.5) { color = '#ffb300'; label = 'Febre baixa'; }
  else if (v < 39.5) { color = '#ff7043'; label = 'Febre moderada'; }
  else               { color = '#ff3d54'; label = 'Febre alta'; }

  tempBarFill.style.background = color;
  tempStatus.textContent = label;
  tempStatus.style.color = color;
}

tempInput.addEventListener('input', () => updateTempIndicator(tempInput.value));
updateTempIndicator(tempInput.value); // inicializa

/* ══════════════════════════════════════════════════════════════════════════════
   MATH TOGGLE (colapsível)
══════════════════════════════════════════════════════════════════════════════ */

function toggleMath() {
  const isExpanded = mathToggle.getAttribute('aria-expanded') === 'true';
  mathToggle.setAttribute('aria-expanded', String(!isExpanded));
  mathContent.hidden = isExpanded;
}

mathToggle.addEventListener('click', toggleMath);
mathToggle.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleMath(); }
});

/* ══════════════════════════════════════════════════════════════════════════════
   COLETA DE DADOS DO FORMULÁRIO
   Retorna um objeto pronto para JSON.stringify, ou null se inválido.
══════════════════════════════════════════════════════════════════════════════ */

function collectFormData() {
  const get = (id) => document.getElementById(id);
  const radio = (name) => {
    const el = document.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value === 'true' : false;
  };

  const contacts     = parseInt(get('contacts').value,    10);
  const days_exposed = parseInt(get('days_exposed').value,10);
  const temperature  = parseFloat(get('temperature').value);
  const symptoms     = radio('symptoms');
  const mask         = radio('mask');
  const vaccinated   = radio('vaccinated');
  const population   = parseInt(get('population').value,  10);
  const exposed      = parseInt(get('exposed').value,     10);
  const infected     = parseInt(get('infected').value,    10);
  const beta         = parseFloat(get('beta').value);
  const gamma        = parseFloat(get('gamma').value);
  const sigma        = parseFloat(get('sigma').value);

  // Validação rápida client-side (o servidor valida definitivamente)
  const errors = [];
  if (isNaN(contacts)     || contacts < 0)        errors.push('Contatos deve ser ≥ 0.');
  if (isNaN(days_exposed) || days_exposed < 0)     errors.push('Dias de exposição deve ser ≥ 0.');
  if (isNaN(temperature)  || temperature < 34 || temperature > 43)
    errors.push('Temperatura deve estar entre 34 e 43 °C.');
  if (isNaN(population)   || population < 1)       errors.push('População deve ser ≥ 1.');
  if (isNaN(exposed)      || exposed < 0)          errors.push('Expostos iniciais deve ser ≥ 0.');
  if (isNaN(infected)     || infected < 0)         errors.push('Infectados iniciais deve ser ≥ 0.');
  if (isNaN(beta)         || beta <= 0)            errors.push('β (beta) deve ser > 0.');
  if (isNaN(gamma)        || gamma <= 0)           errors.push('γ (gamma) deve ser > 0.');
  if (isNaN(sigma)        || sigma <= 0)           errors.push('σ (sigma) deve ser > 0.');
  if (!isNaN(infected) && !isNaN(exposed) && !isNaN(population)) {
    if (infected + exposed > population)
      errors.push('Infectados + Expostos não pode exceder a população total.');
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  return {
    valid: true,
    data: {
      contacts, days_exposed, temperature,
      symptoms, mask, vaccinated,
      population, exposed, infected,
      beta, gamma, sigma
    }
  };
}

/* ══════════════════════════════════════════════════════════════════════════════
   GERENCIAMENTO DE ESTADOS DE UI
══════════════════════════════════════════════════════════════════════════════ */

function showState(state) {
  // Esconde todos
  emptyState.hidden    = true;
  loadingState.hidden  = true;
  errorState.hidden    = true;
  resultsContent.hidden = true;

  // Mostra o desejado
  switch (state) {
    case 'empty':   emptyState.hidden    = false; break;
    case 'loading': loadingState.hidden  = false; break;
    case 'error':   errorState.hidden    = false; break;
    case 'results': resultsContent.hidden = false; break;
  }
}

/* Simula progresso dos steps de loading com delays */
function animateLoadingSteps() {
  // Reseta
  loadSteps.forEach((s, i) => {
    s.className = 'load-step';
    s.textContent = ['✓ Validando parâmetros', '⟳ Calculando risco individual',
                     '— Simulando propagação (30 dias)', '— Gerando projeção'][i];
  });

  const delays = [0, 400, 900, 1600];
  const labels = [
    '✓ Validando parâmetros',
    '✓ Calculando risco individual',
    '✓ Simulando propagação (30 dias)',
    '✓ Gerando projeção'
  ];

  delays.forEach((delay, i) => {
    loadingTimer = setTimeout(() => {
      if (i > 0) {
        loadSteps[i - 1].className = 'load-step done';
        loadSteps[i - 1].textContent = labels[i - 1];
      }
      if (i < loadSteps.length) {
        loadSteps[i].className = 'load-step active';
      }
    }, delay);
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   GAUGE — MEDIDOR CIRCULAR
   Animação do arco SVG: converte percentagem em stroke-dashoffset
══════════════════════════════════════════════════════════════════════════════ */

function animateGauge(pct) {
  /*
   * O arco do gauge cobre 270° (3/4 do círculo).
   * Circunferência total do círculo r=80: C = 2π × 80 ≈ 502.65
   * Arco ativo = 3/4 × C = 376.99
   *
   * stroke-dasharray = 376.99 (arco visível total)
   * stroke-dashoffset: 376.99 = 0% preenchido
   *                    0      = 100% preenchido
   *
   * offset = 376.99 × (1 - pct/100)
   */
  const arcLength = 376.99;
  const offset = arcLength * (1 - pct / 100);

  gaugeFill.style.strokeDasharray  = `${arcLength}`;
  gaugeFill.style.strokeDashoffset = `${offset}`;
  gaugePct.textContent = `${Math.round(pct)}%`;
}

function setRiskTheme(level) {
  // Remove classes anteriores
  riskGauge.classList.remove('risk-low', 'risk-med', 'risk-high');

  if (level === 'Baixo Risco')  riskGauge.classList.add('risk-low');
  else if (level === 'Médio Risco') riskGauge.classList.add('risk-med');
  else                          riskGauge.classList.add('risk-high');
}

/* ══════════════════════════════════════════════════════════════════════════════
   FORMATAÇÃO NUMÉRICA
══════════════════════════════════════════════════════════════════════════════ */

function fmt(n, decimals = 0) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return Number(n).toLocaleString('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtPct(n, total) {
  if (!total || total === 0) return fmt(n);
  const pct = (n / total * 100).toFixed(1);
  return `${fmt(n)} (${pct}%)`;
}

/* ══════════════════════════════════════════════════════════════════════════════
   RENDERIZAÇÃO DOS RESULTADOS
══════════════════════════════════════════════════════════════════════════════ */

function renderResults(data, population) {
  const { risk_percentage, risk_level, message, projection } = data;

  /* ── Risco individual ── */
  animateGauge(risk_percentage);
  setRiskTheme(risk_level);
  riskLevelBadge.textContent = risk_level;
  riskMessage.textContent = message;

  /* ── Stats SEIR (dia 30, último elemento dos arrays) ── */
  const s30 = projection.susceptible[projection.susceptible.length - 1];
  const e30 = projection.exposed[projection.exposed.length   - 1];
  const i30 = projection.infected[projection.infected.length - 1];
  const r30 = projection.recovered[projection.recovered.length - 1];

  statS.textContent = fmtPct(s30, population);
  statE.textContent = fmtPct(e30, population);
  statI.textContent = fmtPct(i30, population);
  statR.textContent = fmtPct(r30, population);

  /* ── Metadados calculados no frontend com base na projeção ── */
  const peakI   = Math.max(...projection.infected);
  const peakDay = projection.infected.indexOf(peakI);
  const r0      = data.r0 ?? (parseFloat(document.getElementById('beta').value) /
                               parseFloat(document.getElementById('gamma').value));
  const gammVal = parseFloat(document.getElementById('gamma').value);
  const infPeriod = gammVal > 0 ? (1 / gammVal).toFixed(1) : '—';

  metaR0.textContent       = isNaN(r0)      ? '—' : r0.toFixed(2);
  metaPeak.textContent     = fmt(peakI);
  metaPeakDay.textContent  = `Dia ${peakDay}`;
  metaInfPeriod.textContent= `${infPeriod} dias`;

  /* ── Coloração do R₀ ── */
  const r0num = parseFloat(r0);
  if (!isNaN(r0num)) {
    metaR0.style.color = r0num >= 1 ? 'var(--red)' : 'var(--green)';
  }

  /* ── Gráfico SEIR ── */
  renderChart(projection);

  /* ── Exibe painel de resultados ── */
  showState('results');
}

/* ══════════════════════════════════════════════════════════════════════════════
   CHART.JS — GRÁFICO SEIR
══════════════════════════════════════════════════════════════════════════════ */

function renderChart(projection) {
  const ctx = document.getElementById('seirChart').getContext('2d');
  const days = Array.from({ length: projection.susceptible.length }, (_, i) => i);

  const commonLineOpts = {
    fill: false,
    tension: 0.4,
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 2,
  };

  const datasets = [
    {
      ...commonLineOpts,
      label: 'Suscetíveis (S)',
      data: projection.susceptible,
      borderColor: '#4fc3f7',
      pointHoverBackgroundColor: '#4fc3f7',
      pointHoverBorderColor: '#fff',
    },
    {
      ...commonLineOpts,
      label: 'Expostos (E)',
      data: projection.exposed,
      borderColor: '#ffd54f',
      pointHoverBackgroundColor: '#ffd54f',
      pointHoverBorderColor: '#fff',
    },
    {
      ...commonLineOpts,
      label: 'Infectados (I)',
      data: projection.infected,
      borderColor: '#ff7043',
      borderWidth: 2.5,
      pointHoverBackgroundColor: '#ff7043',
      pointHoverBorderColor: '#fff',
    },
    {
      ...commonLineOpts,
      label: 'Recuperados (R)',
      data: projection.recovered,
      borderColor: '#69f0ae',
      pointHoverBackgroundColor: '#69f0ae',
      pointHoverBorderColor: '#fff',
    },
  ];

  // Destrói instância anterior se existir
  if (seirChart) {
    seirChart.destroy();
    seirChart = null;
  }

  seirChart = new Chart(ctx, {
    type: 'line',
    data: { labels: days, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 1200,
        easing: 'easeInOutQuart',
      },
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: { display: false },  // legenda customizada no HTML
        tooltip: {
          backgroundColor: 'rgba(6, 15, 30, 0.95)',
          borderColor: 'rgba(0, 229, 255, 0.25)',
          borderWidth: 1,
          titleColor: '#7a9ec8',
          bodyColor: '#e0f0ff',
          titleFont: { family: "'Share Tech Mono', monospace", size: 11 },
          bodyFont:  { family: "'Share Tech Mono', monospace", size: 11 },
          padding: 12,
          callbacks: {
            title(items) {
              return `Dia ${items[0].label}`;
            },
            label(item) {
              const v = item.raw;
              const label = item.dataset.label;
              return `  ${label}: ${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Dias',
            color: '#3d5a7a',
            font: { family: "'Share Tech Mono', monospace", size: 10 },
            padding: { top: 6 },
          },
          ticks: {
            color: '#3d5a7a',
            font: { family: "'Share Tech Mono', monospace", size: 10 },
            maxTicksLimit: 10,
          },
          grid: { color: 'rgba(255,255,255,0.04)' },
          border: { color: 'rgba(255,255,255,0.06)' },
        },
        y: {
          title: {
            display: true,
            text: 'Indivíduos',
            color: '#3d5a7a',
            font: { family: "'Share Tech Mono', monospace", size: 10 },
            padding: { right: 8 },
          },
          ticks: {
            color: '#3d5a7a',
            font: { family: "'Share Tech Mono', monospace", size: 10 },
            maxTicksLimit: 6,
            callback(val) {
              if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
              if (val >= 1_000)    return `${(val / 1_000).toFixed(0)}k`;
              return val;
            },
          },
          grid: { color: 'rgba(255,255,255,0.04)' },
          border: { color: 'rgba(255,255,255,0.06)' },
        },
      },
    },
  });
}

/* ══════════════════════════════════════════════════════════════════════════════
   REQUISIÇÃO À API
══════════════════════════════════════════════════════════════════════════════ */

async function callAPI(payload) {
  const response = await fetch(API_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept':       'application/json',
    },
    body: JSON.stringify(payload),
  });

  const json = await response.json();

  if (!response.ok) {
    // Extrai mensagem de erro do formato Pydantic ou genérico
    const detail = json?.detail ?? json?.message ?? `Erro HTTP ${response.status}`;
    if (Array.isArray(detail)) {
      // Erros Pydantic: array de objetos com { loc, msg }
      const msgs = detail.map(e => `[${(e.loc || []).join('.')}] ${e.msg}`).join('\n');
      throw new Error(msgs);
    }
    throw new Error(String(detail));
  }

  return json;
}

/* ══════════════════════════════════════════════════════════════════════════════
   SUBMIT DO FORMULÁRIO
══════════════════════════════════════════════════════════════════════════════ */

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  /* ── Coleta e validação client-side ── */
  const result = collectFormData();
  if (!result.valid) {
    errorMessage.textContent = result.errors.join(' | ');
    showState('error');
    return;
  }

  /* ── Inicia loading ── */
  btnCalculate.disabled = true;
  showState('loading');
  animateLoadingSteps();

  try {
    /* ── Chama a API ── */
    const data = await callAPI(result.data);

    /* ── Marca todos os steps como concluídos ── */
    clearTimeout(loadingTimer);
    loadSteps.forEach((s, i) => {
      s.className = 'load-step done';
      s.textContent = ['✓ Validando parâmetros', '✓ Calculando risco individual',
                       '✓ Simulando propagação (30 dias)', '✓ Gerando projeção'][i];
    });

    /* Pequena pausa para o usuário ver os steps concluídos */
    await new Promise(r => setTimeout(r, 400));

    /* ── Renderiza ── */
    renderResults(data, result.data.population);

  } catch (err) {
    clearTimeout(loadingTimer);
    console.error('[EpiRaws] Erro na análise:', err);

    // Mensagem amigável baseada no tipo de erro
    let friendlyMsg = err.message || 'Erro desconhecido.';

    if (err instanceof TypeError && err.message.includes('fetch')) {
      friendlyMsg =
        'Não foi possível conectar ao servidor. ' +
        'Verifique se o backend EpiRaws está rodando em http://localhost:8000.';
    }

    errorMessage.textContent = friendlyMsg;
    showState('error');

  } finally {
    btnCalculate.disabled = false;
  }
});

/* ══════════════════════════════════════════════════════════════════════════════
   INICIALIZAÇÃO
══════════════════════════════════════════════════════════════════════════════ */

(function init() {
  // Estado inicial
  showState('empty');

  // Verifica disponibilidade da API em background (silent — não bloqueia o usuário)
  fetch(`${API_BASE}/health`, { method: 'GET', signal: AbortSignal.timeout(3000) })
    .then(r => {
      if (!r.ok) throw new Error('Servidor retornou erro.');
      console.info('[EpiRaws] Backend conectado ✓');
    })
    .catch(() => {
      // Exibe aviso discreto no console — sem bloquear a UI
      console.warn(
        '[EpiRaws] Backend não detectado em http://localhost:8000. ' +
        'Inicie o servidor antes de executar análises.'
      );
    });

  console.info(
    '%c EpiRaws v1.0.0 %c Calculadora Epidemiológica Inteligente ',
    'background:#00e5ff;color:#030912;font-weight:bold;padding:4px 8px;',
    'background:#060f1e;color:#7a9ec8;padding:4px 8px;border:1px solid #00e5ff40;'
  );
})();