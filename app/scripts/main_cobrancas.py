from gestor_cobrancas import GestorCobrancas
from api_client import GranatumClient
from analise_dados import AnalisadorGranatum
import config
import json
import os
from datetime import datetime, timedelta


# =============================================
#  Gerenciamento de listas de clientes (JSON)
# =============================================

def listar_arquivos_clientes():
    """Retorna lista de arquivos JSON encontrados na pasta de clientes."""
    pasta = getattr(config, "CLIENTES_DIR", "clientes")
    if not os.path.isdir(pasta):
        print(f"Pasta '{pasta}' nao encontrada. Crie-a e adicione arquivos JSON.")
        return []

    arquivos = [f for f in os.listdir(pasta) if f.endswith(".json")]
    arquivos.sort()
    return arquivos


def carregar_lista_clientes(nome_arquivo):
    """
    Carrega um JSON de clientes. Formato esperado:
    [
      {"nome": "Fulano", "id": 123},
      {"nome": "Ciclano", "id": 456}
    ]
    Retorna: (lista_ids, lista_completa)
    """
    pasta = getattr(config, "CLIENTES_DIR", "clientes")
    caminho = os.path.join(pasta, nome_arquivo)

    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    ids = [c["id"] for c in dados]
    return ids, dados


def escolher_lista_clientes():
    """
    Mostra as listas disponiveis e deixa o usuario escolher.
    Retorna: (lista_ids, nome_arquivo) ou (None, None) se cancelar.
    """
    arquivos = listar_arquivos_clientes()

    if not arquivos:
        print("Nenhum arquivo JSON encontrado na pasta de clientes.")
        return None, None

    print("\n--- LISTAS DE CLIENTES DISPONIVEIS ---")
    for i, arq in enumerate(arquivos, 1):
        # Carrega pra mostrar quantos clientes tem
        try:
            ids, dados = carregar_lista_clientes(arq)
            print(f"  {i} - {arq} ({len(ids)} clientes)")
        except Exception as e:
            print(f"  {i} - {arq} (ERRO ao ler: {e})")

    print(f"  0 - Cancelar")

    escolha = input("\nEscolha a lista: ").strip()
    if escolha == "0" or not escolha:
        return None, None

    try:
        idx = int(escolha) - 1
        if 0 <= idx < len(arquivos):
            nome = arquivos[idx]
            ids, dados = carregar_lista_clientes(nome)
            print(f"\nLista selecionada: {nome} ({len(ids)} clientes)")
            # Mostra primeiros 5 como preview
            for c in dados[:5]:
                print(f"  -> {c.get('nome', '?')} (ID {c['id']})")
            if len(dados) > 5:
                print(f"  ... e mais {len(dados) - 5}")
            return ids, nome
        else:
            print("Opcao invalida.")
            return None, None
    except (ValueError, KeyError, Exception) as e:
        print(f"Erro: {e}")
        return None, None


# =============================================
#  Busca de categorias por palavra-chave
# =============================================

def carregar_categorias_flat():
    """
    Carrega categorias.json e retorna lista flat apenas de categorias folha
    (sem filhos), que sao as unicas aceitas pela API.
    """
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categorias.json")
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    categorias = []
    for cat in dados:
        filhas = cat.get("categorias_filhas", [])
        if not filhas:
            categorias.append({"id": cat["id"], "descricao": cat["descricao"]})
        else:
            for filha in filhas:
                categorias.append({
                    "id": filha["id"],
                    "descricao": f"{cat['descricao']} > {filha['descricao']}",
                })

    categorias.sort(key=lambda c: c["descricao"])
    return categorias


