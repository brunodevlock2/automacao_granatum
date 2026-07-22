document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    loadOpcoes();
    setupMenu();
});

// --- Menu Navigation ---
function setupMenu() {
    const items = document.querySelectorAll('.menu-item');
    const sections = document.querySelectorAll('.form-section');

    items.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = item.getAttribute('data-target');
            
            // Update active state in menu
            items.forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            // Show target section
            sections.forEach(s => s.classList.remove('active-section'));
            document.getElementById(targetId).classList.add('active-section');
        });
    });
}

// --- WebSocket for Real-time Logs ---
let ws;
const terminalOutput = document.getElementById('terminal-output');
const progressBar = document.getElementById('progress-bar');
const wsStatus = document.getElementById('ws-status');
const wsDot = document.getElementById('ws-dot');

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        wsStatus.textContent = 'Conectado';
        wsDot.className = 'dot connected';
    };

    ws.onclose = () => {
        wsStatus.textContent = 'Desconectado';
        wsDot.className = 'dot disconnected';
        // Try to reconnect
        setTimeout(initWebSocket, 3000);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                appendLog(data.message);
                updateProgress(data.message);
            } else if (data.type === 'done') {
                appendLog(data.message, 'system-msg');
                progressBar.classList.remove('active');
                progressBar.style.width = '100%';
                enableButtons();
            }
        } catch (e) {
            appendLog(event.data);
        }
    };
}

function appendLog(text, className = '') {
    const div = document.createElement('div');
    div.className = `log-line ${className}`;
    div.textContent = text;
    terminalOutput.appendChild(div);
    // Auto-scroll
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Simple heuristic to extract progress from logs (e.g. "Clientes: 2/5" or "25%")
function updateProgress(message) {
    const ratioMatch = message.match(/(\d+)\/(\d+)/);
    if (ratioMatch) {
        const current = parseInt(ratioMatch[1]);
        const total = parseInt(ratioMatch[2]);
        if (total > 0) {
            const pct = (current / total) * 100;
            progressBar.style.width = `${pct}%`;
        }
    }
}

// --- Fetch Data Options ---
async function loadOpcoes() {
    try {
        const res = await fetch('/api/opcoes');
        const data = await res.json();
        
        populateSelect('add-lista', data.listas_clientes);
        populateSelect('rem-lista', data.listas_clientes);
        
        populateSelect('add-categoria', data.categorias, true);
        populateSelect('rem-categoria', data.categorias, true, 'Todas');
        
        populateSelect('add-centro-custo', data.centros_custo, true, 'Nenhum');
    } catch (e) {
        console.error('Erro ao carregar opções', e);
        appendLog('Erro ao carregar configurações da API.', 'system-msg');
    }
}

function populateSelect(id, items, isObject = false, defaultLabel = null) {
    const select = document.getElementById(id);
    if (!select) return;
    
    select.innerHTML = '';
    
    if (defaultLabel !== null) {
        select.innerHTML += `<option value="0">${defaultLabel}</option>`;
    }

    items.forEach(item => {
        const option = document.createElement('option');
        if (isObject) {
            option.value = item.id;
            option.textContent = item.descricao;
        } else {
            option.value = item;
            option.textContent = item;
        }
        select.appendChild(option);
    });
}

// --- API Submissions ---
function disableButtons() {
    document.querySelectorAll('.btn').forEach(b => b.disabled = true);
    progressBar.style.width = '0%';
    progressBar.classList.add('active');
    terminalOutput.innerHTML = '<div class="log-line system-msg">Iniciando tarefa...</div>';
}

function enableButtons() {
    document.querySelectorAll('.btn').forEach(b => b.disabled = false);
}

async function submitAdicionar() {
    disableButtons();
    
    const payload = {
        lista_arquivo: document.getElementById('add-lista').value,
        data_inicio: document.getElementById('add-data-inicio').value,
        data_fim: document.getElementById('add-data-fim').value,
        descricao: document.getElementById('add-descricao').value,
        valor: parseFloat(document.getElementById('add-valor').value),
        categoria_id: parseInt(document.getElementById('add-categoria').value)
    };
    
    const ccl = document.getElementById('add-centro-custo').value;
    if (ccl && ccl !== '0') payload.centro_custo_id = parseInt(ccl);
    
    const dias = document.getElementById('add-dias').value;
    if (dias) payload.dias_para_emissao = parseInt(dias);

    await postAction('/api/executar/adicionar', payload);
}

async function submitRemover() {
    disableButtons();
    
    const payload = {
        lista_arquivo: document.getElementById('rem-lista').value,
        data_inicio: document.getElementById('rem-data-inicio').value,
        data_fim: document.getElementById('rem-data-fim').value,
    };
    
    const desc = document.getElementById('rem-descricao').value;
    if (desc) payload.descricao_contem = desc;
    
    const cat = document.getElementById('rem-categoria').value;
    if (cat && cat !== '0') payload.categoria_id = parseInt(cat);
    
    const val = document.getElementById('rem-valor').value;
    if (val) payload.valor_exato = parseFloat(val);

    await postAction('/api/executar/remover', payload);
}

async function postAction(url, payload) {
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            appendLog(`Erro na requisição: ${res.statusText}`, 'system-msg');
            enableButtons();
        }
    } catch (e) {
        appendLog(`Erro: ${e.message}`, 'system-msg');
        enableButtons();
    }
}
