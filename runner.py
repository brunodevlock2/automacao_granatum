from api_client import GranatumClient
import config
import time

class AutomacaoRunner:
    def __init__(self):
        self.client = GranatumClient()
        self.itens_carregados = [] # Aqui fica nossa "lista de trabalho" (O Contexto)

    # --- PASSO 1: CARREGAR DADOS (GET) ---
    def passo_listar_lancamentos(self, data_inicio, data_fim, conta_id):
        """Busca lançamentos na API e guarda na memória do Runner."""
        print(f"\n--- PASSO 1: BUSCANDO DADOS ---")
        params = {
            "data_inicio": data_inicio, 
            "data_fim": data_fim, 
            "conta_id": conta_id
        }
        # O resultado do GET fica salvo em self.itens_carregados
        self.itens_carregados = self.client.get("lancamentos", params)
        print(f"📦 Itens carregados na memória: {len(self.itens_carregados)}")
        return self # Retorna a si mesmo para permitir encadeamento

    # --- PASSO 2: FILTRAR DADOS (Python) ---
    def passo_filtrar(self, categoria_id=None, centro_custo_id=None, descricao_contem=None):
        """Filtra a lista que já está na memória."""
        print(f"\n--- PASSO 2: APLICANDO FILTROS ---")
        lista_filtrada = []
        
        for item in self.itens_carregados:
            aprovado = True
            
            # Filtro 1: Categoria
            if categoria_id and item.get('categoria_id') != categoria_id:
                aprovado = False
            
            # Filtro 2: Centro de Custo
            if centro_custo_id and item.get('centro_custo_lucro_id') != centro_custo_id:
                aprovado = False

            # Filtro 3: Descrição (Texto aproximado)
            if descricao_contem:
                desc_item = item.get('descricao', '').lower()
                if descricao_contem.lower() not in desc_item:
                    aprovado = False
            
            if aprovado:
                lista_filtrada.append(item)
        
        self.itens_carregados = lista_filtrada
        print(f"🔍 Após filtros, restaram: {len(self.itens_carregados)} itens.")
        
        # Mostra prévia
        for item in self.itens_carregados[:5]:
            print(f"   -> ID {item['id']} | {item['descricao']} | R$ {item['valor']}")
        if len(self.itens_carregados) > 5: print("   ... (e mais)")
            
        return self

    # --- PASSO 3: EXECUTAR AÇÃO (DELETE) ---
    def passo_excluir_em_massa(self):
        """Pega a lista filtrada e manda bala no DELETE um por um."""
        if not self.itens_carregados:
            print("🚫 Lista vazia. Nada a excluir.")
            return

        print(f"\n--- PASSO 3: EXCLUSÃO EM MASSA ---")
        resp = input(f"⚠️  Tem certeza que quer EXCLUIR {len(self.itens_carregados)} itens? (Digite SIM): ")
        if resp != "SIM": return

        sucessos = 0
        for item in self.itens_carregados:
            # Monta o endpoint específico: lancamentos/12345
            endpoint = f"lancamentos/{item['id']}"
            
            print(f"🗑️ Deletando ID {item['id']}...", end="")
            if self.client.delete(endpoint):
                print(" Feito.")
                sucessos += 1
            else:
                print(" Falhou.")
            
            time.sleep(0.5) # Respeita o servidor

        print(f"🏁 Fim. {sucessos} itens excluídos.")

    # --- EXTRA: PASSO CRIAR (POST) ---
    def passo_criar_para_clientes(self, lista_clientes_ids, dados_modelo):
        """
        Exemplo de Runner para criação: 
        Recebe uma lista de IDs de clientes e cria o mesmo lançamento para todos.
        """
        print(f"\n--- PASSO CRIAR: LANÇAMENTO EM LOTE ---")
        for pessoa_id in lista_clientes_ids:
            # Copia o modelo e insere o cliente atual
            novo_lancamento = dados_modelo.copy()
            novo_lancamento['pessoa_id'] = pessoa_id
            
            print(f"📝 Criando para cliente {pessoa_id}...", end="")
            resultado = self.client.post("lancamentos", novo_lancamento)
            
            if resultado:
                print(f" ID Criado: {resultado.get('id')}")
            
            time.sleep(1)


# ==========================================
#   ZONA DE EXECUÇÃO (Onde você manda)
# ==========================================
if __name__ == "__main__":
    runner = AutomacaoRunner()

    # --- CENÁRIO 1: BUSCAR, FILTRAR E DELETAR ---
    # Aqui fazemos a sequência exata que você pediu:
    (runner
        .passo_listar_lancamentos(
            data_inicio="2026-02-01", 
            data_fim="2026-02-28", 
            conta_id=config.CONTA_ID_PADRAO
        )
        .passo_filtrar(
            centro_custo_id=config.CENTRO_CUSTO_ID_PADRAO,
            # categoria_id=config.CATEGORIA_ID_PADRAO, # (Opcional: descomente se quiser filtrar)
            descricao_contem="Taxa"                    # (Opcional: só apaga se tiver 'Taxa' no nome)
        )
        .passo_excluir_em_massa()
    )

    # --- CENÁRIO 2: CRIAR COBRANÇA PARA VÁRIOS CLIENTES (Exemplo) ---
    # Se quiser rodar criação, descomente as linhas abaixo:
    
    # modelo_cobranca = {
    #     "descricao": "Mensalidade Março",
    #     "categoria_id": config.CATEGORIA_ID_PADRAO,
    #     "conta_id": config.CONTA_ID_PADRAO,
    #     "valor": 50.00,
    #     "data_vencimento": "2026-03-10"
    # }
    # lista_clientes = [3146650, 3146651] # IDs que pegamos antes
    
    # runner.passo_criar_para_clientes(lista_clientes, modelo_cobranca)