def escolher_categoria(prompt="Categoria", obrigatoria=True):
    """
    Busca categoria por palavra-chave no categorias.json.
    Retorna o ID da categoria escolhida ou None se cancelar.
    Aceita tambem ID numerico direto.
    """
    categorias = carregar_categorias_flat()

    while True:
        termo = input(f"  {prompt} (palavra-chave ou ID): ").strip()

        if not termo:
            if obrigatoria:
                print("    Categoria obrigatoria. Tente novamente.")
                continue
            return None

        # Aceita ID numerico direto
        if termo.isdigit():
            cat_id = int(termo)
            match = next((c for c in categorias if c["id"] == cat_id), None)
            if match:
                print(f"    -> {match['descricao']} (ID {match['id']})")
                return match["id"]
            else:
                print(f"    ID {cat_id} nao encontrado nas categorias folha.")
                continue

        # Busca por palavra-chave na descricao
        resultados = [
            c for c in categorias
            if termo.lower() in c["descricao"].lower()
        ]

        if not resultados:
            print(f"    Nenhuma categoria com '{termo}'. Tente outra palavra.")
            continue

        if len(resultados) == 1:
            cat = resultados[0]
            print(f"    -> {cat['descricao']} (ID {cat['id']})")
            return cat["id"]

        print(f"\n    {len(resultados)} categorias encontradas:")
        for i, cat in enumerate(resultados, 1):
            print(f"      {i} - {cat['descricao']} (ID {cat['id']})")
        print(f"      0 - Buscar novamente")

        escolha = input("    Escolha: ").strip()
        if escolha == "0" or not escolha:
            continue

        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(resultados):
                cat = resultados[idx]
                print(f"    -> {cat['descricao']} (ID {cat['id']})")
                return cat["id"]
        except ValueError:
            pass
        print("    Opcao invalida.")


# =============================================
#  Busca de centros de custo por palavra-chave
# =============================================

def _flatten_centros_custo(itens, prefixo=""):
    """Achata a arvore de centros de custo recursivamente, retornando apenas folhas."""
    resultado = []
    for item in itens:
        filhos = item.get("centros_custo_lucro_filhos", [])
        desc = item["descricao"]
        desc_completa = f"{prefixo} > {desc}" if prefixo else desc

        if not filhos:
            resultado.append({"id": item["id"], "descricao": desc_completa})
        else:
            resultado.extend(_flatten_centros_custo(filhos, desc_completa))

    return resultado


def carregar_centros_custo_flat():
    """
    Carrega centros_de_custo.json e retorna lista flat apenas de folhas.
    """
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "centros_de_custo.json")
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    centros = _flatten_centros_custo(dados)
    centros.sort(key=lambda c: c["descricao"])
    return centros


def escolher_centro_custo(prompt="Centro de Custo", obrigatoria=False):
    """
    Busca centro de custo por palavra-chave no centros_de_custo.json.
    Retorna o ID escolhido, ou None se pular/cancelar.
    Aceita tambem ID numerico direto.
    """
    centros = carregar_centros_custo_flat()

    while True:
        termo = input(f"  {prompt} (palavra-chave, ID, ou Enter=pular, 0=nenhum): ").strip()

        if not termo:
            if obrigatoria:
                print("    Centro de custo obrigatorio. Tente novamente.")
                continue
            return None

        if termo == "0":
            return 0

        # Aceita ID numerico direto
        if termo.isdigit():
            cc_id = int(termo)
            match = next((c for c in centros if c["id"] == cc_id), None)
            if match:
                print(f"    -> {match['descricao']} (ID {match['id']})")
                return match["id"]
            else:
                print(f"    ID {cc_id} nao encontrado nos centros de custo folha.")
                continue

        # Busca por palavra-chave
        resultados = [
            c for c in centros
            if termo.lower() in c["descricao"].lower()
        ]

        if not resultados:
            print(f"    Nenhum centro de custo com '{termo}'. Tente outra palavra.")
            continue

        if len(resultados) == 1:
            cc = resultados[0]
            print(f"    -> {cc['descricao']} (ID {cc['id']})")
            return cc["id"]

        print(f"\n    {len(resultados)} centros de custo encontrados:")
        for i, cc in enumerate(resultados, 1):
            print(f"      {i} - {cc['descricao']} (ID {cc['id']})")
        print(f"      0 - Buscar novamente")

        escolha = input("    Escolha: ").strip()
        if escolha == "0" or not escolha:
            continue

        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(resultados):
                cc = resultados[idx]
                print(f"    -> {cc['descricao']} (ID {cc['id']})")
                return cc["id"]
        except ValueError:
            pass
        print("    Opcao invalida.")


