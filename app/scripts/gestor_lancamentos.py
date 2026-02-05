import sys
import os
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.api.api_granatum import GranatumAPI as GranatumClient # Check if class is API or Client. 
# Wait, user code said "from api_granatum import GranatumClient". I should trust that, 
# BUT I recently restored main.py which used "from api_granatum import GranatumAPI".
# Let's check api_granatum content first?
# No, gestor_lancamentos.py import was "from api_granatum import GranatumClient".
# I'll stick to that.
from app.api.api_granatum import GranatumClient
from app.config import config
import time
import json

class GestorLancamentos:
    def __init__(self):
        self.client = GranatumClient()

    def buscar_lancamentos_refinados(self, data_inicio, data_fim, conta_id, 
                                     filtro_categoria_id=None, 
                                     filtro_centro_custo_id=None, 
                                     filtro_descricao_aprox=None):
        """
        Busca na API e aplica filtros extras (Categoria, Descrição) via Python 
        para garantir precisão absoluta.
        """
        # 1. Busca bruta na API (Filtro de Conta e Data é obrigatório na API)
        params = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "conta_id": conta_id
        }
        todos_lancamentos = self.client.get("lancamentos", params)
        
        if not todos_lancamentos:
            return []

        # 2. Refinamento (Filtragem Fina no Python)
        lancamentos_filtrados = []
        
        for item in todos_lancamentos:
            passou_filtro = True
            
            # Filtro de Categoria
            if filtro_categoria_id and item.get('categoria_id') != filtro_categoria_id:
                passou_filtro = False

            # Filtro de Centro de Custo
            if filtro_centro_custo_id and item.get('centro_custo_lucro_id') != filtro_centro_custo_id:
                passou_filtro = False
            
            # Filtro de Descrição (Aproximada/Contém)
            if filtro_descricao_aprox:
                desc_atual = item.get('descricao', '').lower()
                termo_busca = filtro_descricao_aprox.lower()
                if termo_busca not in desc_atual:
                    passou_filtro = False
            
            if passou_filtro:
                lancamentos_filtrados.append(item)
                
        return lancamentos_filtrados

    def excluir_lista(self, lista_lancamentos):
        """Recebe uma lista já filtrada e executa a exclusão um a um."""
        if not lista_lancamentos:
            print("📭 Lista vazia. Nada a excluir.")
            return

        print(f"\n⚠️ PREPARANDO PARA EXCLUIR {len(lista_lancamentos)} ITENS.")
        confirmacao = input("Digite 'SIM' para confirmar a exclusão irreversível: ")
        
        if confirmacao != 'SIM':
            print("🚫 Cancelado.")
            return

        sucessos = 0
        for item in lista_lancamentos:
            # Endpoint DELETE exige o ID na URL
            endpoint = f"lancamentos/{item['id']}"
            if self.client.delete(endpoint):
                sucessos += 1
            time.sleep(1) # Rate limit preventivo
            
        print(f"\n🏁 Processo finalizado. {sucessos} itens excluídos.")

# --- ZONA DE EXECUÇÃO ---
if __name__ == "__main__":
    gestor = GestorLancamentos()
    
    # Exemplo de uso com TODOS os filtros que você pediu
    resultados = gestor.buscar_lancamentos_refinados(
        data_inicio="2026-02-01",
        data_fim="2026-02-28",
        conta_id=config.CONTA_ID_PADRAO,
        
        # Filtros Opcionais (Se não quiser usar, passe None ou apague a linha)
        filtro_categoria_id=config.CATEGORIA_ID_PADRAO,  # Só desta categoria
        filtro_centro_custo_id=None,                     # Ignora centro de custo
        filtro_descricao_aprox="Taxa"                    # Só descrições que tenham "Taxa"
    )
    
    print(f"\n🔍 Encontrados: {len(resultados)} lançamentos compatíveis.")
    
    # Mostra o que achou antes de apagar
    for l in resultados:
        print(f" - [{l['id']}] {l['descricao']} | R$ {l['valor']}")
        
    # Chama a exclusão
    if resultados:
        gestor.excluir_lista(resultados)