import sys
import os
import asyncio
import threading
import json
from contextlib import redirect_stdout
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.scripts.gestor_cobrancas import GestorCobrancas
from app.scripts.analise_dados import AnalisadorGranatum
from app.api.api_client import GranatumClient
from app.config import config
from app.scripts.main_cobrancas import (
    listar_arquivos_clientes, 
    carregar_lista_clientes, 
    carregar_categorias_flat,
    carregar_centros_custo_flat
)

app = FastAPI(title="Gestor de Cobranças Granatum")

# Setup static files and templates (supporting PyInstaller packaging)
if getattr(sys, 'frozen', False):
    # Executável do PyInstaller
    base_dir = sys._MEIPASS
else:
    # Código-fonte Python
    base_dir = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(base_dir, "static")
templates_dir = os.path.join(base_dir, "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# --- WebSocket Manager for Real-time Logs ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except:
            pass

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# --- Custom Stdout Redirector to broadcast prints to WebSockets ---
class WebSocketLogger:
    def __init__(self, loop):
        self.loop = loop
        self.terminal = sys.stdout

    def write(self, message):
        self.terminal.write(message)
        if message.strip():
            # Broadcast to websockets
            asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps({"type": "log", "message": message.strip()})), self.loop)

    def flush(self):
        self.terminal.flush()

# --- Helper to run background tasks with intercepted stdout ---
def run_with_logging(func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        
    logger = WebSocketLogger(loop)
    
    def target():
        with redirect_stdout(logger):
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"ERRO: {e}")
            finally:
                asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps({"type": "done", "message": "Tarefa concluída."})), loop)

    thread = threading.Thread(target=target)
    thread.start()


# --- Models ---
class AdicionarRequest(BaseModel):
    lista_arquivo: str
    data_inicio: str
    data_fim: str
    descricao: str
    categoria_id: int
    valor: float
    centro_custo_id: Optional[int] = None
    dias_para_emissao: Optional[int] = None

class RemoverRequest(BaseModel):
    lista_arquivo: str
    data_inicio: str
    data_fim: str
    descricao_contem: Optional[str] = None
    categoria_id: Optional[int] = None
    valor_exato: Optional[float] = None

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/opcoes")
async def get_opcoes():
    """Retorna os dados necessários para preencher os selects no frontend."""
    arquivos = listar_arquivos_clientes()
    categorias = carregar_categorias_flat()
    centros_custo = carregar_centros_custo_flat()
    
    return {
        "listas_clientes": arquivos,
        "categorias": categorias,
        "centros_custo": centros_custo
    }

@app.post("/api/executar/adicionar")
async def executar_adicionar(req: AdicionarRequest):
    ids, dados = carregar_lista_clientes(req.lista_arquivo)
    mapa_clientes = {c["id"]: c.get("nome", str(c["id"])) for c in dados}

    novo_item = {
        "descricao": req.descricao,
        "categoria_id": req.categoria_id,
        "valor": req.valor,
    }
    if req.centro_custo_id and req.centro_custo_id != 0:
        novo_item["centro_custo_lucro_id"] = req.centro_custo_id

    gestor = GestorCobrancas()

    def task():
        gestor.adicionar_lancamento_a_cobrancas(
            clientes_ids=ids,
            data_inicio=req.data_inicio,
            data_fim=req.data_fim,
            novo_item=novo_item,
            conta_id=config.CONTA_ID_PADRAO,
            mapa_clientes=mapa_clientes,
            dias_para_emissao=req.dias_para_emissao,
        )

    run_with_logging(task)
    return {"status": "started"}

@app.post("/api/executar/remover")
async def executar_remover(req: RemoverRequest):
    ids, dados = carregar_lista_clientes(req.lista_arquivo)
    mapa_clientes = {c["id"]: c.get("nome", str(c["id"])) for c in dados}

    filtro = {}
    if req.descricao_contem:
        filtro["descricao_contem"] = req.descricao_contem
    if req.categoria_id:
        filtro["categoria_id"] = req.categoria_id
    if req.valor_exato:
        filtro["valor"] = req.valor_exato

    gestor = GestorCobrancas()

    def task():
        gestor.remover_lancamento_de_cobrancas(
            clientes_ids=ids,
            data_inicio=req.data_inicio,
            data_fim=req.data_fim,
            filtro_remocao=filtro,
            conta_id=config.CONTA_ID_PADRAO,
            mapa_clientes=mapa_clientes,
        )

    run_with_logging(task)
    return {"status": "started"}

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import time
    
    def open_browser():
        time.sleep(1.5)  # Aguarda uvicorn iniciar
        webbrowser.open("http://localhost:8000")

    # Inicia a thread para abrir o navegador
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Roda o servidor
    uvicorn.run(app, host="0.0.0.0", port=8000)