def escolher_multiplas_categorias():
    """
    Exibe uma lista de todas as categorias e permite ao usuário selecionar várias.
    Retorna uma lista de descrições de categorias selecionadas.
    """
    categorias = carregar_categorias_flat()
    if not categorias:
        print("Nenhuma categoria encontrada.")
        return []

    print("\n--- SELECIONE UMA OU MAIS CATEGORIAS ---")
    for i, cat in enumerate(categorias, 1):
        print(f"  {i} - {cat['descricao']}")
    print("  0 - Cancelar")

    while True:
        escolha_str = input("\nDigite os números das categorias, separados por vírgula (ex: 1, 5, 8): ").strip()
        if escolha_str == '0':
            return []
        
        try:
            indices = [int(i.strip()) - 1 for i in escolha_str.split(',')]
            
            selecionadas = []
            for idx in indices:
                if 0 <= idx < len(categorias):
                    selecionadas.append(categorias[idx]['descricao'])
                else:
                    raise ValueError(f"Número {idx + 1} está fora do intervalo válido.")
            
            print("\nCategorias selecionadas:")
            for nome in selecionadas:
                print(f"  -> {nome}")
            return selecionadas
        except (ValueError, IndexError) as e:
            print(f"Seleção inválida. Por favor, digite números da lista, separados por vírgula. Erro: {e}")
            continue


def escolher_multiplos_centros_custo():
    """
    Exibe uma lista de todos os centros de custo e permite ao usuário selecionar vários.
    Retorna uma lista de descrições de centros de custo selecionados.
    """
    centros = carregar_centros_custo_flat()
    if not centros:
        print("Nenhum centro de custo encontrado.")
        return []

    print("\n--- SELECIONE UM OU MAIS CENTROS DE CUSTO ---")
    for i, cc in enumerate(centros, 1):
        print(f"  {i} - {cc['descricao']}")
    print("  0 - Cancelar")

    while True:
        escolha_str = input("\nDigite os números dos centros de custo, separados por vírgula (ex: 1, 5, 8): ").strip()
        if escolha_str == '0':
            return []
        
        try:
            indices = [int(i.strip()) - 1 for i in escolha_str.split(',')]
            
            selecionados = []
            for idx in indices:
                if 0 <= idx < len(centros):
                    selecionados.append(centros[idx]['descricao'])
                else:
                    raise ValueError(f"Número {idx + 1} está fora do intervalo válido.")
            
            print("\nCentros de custo selecionados:")
            for nome in selecionados:
                print(f"  -> {nome}")
            return selecionados
        except (ValueError, IndexError) as e:
            print(f"Seleção inválida. Por favor, digite números da lista, separados por vírgula. Erro: {e}")
            continue

# =============================================
#  Menu principal
# =============================================

def menu_principal():
    print()
    print("=" * 50)
    print("  GESTOR DE COBRANCAS - Granatum")
    print("=" * 50)
    print()
    print(f"  Conta padrao: {config.CONTA_ID_PADRAO}")
    print(f"  Tipo cobranca: {config.TIPO_COBRANCA_PADRAO}")
    print(f"  Pasta de listas: {getattr(config, 'CLIENTES_DIR', 'clientes')}/")
    print()
    print("  1 - ADICIONAR lancamento a cobrancas existentes")
    print("  2 - REMOVER lancamento de cobrancas existentes")
    print("  3 - LISTAR cobrancas (apenas visualizar)")
    print("  4 - DELETAR lancamentos por descricao")
    print("  5 - LISTAR lancamentos (busca geral)")
    print("  6 - LISTAR lancamentos por lista de clientes")
    print("-" * 50)
    print("  7 - ANÁLISE DE DADOS E RELATÓRIOS")
    print("-" * 50)
    print("  0 - Sair")
    print()
    return input("Escolha: ").strip()


