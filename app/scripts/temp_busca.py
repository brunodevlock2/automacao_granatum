import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.scripts.gestor_cobrancas import GestorCobrancas
from app.config import config

gestor = GestorCobrancas()

lancamentos = gestor.buscar_lancamentos(
    conta_id=config.CONTA_ID_PADRAO,
    data_inicio="2026-03-01",
    data_fim="2026-03-31",
    busca="Estrela"
)

with open("c:\\automacao_granatum\\app\\scripts\\temp_output.txt", "w", encoding="utf-8") as f:
    f.write(f"Encontrados {len(lancamentos)} lancamentos.\n")
    for i, l in enumerate(lancamentos[:5]):
        f.write(f"{i+1}. ID: {l['id']} - Descricao: '{l.get('descricao')}' - Valor: {l.get('valor')}\n")
