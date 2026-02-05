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

import os
# Base dir is project root (c:\automacao_granatum)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Diretório com arquivos JSON de listas de clientes
CLIENTES_DIR = os.path.join(BASE_DIR, "data", "clientes")

# Tipo de cobrança padrão (opções: 'boleto', 'cartao_credito', 'pix')
TIPO_COBRANCA_PADRAO = "boleto"

# Diretório para backups
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")

# Arquivos JSON Data
CATEGORIAS_JSON_PATH = os.path.join(BASE_DIR, "data", "categorias.json")
CENTROS_CUSTO_JSON_PATH = os.path.join(BASE_DIR, "data", "centros_de_custo.json")