# =============================================
#  Funcoes de execucao
# =============================================

def executar_adicionar(gestor):
    """Coleta parametros e executa o fluxo de adicao."""
    print("\n--- ADICIONAR LANCAMENTO A COBRANCAS ---")

    clientes_ids, nome_lista = escolher_lista_clientes()
    if not clientes_ids:
        return

    # Carregar nomes dos clientes para logica Casal
    _, clientes_dados = carregar_lista_clientes(nome_lista)
    mapa_clientes = {c["id"]: c.get("nome", str(c["id"])) for c in clientes_dados}

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    print("\nDados do novo lancamento a adicionar:")
    descricao = input("  Descricao: ").strip()
    if not descricao:
        print("Descricao obrigatoria. Cancelando.")
        return

    categoria_id = escolher_categoria("Categoria do lancamento")
    if not categoria_id:
        print("Categoria obrigatoria. Cancelando.")
        return

    valor_input = input("  Valor (positivo, por pessoa): ").strip()
    if not valor_input:
        print("Valor obrigatorio. Cancelando.")
        return
    valor = float(valor_input)

    ccl_id = escolher_centro_custo("Centro de Custo")

    novo_item = {
        "descricao": descricao,
        "categoria_id": categoria_id,
        "valor": valor,
    }

    if ccl_id and ccl_id != 0:
        novo_item["centro_custo_lucro_id"] = ccl_id

    print(f"\nLista: {nome_lista}")
    print(f"Novo item: {novo_item}")
    print(f"  * Clientes com 'Casal' no nome terao valor x2 (R${valor} -> R${valor * 2})")

    gestor.adicionar_lancamento_a_cobrancas(
        clientes_ids=clientes_ids,
        data_inicio=data_inicio,
        data_fim=data_fim,
        novo_item=novo_item,
        conta_id=config.CONTA_ID_PADRAO,
        mapa_clientes=mapa_clientes,
    )


def executar_remover(gestor):
    """Coleta parametros e executa o fluxo de remocao."""
    print("\n--- REMOVER LANCAMENTO DE COBRANCAS ---")

    clientes_ids, nome_lista = escolher_lista_clientes()
    if not clientes_ids:
        return

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    print("\nCriterios para identificar o lancamento a remover:")
    print("  (Preencha pelo menos 1. Deixe em branco para ignorar o criterio)")

    filtro = {}

    desc = input("  Descricao contem: ").strip()
    if desc:
        filtro["descricao_contem"] = desc

    usar_cat = input("  Filtrar por categoria? (s/N): ").strip().lower()
    if usar_cat == "s":
        cat_id = escolher_categoria("Categoria para filtro", obrigatoria=False)
        if cat_id:
            filtro["categoria_id"] = cat_id

    val = input("  Valor exato (opcional): ").strip()
    if val:
        filtro["valor"] = float(val)

    if not filtro:
        print("Nenhum criterio informado. Cancelando.")
        return

    # Carregar mapa de nomes para o relatorio
    try:
        _, clientes_dados = carregar_lista_clientes(nome_lista)
        mapa_clientes = {c["id"]: c["nome"] for c in clientes_dados}
    except Exception:
        mapa_clientes = {}

    print(f"\nLista: {nome_lista}")
    print(f"Filtro de remocao: {filtro}")

    gestor.remover_lancamento_de_cobrancas(
        clientes_ids=clientes_ids,
        data_inicio=data_inicio,
        data_fim=data_fim,
        filtro_remocao=filtro,
        conta_id=config.CONTA_ID_PADRAO,
        mapa_clientes=mapa_clientes,
    )


