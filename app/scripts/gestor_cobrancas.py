import sys
import os
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.api.api_client import GranatumClient
from app.config import config
import json
import time
from datetime import datetime


class RateLimiter:
    """
    Controla o ritmo de requisicoes para respeitar os limites da API Granatum.
    Limites: 100 req/min, 200 req/5min.
    Estrategia: 0.8s entre chamadas (~75 req/min).
    """
    def __init__(self, intervalo_segundos=0.5):
        self.intervalo = intervalo_segundos
        self.ultimo_request = 0

    def aguardar(self):
        agora = time.time()
        decorrido = agora - self.ultimo_request
        if decorrido < self.intervalo:
            time.sleep(self.intervalo - decorrido)
        self.ultimo_request = time.time()


class GestorCobrancas:
    def __init__(self):
        self.client = GranatumClient()
        self.rate_limiter = RateLimiter()
        self.backup_dir = getattr(config, "BACKUP_DIR", "backups")
        self._categorias_pai = None  # cache do mapa de categorias pai

    # =============================================
    #  Wrappers de API com rate limiting
    # =============================================

    def _api_get(self, endpoint, params=None):
        self.rate_limiter.aguardar()
        return self.client.get(endpoint, params)

    def _api_post(self, endpoint, data):
        self.rate_limiter.aguardar()
        return self.client.post(endpoint, data)

    def _api_delete(self, endpoint, params=None):
        self.rate_limiter.aguardar()
        return self.client.delete(endpoint, params)

    # =============================================
    #  Busca de cobrancas
    # =============================================

    def buscar_cobrancas_por_cliente(self, cliente_id, data_inicio, data_fim, conta_id=None):
        """
        Busca todas as cobrancas de um cliente em um periodo.
        Faz paginacao automatica (API retorna 50 por pagina).
        """
        todas_cobrancas = []
        start = 0

        while True:
            params = {
                "cliente_id": cliente_id,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "start": start,
            }
            if conta_id:
                params["conta_id"] = conta_id

            pagina = self._api_get("cobrancas", params)

            if not pagina or not isinstance(pagina, list):
                break

            todas_cobrancas.extend(pagina)

            if len(pagina) < 50:
                break
            start += 50

        return todas_cobrancas

    def buscar_cobrancas_todos_clientes(self, clientes_ids, data_inicio, data_fim, conta_id=None):
        """Busca cobrancas de multiplos clientes."""
        todas = []
        for cliente_id in clientes_ids:
            print(f"  Buscando cobrancas do cliente {cliente_id}...")
            cobrancas = self.buscar_cobrancas_por_cliente(
                cliente_id, data_inicio, data_fim, conta_id
            )
            print(f"    Encontradas: {len(cobrancas)}")
            todas.extend(cobrancas)

        print(f"Total de cobrancas encontradas: {len(todas)}")
        return todas

    # =============================================
    #  Busca de lancamentos vinculados a cobrancas
    # =============================================

    @staticmethod
    def _parse_lancamento_ids(lancamento_ids_str):
        """
        Converte a string 'lancamento_ids' da API em lista de inteiros.
        Ex: "7835741,7835742" -> [7835741, 7835742]
        """
        if not lancamento_ids_str:
            return []
        return [int(id_str.strip()) for id_str in str(lancamento_ids_str).split(",") if id_str.strip()]

    def buscar_lancamentos_da_cobranca(self, cobranca):
        """
        Para uma cobranca, busca os dados completos de cada lancamento vinculado.
        Lancamentos com 404 (inexistentes) sao ignorados com aviso.
        """
        ids = self._parse_lancamento_ids(cobranca.get("lancamento_ids", ""))
        lancamentos = []

        for lanc_id in ids:
            dados = self._api_get(f"lancamentos/{lanc_id}")
            if dados and isinstance(dados, dict) and dados.get("id"):
                lancamentos.append(dados)
            else:
                print(f"  ⚠ Lancamento {lanc_id} nao encontrado na API (404 ou inexistente). Ignorando e continuando...")

        return lancamentos

    # =============================================
    #  Backup
    # =============================================

    def salvar_backup(self, dados, prefixo="backup_cobranca"):
        """Salva dados em arquivo JSON com timestamp."""
        os.makedirs(self.backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"{prefixo}_{timestamp}.json"
        caminho = os.path.join(self.backup_dir, nome_arquivo)

        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)

        print(f"Backup salvo: {caminho}")
        return caminho

    # =============================================
    #  Transformacao de dados
    # =============================================

    @staticmethod
    def _is_taxa_automatica_boleto(lancamento):
        """
        Identifica lancamentos de taxa automatica gerados pelo Granatum ao criar
        cobranca do tipo boleto ('Taxa - Granatum Pagamentos').
        Esses lancamentos NAO devem ser incluidos na recriacao pois o sistema
        os gera automaticamente.
        """
        return lancamento.get("descricao", "").strip() == "Taxa - Granatum Pagamentos"

    @staticmethod
    def _lancamento_para_item(lancamento):
        """
        Converte um lancamento completo para o formato de 'item' do POST cobranca.
        Campos: descricao, categoria_id, valor (positivo), centro_custo_lucro_id (opcional).
        """
        item = {
            "descricao": lancamento["descricao"],
            "categoria_id": lancamento["categoria_id"],
            "valor": abs(float(lancamento["valor"])),
        }

        ccl_id = lancamento.get("centro_custo_lucro_id")
        if ccl_id and int(ccl_id) != 0:
            item["centro_custo_lucro_id"] = ccl_id

        return item

    def _montar_payload_cobranca(self, cobranca_original, itens_lista, dias_para_emissao=None):
        """
        Monta o payload para POST /cobrancas com base na cobranca original
        e uma lista de itens.
        """
        payload = {
            "conta_id": cobranca_original["conta_id"],
            "cliente_id": cobranca_original["cliente_id"],
            "data_vencimento": cobranca_original["data_vencimento"],
            "tipo_cobranca": config.TIPO_COBRANCA_PADRAO,
            "pagamento_automatico": True,
            "cobrar_juros": False,
            "itens": itens_lista,
        }

        if dias_para_emissao is not None:
            # tipo_emissao 2 = Agendar/Emitir de acordo com dias_para_emissao
            payload["dias_para_emissao"] = dias_para_emissao
            payload["tipo_emissao"] = 2

        return payload

    @staticmethod
    def _lancamento_corresponde_filtro(lancamento, filtro):
        """
        Verifica se um lancamento corresponde aos criterios do filtro (AND logico).
        Criterios possiveis: descricao_contem, categoria_id, valor.
        """
        if not filtro:
            return False

        corresponde = True

        if "descricao_contem" in filtro:
            if filtro["descricao_contem"].lower() not in lancamento.get("descricao", "").lower():
                corresponde = False

        if "categoria_id" in filtro:
            if lancamento.get("categoria_id") != filtro["categoria_id"]:
                corresponde = False

        if "valor" in filtro:
            if abs(float(lancamento.get("valor", 0))) != abs(float(filtro["valor"])):
                corresponde = False

        return corresponde

    # =============================================
    #  Validacao de categorias pai/filha
    # =============================================

    def _carregar_mapa_categorias_pai(self):
        """
        Carrega categorias.json e retorna dict das categorias PAI:
        { cat_id: {"descricao": str, "filhas": [{"id": int, "descricao": str}, ...]} }
        Apenas categorias com filhos aparecem neste mapa.
        """
        if self._categorias_pai is not None:
            return self._categorias_pai

        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../data/categorias.json")
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except FileNotFoundError:
            print("  AVISO: categorias.json nao encontrado. Validacao de categorias desativada.")
            self._categorias_pai = {}
            return self._categorias_pai

        mapa = {}
        for cat in dados:
            filhas = cat.get("categorias_filhas", [])
            if filhas:
                mapa[cat["id"]] = {
                    "descricao": cat["descricao"],
                    "filhas": [{"id": f["id"], "descricao": f["descricao"]} for f in filhas],
                }
        self._categorias_pai = mapa
        return mapa

    def _validar_categorias_itens(self, itens_lista):
        """
        Verifica se algum item usa categoria pai (que tem filhas).
        O usuario pediu para PERMITIR usar qualquer categoria.
        Entao, apenas retornamos a lista original sem bloquear.
        A API que decida se aceita ou nao.
        """
        # Bypass completo solicitado pelo usuario
        return itens_lista

    # =============================================
    #  Acoes na API (delete / create cobranca)
    # =============================================

    def deletar_cobranca(self, cobranca_id, excluir_lancamentos=True):
        """Cancela uma cobranca. Com excluir_lancamentos=True, apaga lancamentos tambem."""
        params = {
            "excluir_lancamentos": str(excluir_lancamentos).lower(),
            "enviar_email_aviso": "false",
        }
        resultado = self._api_delete(f"cobrancas/{cobranca_id}", params)

        if resultado and resultado is not False:
            print(f"    Cobranca {cobranca_id} cancelada com sucesso.")
            return True
        else:
            print(f"    FALHA ao cancelar cobranca {cobranca_id}!")
            return False

    def criar_cobranca(self, payload):
        """Cria uma nova cobranca via POST. Retorna dict ou None."""
        resultado = self._api_post("cobrancas", payload)

        if resultado and isinstance(resultado, dict):
            if resultado.get("id"):
                print(f"    Nova cobranca criada: ID {resultado['id']}, valor R${resultado.get('valor', '?')}")
                return resultado
            elif "errors" in resultado:
                # Retorna o erro para tratamento
                return resultado
        
        print(f"    FALHA ao criar cobranca!")
        return None

    # =============================================
    #  Busca e exclusao de lancamentos avulsos
    # =============================================

    def buscar_lancamentos(self, conta_id, data_inicio, data_fim,
                           busca=None, categoria_id=None, pessoa_id=None):
        """
        Busca lancamentos via GET /lancamentos com paginacao.
        Parametro 'busca' faz busca aproximada na descricao, valor, obs e pessoa.
        Parametro 'categoria_id' filtra por categoria exata na API.
        Parametro 'pessoa_id' filtra por cliente/fornecedor.
        """
        todos = []
        start = 0

        while True:
            params = {
                "conta_id": conta_id,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "start": start,
                "limit": 500,
                "tipo_view": "detail",
            }
            if busca:
                params["busca"] = busca
            if categoria_id:
                params["categoria_id"] = categoria_id
            if pessoa_id:
                params["pessoa_id"] = pessoa_id

            pagina = self._api_get("lancamentos", params)

            if not pagina or not isinstance(pagina, list):
                break

            todos.extend(pagina)

            if len(pagina) < 500:
                break
            start += 500

        return todos

    def deletar_lancamento(self, lancamento_id):
        """Deleta um lancamento via DELETE /lancamentos/:id."""
        resultado = self._api_delete(f"lancamentos/{lancamento_id}")

        if resultado and resultado is not False:
            return True
        else:
            print(f"    FALHA ao deletar lancamento {lancamento_id}!")
            return False

    def deletar_lancamentos_por_descricao(self, conta_id, data_inicio, data_fim, descricao_contem):
        """
        Busca lancamentos por periodo e filtra por descricao (contem).
        Mostra preview, pede confirmacao, e deleta os que correspondem.
        """
        resumo = {"encontrados": 0, "deletados": 0, "falhas": 0}

        # === PASSO 1: Buscar lancamentos ===
        print("\n=== PASSO 1: Buscando lancamentos ===")
        lancamentos = self.buscar_lancamentos(conta_id, data_inicio, data_fim, busca=descricao_contem)
        print(f"  API retornou: {len(lancamentos)} lancamento(s)")

        # Filtro local por descricao (mais preciso que o 'busca' da API)
        filtrados = [
            l for l in lancamentos
            if descricao_contem.lower() in l.get("descricao", "").lower()
        ]
        resumo["encontrados"] = len(filtrados)

        if not filtrados:
            print("  Nenhum lancamento corresponde ao filtro. Nada a fazer.")
            return resumo

        # === PASSO 2: Preview ===
        print(f"\n=== PASSO 2: {len(filtrados)} lancamento(s) encontrado(s) ===")
        print(f"  {'ID':<12} {'Descricao':<40} {'Valor':>10} {'Vencimento':<12}")
        print(f"  {'-'*76}")
        for l in filtrados:
            print(f"  {l['id']:<12} {l.get('descricao','')[:40]:<40} "
                  f"R${l.get('valor','0'):>8} {l.get('data_vencimento','')}")

        # === PASSO 3: Backup ===
        print("\n=== PASSO 3: Salvando backup ===")
        self.salvar_backup(filtrados, "backup_antes_deletar_lancamentos")

        # === Confirmacao ===
        confirmacao = input(f"\nDeletar {len(filtrados)} lancamento(s)? Digite 'SIM': ")
        if confirmacao != "SIM":
            print("Cancelado.")
            return resumo

        # === PASSO 4: Deletar ===
        print("\n=== PASSO 4: Deletando lancamentos ===")
        for l in filtrados:
            lid = l["id"]
            desc = l.get("descricao", "")[:50]
            if self.deletar_lancamento(lid):
                resumo["deletados"] += 1
                print(f"  ✓ {lid} - {desc}")
            else:
                resumo["falhas"] += 1
                print(f"  ✗ {lid} - {desc}")

        # === Resumo ===
        print(f"\n=== RESULTADO FINAL ===")
        print(f"  Encontrados: {resumo['encontrados']}")
        print(f"  Deletados: {resumo['deletados']}")
        print(f"  Falhas: {resumo['falhas']}")

        self.salvar_backup(resumo, "log_resultado_deletar_lancamentos")
        return resumo

    # =============================================
    #  FLUXO PRINCIPAL: ADICIONAR lancamento
    # =============================================

    @staticmethod
    def _ajustar_valor_casal(novo_item, cliente_id, mapa_clientes):
        """
        Se o nome do cliente contem 'casal' (case-insensitive),
        retorna copia do item com valor dobrado. Senao retorna como esta.
        """
        nome = mapa_clientes.get(cliente_id, "")
        if "casal" in nome.lower():
            item_casal = dict(novo_item)
            item_casal["valor"] = round(novo_item["valor"] * 2, 2)
            return item_casal, True
        return dict(novo_item), False

    def adicionar_lancamento_a_cobrancas(self, clientes_ids, data_inicio, data_fim,
                                          novo_item, conta_id=None, mapa_clientes=None,
                                          dias_para_emissao=None):
        """
        Adiciona um lancamento a cobrancas existentes.

        Passos:
        1. Busca cobrancas de todos os clientes no periodo
        2. Busca lancamentos completos de cada cobranca
        3. Salva backup JSON
        4. Validacao de categorias
        5. Deleta cada cobranca (excluir_lancamentos=true)
        6. Recria com itens originais + novo item (valor x2 para Casal)
        """
        if mapa_clientes is None:
            mapa_clientes = {}

        resumo = {
            "processadas": 0, "sucesso": 0, "falhas": 0,
            "clientes_impactados": set(),
            "total_lancamentos": 0,
            "detalhes": [],
        }

        # === PASSO 1: Buscar cobrancas ===
        print("\n=== PASSO 1: Buscando cobrancas ===")
        cobrancas = self.buscar_cobrancas_todos_clientes(
            clientes_ids, data_inicio, data_fim, conta_id
        )

        if not cobrancas:
            print("Nenhuma cobranca encontrada. Nada a fazer.")
            return resumo

        # === PASSO 2: Buscar lancamentos de cada cobranca ===
        print("\n=== PASSO 2: Buscando lancamentos de cada cobranca ===")
        cobrancas_completas = []

        for cob in cobrancas:
            print(f"  Cobranca ID {cob['id']} (cliente {cob['cliente_id']})...")
            lancamentos = self.buscar_lancamentos_da_cobranca(cob)
            cobrancas_completas.append({
                "cobranca": cob,
                "lancamentos": lancamentos,
            })
            print(f"    {len(lancamentos)} lancamentos encontrados.")

        # === PASSO 3: Backup ===
        print("\n=== PASSO 3: Salvando backup ===")
        self.salvar_backup(cobrancas_completas, "backup_antes_adicionar")

        # === CONFIRMACAO ===
        print(f"\nResumo: {len(cobrancas)} cobrancas serao deletadas e recriadas.")
        print(f"Novo item a adicionar: {novo_item.get('descricao')} - R${novo_item.get('valor')}")
        for reg in cobrancas_completas:
            cob = reg["cobranca"]
            qtd = len(reg["lancamentos"])
            print(f"  -> Cobranca {cob['id']} | Cliente {cob['cliente_id']} | "
                  f"R${cob['valor']} | {qtd} lancamento(s)")

        confirmacao = input("\nDigite 'SIM' para prosseguir: ")
        if confirmacao != "SIM":
            print("Operacao cancelada pelo usuario.")
            return resumo

        # === PASSO 4: Ajustar valor Casal + Validar categorias ANTES de deletar ===
        print("\n=== PASSO 4: Preparando itens e validando categorias ===")
        itens_por_cobranca = []
        for registro in cobrancas_completas:
            cob = registro["cobranca"]
            lancs = registro["lancamentos"]
            cliente_id = cob["cliente_id"]

            # Filtrar taxa automatica de boleto (gerada pelo sistema)
            lancs_filtrados = [l for l in lancs if not self._is_taxa_automatica_boleto(l)]
            taxa_removidas = len(lancs) - len(lancs_filtrados)
            if taxa_removidas:
                print(f"  Cobranca {cob['id']}: {taxa_removidas} taxa(s) de boleto filtrada(s) "
                      f"(auto-gerada pelo sistema)")

            itens_originais = [self._lancamento_para_item(l) for l in lancs_filtrados]

            # Ajustar valor para Casal
            item_ajustado, eh_casal = self._ajustar_valor_casal(
                novo_item, cliente_id, mapa_clientes
            )
            if eh_casal:
                nome_cli = mapa_clientes.get(cliente_id, str(cliente_id))
                print(f"  Cliente {nome_cli}: valor x2 -> R${item_ajustado['valor']}")

            itens_finais = itens_originais + [item_ajustado]

            # Validar e corrigir categorias pai
            itens_validados = self._validar_categorias_itens(itens_finais)
            if itens_validados is None:
                print("Operacao cancelada. Nenhuma cobranca foi alterada.")
                return resumo

            itens_por_cobranca.append(itens_validados)

        print("  Categorias OK.")

        # === PASSO 5: Deletar e Recriar cobrancas ===
        print("\n=== PASSO 5: Deletar e Recriar cobrancas ===")
        resumo["ignoradas"] = 0

        for i, registro in enumerate(cobrancas_completas):
            cob = registro["cobranca"]
            lancamentos_originais = registro["lancamentos"]
            itens_finais = itens_por_cobranca[i]
            
            cob_id = cob["id"]
            cliente_id = cob["cliente_id"]

            # --- VERIFICACAO DE DUPLICIDADE (Seguranca) ---
            descricao_alvo = novo_item.get("descricao", "").strip()
            item_duplicado = False
            for l in lancamentos_originais:
                if l.get("descricao", "").strip() == descricao_alvo:
                    item_duplicado = True
                    break
            
            if item_duplicado:
                print(f"\n--- Processando cobranca {cob_id} (cliente {cliente_id}) ---")
                print(f"  ⚠ AVISO: Item '{descricao_alvo}' ja existe nesta cobranca. Pulando.")
                resumo["ignoradas"] += 1
                resumo["detalhes"].append({
                    "cobranca_id_original": cob_id,
                    "cliente_id": cliente_id,
                    "cliente_nome": mapa_clientes.get(cliente_id, str(cliente_id)),
                    "status": "SKIPPED_DUPLICATE",
                    "motivo": f"Item '{descricao_alvo}' ja existe"
                })
                continue
            # -----------------------------------------------

            resumo["processadas"] += 1

            print(f"\n--- Processando cobranca {cob_id} (cliente {cliente_id}) ---")

            # Deletar a cobranca original
            print(f"  Deletando cobranca {cob_id}...")
            if not self.deletar_cobranca(cob_id, excluir_lancamentos=True):
                print(f"  FALHA na exclusao! Pulando recriacao para seguranca.")
                resumo["falhas"] += 1
                resumo["detalhes"].append({
                    "cobranca_id_original": cob_id,
                    "cliente_id": cliente_id,
                    "status": "FALHA_DELETE",
                })
                continue

            # Recriar com todos os itens (ja validados)
            print(f"  Recriando com {len(itens_finais)} itens...")
            
            while True:
                payload = self._montar_payload_cobranca(cob, itens_finais, dias_para_emissao)
                nova_cob = self.criar_cobranca(payload)

                if nova_cob and nova_cob.get("id"):
                    # SUCESSO
                    resumo["sucesso"] += 1
                    resumo["clientes_impactados"].add(cliente_id)
                    resumo["total_lancamentos"] += len(itens_finais)
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cobranca_id_novo": nova_cob["id"],
                        "cliente_id": cliente_id,
                        "cliente_nome": mapa_clientes.get(cliente_id, str(cliente_id)),
                        "status": "OK",
                        "itens_count": len(itens_finais),
                        "valor_novo": str(nova_cob.get("valor", "?")),
                    })
                    break # Sai do loop de retry e vai para proxima cobranca

                elif nova_cob and "errors" in nova_cob:
                    # ERRO DE VALIDACAO (422)
                    errors = nova_cob.get("errors", {})
                    itens_err = errors.get("itens", [])
                    if not itens_err:
                        # Erro nao e nos itens ou formato inesperado
                        print(f"    ERRO DESCONHECIDO na validacao: {errors}")
                        resumo["falhas"] += 1
                        resumo["detalhes"].append({
                            "cobranca_id_original": cob_id,
                            "cliente_id": cliente_id,
                            "status": "FALHA_CREATE_422_GENERICO",
                        })
                        break
                    
                    print(f"\n    ⚠ ERRO DE VALIDACAO DETECTADO PELA API!")
                    print(f"    A API rejeitou alguns itens (provavelmente Categoria Pai).")
                    
                    correcoes_feitas = False
                    
                    for idx, err in enumerate(itens_err):
                        if err is None:
                            continue # Item valido
                            
                        # Identificar o item problematico
                        if idx < len(itens_finais):
                            item_problematico = itens_finais[idx]
                            desc = item_problematico.get("descricao", "?")
                            valor = item_problematico.get("valor", "?")
                            cat_id_atual = item_problematico.get("categoria_id", "?")
                            
                            print(f"\n    >> ITEM PROBLEMATICO (Indice {idx+1}):")
                            print(f"       Descricao: {desc}")
                            print(f"       Valor: R${valor}")
                            print(f"       Categoria ID Atual: {cat_id_atual}")
                            print(f"       Erro: {err}")

                            # === AUTO-CORRECAO: Tentar usar subcategoria ===
                            mapa_pai = self._carregar_mapa_categorias_pai()
                            if int(cat_id_atual) in mapa_pai:
                                info_pai = mapa_pai[int(cat_id_atual)]
                                filhas = info_pai["filhas"]
                                if filhas:
                                    # Usa estrategia: pega sempre a primeira filha
                                    # TODO: Poderia ser mais inteligente (tentar match de nome), mas por ora resolve o block.
                                    nova_filha = filhas[0]
                                    print(f"       🔧 AUTO-RESOLUCAO: A API probiu a categoria pai.")
                                    print(f"       -> Substituindo por subcategoria: '{nova_filha['descricao']}' (ID {nova_filha['id']})")
                                    
                                    item_problematico["categoria_id"] = nova_filha["id"]
                                    correcoes_feitas = True
                                    continue # Item corrigido, vai pro proximo
                            
                            # Se não conseguiu auto-corrigir, pede ajuda ao usuário
                            print("       Opcoes:")
                            print("       1 - Informar novo ID de Categoria (valido e folha)")
                            print("       2 - Remover este item da cobranca")
                            print("       0 - Desistir desta cobranca (vai constar como FALHA)")
                            
                            opcao = input("       Escolha: ").strip()
                            
                            if opcao == "1":
                                novo_cat_id = input("       Digite o novo ID da Categoria: ").strip()
                                if novo_cat_id and novo_cat_id.isdigit():
                                    item_problematico["categoria_id"] = int(novo_cat_id)
                                    print(f"       ✅ Categoria alterada para {novo_cat_id}")
                                    correcoes_feitas = True
                                else:
                                    print("       ID invalido. Item mantido (vai falhar de novo).")
                            
                            elif opcao == "2":
                                del itens_finais[idx]
                                print("       🗑 Item removido da lista.")
                                correcoes_feitas = True
                                # Como alteramos o tamanho da lista, os indices mudam.
                                # O jeito certo seria reiniciar o loop de validacao ou ajustar indices.
                                # Mas aqui, o break abaixo reinicia o 'post', que recebera novo erro ou sucesso.
                                # Porem, se removermos, o array de erro da API nao bate mais com indices.
                                # Como estamos iterando sobre o array de ERRO da resposta anterior, 
                                # e possivel que remover o item bagunce a correcao dos PROXIMOS itens deste mesmo loop?
                                # Sim. Entao vamos parar de iterar erros e tentar reenviar IMEDIATAMENTE.
                                break 
                            
                            elif opcao == "0":
                                print("       Desistindo desta cobranca.")
                                resumo["falhas"] += 1
                                resumo["detalhes"].append({
                                    "cobranca_id_original": cob_id,
                                    "status": "ABORTADO_PELO_USUARIO",
                                })
                                # Precisamos sair do loop while True (retry) e do loop for (erros)
                                # Flag para sair do while
                                break
                    
                    if correcoes_feitas:
                        print("\n    Tentando criar novamente com as correcoes...")
                        continue # Volta ao inicio do while True
                    else:
                        # Usuario desistiu ou nao corrigiu nada
                        break # Sai do while True, conta como falha
                        
                else:
                    # ERRO GENERICO (None)
                    resumo["falhas"] += 1
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cliente_id": cliente_id,
                        "cliente_nome": mapa_clientes.get(cliente_id, str(cliente_id)),
                        "status": "FALHA_CREATE_NET_ERROR",
                    })
                    break

        # === Resumo final ===
        data_execucao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clientes_set = resumo["clientes_impactados"]

        print(f"\n{'=' * 55}")
        print(f"  RESUMO DA EXECUCAO")
        print(f"{'=' * 55}")
        print(f"  Data/Hora:            {data_execucao}")
        print(f"  Cobrancas recriadas:  {resumo['sucesso']}")
        print(f"  Cobrancas com falha:  {resumo['falhas']}")
        print(f"  Cobrancas ignoradas:  {resumo.get('ignoradas', 0)} (Duplicadas)")
        print(f"  Lancamentos totais:   {resumo['total_lancamentos']}")
        print(f"  Clientes impactados:  {len(clientes_set)}")
        print(f"  Item adicionado:      {novo_item.get('descricao')}")
        print(f"  Valor por pessoa:     R${novo_item.get('valor')}")
        print(f"{'=' * 55}")

        # Backup completo do resultado
        backup_completo = {
            "data_execucao": data_execucao,
            "operacao": "ADICIONAR_LANCAMENTO",
            "item_adicionado": novo_item,
            "periodo": {"data_inicio": data_inicio, "data_fim": data_fim},
            "cobrancas_recriadas": resumo["sucesso"],
            "cobrancas_com_falha": resumo["falhas"],
            "total_lancamentos": resumo["total_lancamentos"],
            "clientes_impactados": len(clientes_set),
            "lista_clientes": list(clientes_set),
            "detalhes": resumo["detalhes"],
        }
        self.salvar_backup(backup_completo, "log_resultado_adicionar")
        return resumo

    # =============================================
    #  FLUXO PRINCIPAL: REMOVER lancamento
    # =============================================

    def remover_lancamento_de_cobrancas(self, clientes_ids, data_inicio, data_fim,
                                         filtro_remocao, conta_id=None,
                                         mapa_clientes=None):
        """
        Remove lancamento(s) de cobrancas existentes (versao otimizada).

        Executa todo o fluxo com output minimo (contadores) e exibe
        um relatorio completo apenas no final.

        filtro_remocao: dict com criterios (AND logico):
            descricao_contem: str
            categoria_id: int
            valor: float
        mapa_clientes: dict {cliente_id: nome} para o relatorio.
        """
        if mapa_clientes is None:
            mapa_clientes = {}

        resumo = {
            "processadas": 0, "sucesso": 0, "falhas": 0,
            "sem_recriacao": 0,
            "total_cobrancas": 0, "total_lancamentos": 0,
            "total_removidos": 0, "taxas_filtradas": 0,
            "detalhes": [], "erros_busca_lanc": [],
        }

        # Ativar modo silencioso na API
        self.client.silent = True

        try:
            # === PASSO 1: Buscar cobrancas ===
            print("\n[1/5] Buscando cobrancas...")
            todas_cobrancas = []
            total_clientes = len(clientes_ids)

            for i, cliente_id in enumerate(clientes_ids, 1):
                print(f"\r  Clientes: {i}/{total_clientes}", end="", flush=True)
                cobrancas = self.buscar_cobrancas_por_cliente(
                    cliente_id, data_inicio, data_fim, conta_id
                )
                todas_cobrancas.extend(cobrancas)
            print(f"\r  Clientes: {total_clientes}/{total_clientes} - "
                  f"{len(todas_cobrancas)} cobranca(s) encontrada(s)")

            resumo["total_cobrancas"] = len(todas_cobrancas)

            if not todas_cobrancas:
                print("  Nenhuma cobranca encontrada.")
                return resumo

            # === PASSO 2: Buscar lancamentos de cada cobranca ===
            print("[2/5] Buscando lancamentos...")
            cobrancas_completas = []
            total_cob = len(todas_cobrancas)
            contador_lanc = 0

            for i, cob in enumerate(todas_cobrancas, 1):
                print(f"\r  Cobrancas: {i}/{total_cob} | Lancamentos: {contador_lanc}",
                      end="", flush=True)
                ids = self._parse_lancamento_ids(cob.get("lancamento_ids", ""))
                lancamentos = []
                for lanc_id in ids:
                    dados = self._api_get(f"lancamentos/{lanc_id}")
                    contador_lanc += 1
                    print(f"\r  Cobrancas: {i}/{total_cob} | Lancamentos: {contador_lanc}",
                          end="", flush=True)
                    if dados and isinstance(dados, dict) and dados.get("id"):
                        lancamentos.append(dados)
                    else:
                        resumo["erros_busca_lanc"].append({
                            "lancamento_id": lanc_id,
                            "cobranca_id": cob["id"],
                            "cliente_id": cob["cliente_id"],
                        })
                cobrancas_completas.append({"cobranca": cob, "lancamentos": lancamentos})

            resumo["total_lancamentos"] = contador_lanc
            print(f"\r  Cobrancas: {total_cob}/{total_cob} | "
                  f"Lancamentos: {contador_lanc} encontrado(s)          ")

            # === PASSO 3: Backup ===
            print("[3/5] Salvando backup...")
            self.salvar_backup(cobrancas_completas, "backup_antes_remover")

            # === Contar o que sera removido ===
            total_a_remover = 0
            for registro in cobrancas_completas:
                for lanc in registro["lancamentos"]:
                    if self._lancamento_corresponde_filtro(lanc, filtro_remocao):
                        total_a_remover += 1

            if total_a_remover == 0:
                print("  Nenhum lancamento corresponde ao filtro. Nada a remover.")
                return resumo

            resumo["total_removidos"] = total_a_remover

            # === Confirmacao rapida ===
            print(f"\n  Cobrancas: {len(todas_cobrancas)} | "
                  f"Lancamentos a remover: {total_a_remover}")
            confirmacao = input("  Digite 'SIM' para prosseguir: ")
            if confirmacao != "SIM":
                print("  Cancelado.")
                return resumo

            # === PASSO 4: Preparar itens (validar categorias) ===
            print("[4/5] Validando categorias...")
            itens_por_cobranca = []
            for registro in cobrancas_completas:
                cob = registro["cobranca"]
                lancs = registro["lancamentos"]

                lancs_sem_taxa = [l for l in lancs if not self._is_taxa_automatica_boleto(l)]
                resumo["taxas_filtradas"] += len(lancs) - len(lancs_sem_taxa)

                itens_mantidos = []
                itens_removidos = []
                for lanc in lancs_sem_taxa:
                    if self._lancamento_corresponde_filtro(lanc, filtro_remocao):
                        itens_removidos.append(lanc["descricao"])
                    else:
                        itens_mantidos.append(self._lancamento_para_item(lanc))

                if itens_mantidos:
                    itens_validados = self._validar_categorias_itens(itens_mantidos)
                    if itens_validados is None:
                        print("  Operacao cancelada. Nenhuma cobranca foi alterada.")
                        return resumo
                    itens_mantidos = itens_validados

                itens_por_cobranca.append({
                    "itens_mantidos": itens_mantidos,
                    "itens_removidos": itens_removidos,
                })
            print("  Categorias OK.")

            # === PASSO 5: Deletar e Recriar ===
            print("[5/5] Processando cobrancas...")
            total_proc = len(cobrancas_completas)

            for i, registro in enumerate(cobrancas_completas):
                cob = registro["cobranca"]
                dados_itens = itens_por_cobranca[i]
                itens_mantidos = dados_itens["itens_mantidos"]
                itens_removidos = dados_itens["itens_removidos"]
                resumo["processadas"] += 1

                cob_id = cob["id"]
                cliente_id = cob["cliente_id"]
                nome_cli = mapa_clientes.get(cliente_id, str(cliente_id))

                print(f"\r  Processando: {i + 1}/{total_proc}", end="", flush=True)

                # Deletar original
                params_del = {
                    "excluir_lancamentos": "true",
                    "enviar_email_aviso": "false",
                }
                resultado_del = self._api_delete(f"cobrancas/{cob_id}", params_del)

                if not resultado_del or resultado_del is False:
                    resumo["falhas"] += 1
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cliente_id": cliente_id,
                        "cliente_nome": nome_cli,
                        "status": "FALHA_DELETE",
                        "motivo": "Erro ao cancelar cobranca na API",
                    })
                    continue

                # Se nao sobrou nenhum item, apenas deletar
                if not itens_mantidos:
                    resumo["sucesso"] += 1
                    resumo["sem_recriacao"] += 1
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cliente_id": cliente_id,
                        "cliente_nome": nome_cli,
                        "status": "OK_SEM_RECRIACAO",
                    })
                    continue

                # Recriar sem os itens removidos
                payload = self._montar_payload_cobranca(cob, itens_mantidos)
                nova_cob = self._api_post("cobrancas", payload)

                if nova_cob and isinstance(nova_cob, dict) and nova_cob.get("id"):
                    resumo["sucesso"] += 1
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cobranca_id_novo": nova_cob["id"],
                        "cliente_id": cliente_id,
                        "cliente_nome": nome_cli,
                        "status": "OK",
                        "itens_count": len(itens_mantidos),
                        "valor_novo": str(nova_cob.get("valor", "?")),
                    })
                else:
                    resumo["falhas"] += 1
                    resumo["detalhes"].append({
                        "cobranca_id_original": cob_id,
                        "cliente_id": cliente_id,
                        "cliente_nome": nome_cli,
                        "status": "FALHA_CREATE",
                        "motivo": "Erro ao recriar cobranca na API",
                    })

            print(f"\r  Processando: {total_proc}/{total_proc} - Concluido.          ")

        finally:
            # Sempre restaurar modo verbose
            self.client.silent = False

        # === RELATORIO FINAL ===
        data_execucao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        falhas = [d for d in resumo["detalhes"] if "FALHA" in d.get("status", "")]
        sem_recriacao = [d for d in resumo["detalhes"] if d.get("status") == "OK_SEM_RECRIACAO"]

        print(f"\n{'=' * 60}")
        print(f"  RELATORIO - REMOVER LANCAMENTO DE COBRANCAS")
        print(f"{'=' * 60}")
        print(f"  Data/Hora:                {data_execucao}")
        print(f"  Periodo:                  {data_inicio} a {data_fim}")
        print(f"  Filtro:                   {filtro_remocao}")
        print(f"{'-' * 60}")
        print(f"  BUSCA")
        print(f"    Clientes pesquisados:     {len(clientes_ids)}")
        print(f"    Cobrancas encontradas:    {resumo['total_cobrancas']}")
        print(f"    Lancamentos encontrados:  {resumo['total_lancamentos']}")
        print(f"    Lancamentos a remover:    {resumo['total_removidos']}")
        if resumo["taxas_filtradas"]:
            print(f"    Taxas boleto filtradas:   {resumo['taxas_filtradas']}")
        if resumo["erros_busca_lanc"]:
            print(f"    Erros busca lancamento:   {len(resumo['erros_busca_lanc'])}")
        print(f"{'-' * 60}")
        print(f"  EXECUCAO")
        print(f"    Cobrancas processadas:    {resumo['processadas']}")
        print(f"    Sucesso:                  {resumo['sucesso']}")
        if resumo["sem_recriacao"]:
            print(f"      (sem recriacao):        {resumo['sem_recriacao']}")
        print(f"    Falhas:                   {resumo['falhas']}")

        if falhas:
            print(f"{'-' * 60}")
            print(f"  FALHAS DETALHADAS")
            for i, f in enumerate(falhas, 1):
                print(f"    {i}. Cliente: {f.get('cliente_nome', '?')} (ID {f['cliente_id']})")
                print(f"       Cobranca: {f['cobranca_id_original']}")
                print(f"       Erro: {f['status']} - {f.get('motivo', '?')}")

        if resumo["erros_busca_lanc"]:
            print(f"{'-' * 60}")
            print(f"  LANCAMENTOS NAO ENCONTRADOS")
            for err in resumo["erros_busca_lanc"]:
                nome = mapa_clientes.get(err["cliente_id"], str(err["cliente_id"]))
                print(f"    Lancamento {err['lancamento_id']} | "
                      f"Cobranca {err['cobranca_id']} | Cliente: {nome}")

        print(f"{'=' * 60}")

        # Backup do resultado
        backup_resultado = {
            "data_execucao": data_execucao,
            "operacao": "REMOVER_LANCAMENTO",
            "filtro": filtro_remocao,
            "periodo": {"data_inicio": data_inicio, "data_fim": data_fim},
            "cobrancas_encontradas": resumo["total_cobrancas"],
            "lancamentos_encontrados": resumo["total_lancamentos"],
            "lancamentos_removidos": resumo["total_removidos"],
            "processadas": resumo["processadas"],
            "sucesso": resumo["sucesso"],
            "falhas": resumo["falhas"],
            "erros_busca_lancamento": resumo["erros_busca_lanc"],
            "detalhes": resumo["detalhes"],
        }
        self.salvar_backup(backup_resultado, "log_resultado_remover")
        return resumo
