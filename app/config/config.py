# config.py
# Este arquivo serve para guardar configurações fixas.
# Assim, não misturamos dados sensíveis com a lógica do programa.

# Seu Token de Acesso (Pegue lá nas configurações do Granatum)
TOKEN_GRANATUM = "9e80e43831ea8f8a00e7b1f0e7ae60331161e51d52c7830f592a8425a5730f99"

# IDs Fixos (Esses números você pega na URL do Granatum ou nos testes anteriores)
# Exemplo: Se a URL da conta é granatum.com.br/financeiro/contas/12345, o ID é 115126 (baseado no seu histórico)
CONTA_ID_PADRAO = 115126  

# Categoria "Taxa de Preparo Divino Manto" (ID que vimos no seu JSON)
CATEGORIA_ID_PADRAO = 2401581

# Centro de Custo (ID que vimos no seu JSON)
CENTRO_CUSTO_ID_PADRAO = 308906

# URLs da API (Não precisa mudar)
URL_BASE = "https://api.granatum.com.br/v1"

# --- Configurações de Cobranças ---

import sys
import os

# Base dir calculation
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Se existir um config.json no BASE_DIR (ao lado do executavel), sobrescreve as variaveis!
config_json_path = os.path.join(BASE_DIR, "config.json")
if os.path.exists(config_json_path):
    try:
        import json
        with open(config_json_path, "r", encoding="utf-8") as f:
            overrides = json.load(f)
            if "TOKEN_GRANATUM" in overrides: TOKEN_GRANATUM = overrides["TOKEN_GRANATUM"]
            if "CONTA_ID_PADRAO" in overrides: CONTA_ID_PADRAO = int(overrides["CONTA_ID_PADRAO"])
            if "CATEGORIA_ID_PADRAO" in overrides: CATEGORIA_ID_PADRAO = int(overrides["CATEGORIA_ID_PADRAO"])
            if "CENTRO_CUSTO_ID_PADRAO" in overrides: CENTRO_CUSTO_ID_PADRAO = int(overrides["CENTRO_CUSTO_ID_PADRAO"])
            if "TIPO_COBRANCA_PADRAO" in overrides: TIPO_COBRANCA_PADRAO = overrides["TIPO_COBRANCA_PADRAO"]
    except Exception as e:
        print(f"Erro ao ler config.json: {e}")

# Diretório com arquivos JSON de listas de clientes
CLIENTES_DIR = os.path.join(BASE_DIR, "data", "clientes")

# Tipo de cobrança padrão (opções: 'boleto', 'cartao_credito', 'pix')
TIPO_COBRANCA_PADRAO = "boleto"

# Diretório para backups
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")

# Arquivos JSON Data
CATEGORIAS_JSON_PATH = os.path.join(BASE_DIR, "data", "categorias.json")
CENTROS_CUSTO_JSON_PATH = os.path.join(BASE_DIR, "data", "centros_de_custo.json")