def executar_listar(gestor):
    """Lista cobrancas com seus lancamentos vinculados."""
    print("\n--- LISTAR COBRANCAS ---")

    clientes_ids, nome_lista = escolher_lista_clientes()
    if not clientes_ids:
        return

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    cobrancas = gestor.buscar_cobrancas_todos_clientes(
        clientes_ids, data_inicio, data_fim, config.CONTA_ID_PADRAO
    )

    if not cobrancas:
        print("Nenhuma cobranca encontrada.")
        return

    print(f"\nBuscando lancamentos de {len(cobrancas)} cobranca(s)...\n")

    for cob in cobrancas:
        ids_lanc = cob.get("lancamento_ids", "")
        qtd = len(ids_lanc.split(",")) if ids_lanc else 0

        print("=" * 70)
        print(f"COBRANCA {cob['id']} | Cliente {cob['cliente_id']} | "
              f"R${cob['valor']} | Venc {cob['data_vencimento']} | "
              f"{cob.get('status_descricao', '?')}")
        print(f"  Link: {cob.get('link_publico', '-')}")
        print(f"  Lancamento IDs: {ids_lanc}")
        print("-" * 70)

        lancamentos = gestor.buscar_lancamentos_da_cobranca(cob)

        if not lancamentos:
            print("  (nenhum lancamento encontrado)")
        else:
            print(f"  {'ID':<10} {'Descricao':<35} {'Valor':>10} {'Categoria':<10}")
            print(f"  {'-'*65}")
            for lanc in lancamentos:
                print(f"  {lanc['id']:<10} {lanc.get('descricao',''):<35} "
                      f"R${lanc.get('valor','0'):>8} {lanc.get('categoria_id','')}")
        print()


def executar_deletar_lancamentos(gestor):
    """Deleta lancamentos diretamente por periodo e descricao."""
    print("\n--- DELETAR LANCAMENTOS POR DESCRICAO ---")

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    descricao = input("Descricao contem: ").strip()
    if not descricao:
        print("Descricao obrigatoria. Cancelando.")
        return

    print(f"\nBusca: '{descricao}' de {data_inicio} a {data_fim}")

    gestor.deletar_lancamentos_por_descricao(
        conta_id=config.CONTA_ID_PADRAO,
        data_inicio=data_inicio,
        data_fim=data_fim,
        descricao_contem=descricao,
    )


def executar_listar_lancamentos(gestor):
    """Lista lancamentos com filtros por data, descricao e categoria."""
    print("\n--- LISTAR LANCAMENTOS (BUSCA GERAL) ---")

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    descricao = input("Descricao contem (Enter=todas): ").strip() or None

    usar_cat = input("Filtrar por categoria? (s/N): ").strip().lower()
    categoria_id = None
    if usar_cat == "s":
        categoria_id = escolher_categoria("Categoria para filtro", obrigatoria=False)

    print(f"\nBuscando lancamentos de {data_inicio} a {data_fim}...")
    if descricao:
        print(f"  Filtro descricao: '{descricao}'")
    if categoria_id:
        print(f"  Filtro categoria ID: {categoria_id}")

    lancamentos = gestor.buscar_lancamentos(
        conta_id=config.CONTA_ID_PADRAO,
        data_inicio=data_inicio,
        data_fim=data_fim,
        busca=descricao,
        categoria_id=categoria_id,
    )

    # Filtro local por descricao (mais preciso que o 'busca' da API)
    if descricao:
        lancamentos = [
            l for l in lancamentos
            if descricao.lower() in l.get("descricao", "").lower()
        ]

    if not lancamentos:
        print("\nNenhum lancamento encontrado.")
        return

    # Carregar nomes de categorias para exibicao
    try:
        categorias = carregar_categorias_flat()
        mapa_cat = {c["id"]: c["descricao"] for c in categorias}
    except Exception:
        mapa_cat = {}

    # Carregar nomes de clientes para exibicao
    mapa_pessoas = {}
    try:
        _, clientes_dados = carregar_lista_clientes("todos_clientes.json")
        mapa_pessoas = {c["id"]: c["nome"] for c in clientes_dados}
    except Exception:
        pass

    print(f"\n{len(lancamentos)} lancamento(s) encontrado(s):\n")
    print(f"  {'ID':<12} {'Descricao':<30} {'Cliente/Fornecedor':<25} {'Valor':>10} {'Vencimento':<12} {'Categoria'}")
    print(f"  {'-'*120}")

    total = 0.0
    for l in lancamentos:
        cat_id = l.get("categoria_id", "")
        cat_nome = mapa_cat.get(cat_id, str(cat_id))
        if len(cat_nome) > 25:
            cat_nome = cat_nome[:22] + "..."
        valor = l.get("valor", "0")
        total += float(valor)

        # Nome do cliente/fornecedor: tentar do detail da API, senao do mapa local
        pessoa_id = l.get("pessoa_id")
        pessoa_nome = ""
        if isinstance(l.get("pessoa"), dict):
            pessoa_nome = l["pessoa"].get("nome", "")
        if not pessoa_nome and pessoa_id:
            pessoa_nome = mapa_pessoas.get(pessoa_id, str(pessoa_id))
        if len(pessoa_nome) > 24:
            pessoa_nome = pessoa_nome[:21] + "..."

        print(f"  {l['id']:<12} {l.get('descricao','')[:30]:<30} "
              f"{pessoa_nome:<25} R${valor:>8} {l.get('data_vencimento',''):<12} {cat_nome}")

    print(f"  {'-'*120}")
    print(f"  {'TOTAL':>67} R${total:>8.2f}")
    print(f"  {len(lancamentos)} lancamento(s)")


def executar_listar_lancamentos_por_clientes(gestor):
    """Lista lancamentos filtrados por lista de clientes."""
    print("\n--- LISTAR LANCAMENTOS POR LISTA DE CLIENTES ---")

    clientes_ids, nome_lista = escolher_lista_clientes()
    if not clientes_ids:
        return

    # Carregar dados completos para ter os nomes
    _, clientes_dados = carregar_lista_clientes(nome_lista)
    mapa_nomes = {c["id"]: c.get("nome", str(c["id"])) for c in clientes_dados}

    data_inicio = input("\nData inicio (YYYY-MM-DD): ").strip()
    data_fim = input("Data fim (YYYY-MM-DD): ").strip()

    if not data_inicio or not data_fim:
        print("Datas obrigatorias. Cancelando.")
        return

    descricao = input("Descricao contem (Enter=todas): ").strip() or None

    usar_cat = input("Filtrar por categoria? (s/N): ").strip().lower()
    categoria_id = None
    if usar_cat == "s":
        categoria_id = escolher_categoria("Categoria para filtro", obrigatoria=False)

    # Carregar nomes de categorias para exibicao
    try:
        categorias = carregar_categorias_flat()
        mapa_cat = {c["id"]: c["descricao"] for c in categorias}
    except Exception:
        mapa_cat = {}

    print(f"\nBuscando lancamentos de {len(clientes_ids)} cliente(s)...")

    total_geral = 0.0
    total_lancamentos = 0

    for cliente_id in clientes_ids:
        nome_cliente = mapa_nomes.get(cliente_id, str(cliente_id))
        print(f"\n  Buscando: {nome_cliente}...")

        lancamentos = gestor.buscar_lancamentos(
            conta_id=config.CONTA_ID_PADRAO,
            data_inicio=data_inicio,
            data_fim=data_fim,
            busca=descricao,
            categoria_id=categoria_id,
            pessoa_id=cliente_id,
        )

        # Filtro local por descricao
        if descricao:
            lancamentos = [
                l for l in lancamentos
                if descricao.lower() in l.get("descricao", "").lower()
            ]

        if not lancamentos:
            continue

        print(f"\n{'=' * 95}")
        print(f"  CLIENTE: {nome_cliente} (ID {cliente_id}) - {len(lancamentos)} lancamento(s)")
        print(f"{'=' * 95}")
        print(f"  {'ID':<12} {'Descricao':<35} {'Valor':>10} {'Vencimento':<12} {'Categoria'}")
        print(f"  {'-'*90}")

        subtotal = 0.0
        for l in lancamentos:
            cat_id = l.get("categoria_id", "")
            cat_nome = mapa_cat.get(cat_id, str(cat_id))
            if len(cat_nome) > 25:
                cat_nome = cat_nome[:22] + "..."
            valor = l.get("valor", "0")
            subtotal += float(valor)
            print(f"  {l['id']:<12} {l.get('descricao','')[:35]:<35} "
                  f"R${valor:>8} {l.get('data_vencimento',''):<12} {cat_nome}")

        print(f"  {'-'*90}")
        print(f"  {'Subtotal':>47} R${subtotal:>8.2f}")

        total_geral += subtotal
        total_lancamentos += len(lancamentos)

    print(f"\n{'=' * 95}")
    print(f"  TOTAL GERAL: {total_lancamentos} lancamento(s) | R${total_geral:.2f}")
    print(f"{'=' * 95}")


def executar_analise_dados():
    """Menu e fluxo para a análise de dados e relatórios."""
    print("\n--- ANÁLISE DE DADOS E RELATÓRIOS ---")
    
    # Pergunta sobre o tipo de lançamento
    tipo_lancamento = input("Analisar lançamentos de (R)eceita ou (D)espesa? [R/D]: ").strip().upper()
    if tipo_lancamento not in ['R', 'D']:
        print("Opção inválida. Use 'R' para Receita ou 'D' para Despesa.")
        return
        
    client = GranatumClient()
    analisador = AnalisadorGranatum(client)

    # Coleta de período
    print("\nDefina o período da análise.")
    # Sugestão de data: primeiro dia do mês passado
    hoje = datetime.now()
    primeiro_dia_mes_passado = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
    data_sugerida_inicio = primeiro_dia_mes_passado.strftime('%Y-%m-01')
    data_sugerida_fim = (primeiro_dia_mes_passado.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    data_sugerida_fim = data_sugerida_fim.strftime('%Y-%m-%d')
    
    data_inicio = input(f"Data início (YYYY-MM-DD) [sugestão: {data_sugerida_inicio}]: ").strip() or data_sugerida_inicio
    data_fim = input(f"Data fim (YYYY-MM-DD) [sugestão: {data_sugerida_fim}]: ").strip() or data_sugerida_fim

    # Busca todos os lançamentos do período, já filtrando por Receita ou Despesa
    df_filtrado = analisador.obter_lancamentos(data_inicio, data_fim, tipo_lancamento)

    if df_filtrado.empty:
        print(f"\nNenhum lançamento de {'Receita' if tipo_lancamento == 'R' else 'Despesa'} encontrado no período.")
        return

    while True:
        print("\n--- TIPO DE ANÁLISE ---")
        print("1 - Relatório completo por Categoria")
        print("2 - Relatório completo por Centro de Custo")
        print("3 - Relatório de tendência mensal (série temporal)")
        print("4 - Filtrar por descrição e gerar relatórios completos")
        print("-" * 20)
        print("5 - Top 12 Categorias")
        print("6 - Top 12 Centros de Custo")
        print("7 - Análise Sazonal (Mensal)")
        print("-" * 20)
        print("0 - Voltar ao menu principal")

        opcao = input("\nEscolha a análise: ").strip()

        if opcao == "1":
            titulo = f"Relatório de {'Receitas' if tipo_lancamento == 'R' else 'Despesas'} por Categoria ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_agrupado(df_filtrado, 'categoria_descricao', titulo)

        elif opcao == "2":
            titulo = f"Relatório de {'Receitas' if tipo_lancamento == 'R' else 'Despesas'} por Centro de Custo ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_agrupado(df_filtrado, 'centro_custo_descricao', titulo)

        elif opcao == "3":
            titulo = f"Tendência Mensal de {'Receitas' if tipo_lancamento == 'R' else 'Despesas'} ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_tendencia_temporal(df_filtrado, titulo)
        
        elif opcao == "4":
            descricao = input("Filtrar por descrição que contém: ").strip()
            if not descricao:
                print("Descrição não pode ser vazia.")
                continue

            df_sub_filtrado = df_filtrado[df_filtrado['descricao'].str.contains(descricao, case=False, na=False)].copy()
            
            if df_sub_filtrado.empty:
                print(f"Nenhum lançamento encontrado com a descrição '{descricao}'.")
                continue
            
            print(f"\n--- GERANDO RELATÓRIOS PARA '{descricao}' ---")
            
            titulo_cat = f"Relatório por Categoria para '{descricao}' ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_agrupado(df_sub_filtrado, 'categoria_descricao', titulo_cat)

            titulo_cc = f"Relatório por Centro de Custo para '{descricao}' ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_agrupado(df_sub_filtrado, 'centro_custo_descricao', titulo_cc)

            titulo_ts = f"Tendência Mensal para '{descricao}' ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_tendencia_temporal(df_sub_filtrado, titulo_ts)

        elif opcao == "5":
            titulo = f"Top 12 Categorias de {'Receita' if tipo_lancamento == 'R' else 'Despesa'} ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_top_n(df_filtrado, 'categoria_descricao', titulo, n=12)

        elif opcao == "6":
            titulo = f"Top 12 Centros de Custo de {'Receita' if tipo_lancamento == 'R' else 'Despesa'} ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_top_n(df_filtrado, 'centro_custo_descricao', titulo, n=12)

        elif opcao == "7":
            agrupar_por_escolha = input("Analisar por (C)ategoria ou (CC) Centro de Custo? [C/CC]: ").strip().upper()
            
            if agrupar_por_escolha == 'C':
                agrupar_por_col = 'categoria_descricao'
                itens_selecionados = escolher_multiplas_categorias()
            elif agrupar_por_escolha == 'CC':
                agrupar_por_col = 'centro_custo_descricao'
                itens_selecionados = escolher_multiplos_centros_custo()
            else:
                print("Opção inválida.")
                continue

            if not itens_selecionados:
                print("Nenhum item selecionado. Voltando ao menu de análise.")
                continue

            titulo = f"Análise Sazonal de {'Receitas' if tipo_lancamento == 'R' else 'Despesas'} ({data_inicio} a {data_fim})"
            analisador.gerar_relatorio_sazonal(df_filtrado, agrupar_por_col, itens_selecionados, titulo)

        elif opcao == "0":
            break
        else:
            print("Opção inválida.")


# =============================================
#  Ponto de entrada
# =============================================

if __name__ == "__main__":
    gestor = GestorCobrancas()

    while True:
        opcao = menu_principal()

        if opcao == "1":
            executar_adicionar(gestor)
        elif opcao == "2":
            executar_remover(gestor)
        elif opcao == "3":
            executar_listar(gestor)
        elif opcao == "4":
            executar_deletar_lancamentos(gestor)
        elif opcao == "5":
            executar_listar_lancamentos(gestor)
        elif opcao == "6":
            executar_listar_lancamentos_por_clientes(gestor)
        elif opcao == "7":
            executar_analise_dados()
        elif opcao == "0":
            print("Encerrado.")
            break
        else:
            print("Opcao invalida.")
