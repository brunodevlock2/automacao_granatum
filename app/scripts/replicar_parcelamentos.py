import sys
import os
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.scripts.gestor_cobrancas import GestorCobrancas
from app.config import config

def duplicar_parcelamentos_corrigido():
    print("\n" + "="*70)
    print("  REPLICAR PARCELAMENTOS DE MARÇO PARA ABRIL (AGRUPADOS POR VALOR)")
    print("="*70 + "\n")

    gestor = GestorCobrancas()
    
    # Textos EXATOS que você enviou. A busca_api é curta apenas para não bugar a pesquisa do Granatum
    itens_para_replicar = [
        {
            "busca_api": "Estrela Divina",
            "busca_exata": "Taxa de Preparo - Núcleo Estrela Divina (R$48,00 por pessoa em 3x de R$16,00 - Mar, Abr, Maio)"
        },
        {
            "busca_api": "Contribuição salão",
            "busca_exata": "Contribuição salão de preparos e encontros da 3a região (8 parcelas de R$20,00 por pessoa - De Março a Outubro de 2026)"
        }
    ]
    
    data_origem_inicio = "2026-03-01"
    data_origem_fim = "2026-03-31"
    
    data_destino_inicio = "2026-04-01"
    data_destino_fim = "2026-04-30"
    
    for config_item in itens_para_replicar:
        busca_api = config_item["busca_api"]
        busca_exata = config_item["busca_exata"]
        
        print(f"\n{'-'*70}")
        print(f"[{busca_exata}]")
        print(f"Buscando em Março ({data_origem_inicio} a {data_origem_fim})...")
        
        lancamentos_marco = gestor.buscar_lancamentos(
            conta_id=config.CONTA_ID_PADRAO,
            data_inicio=data_origem_inicio,
            data_fim=data_origem_fim,
            busca=busca_api
        )
        
        # Filtro EXATO
        lancamentos_filtrados = [
            l for l in lancamentos_marco 
            if busca_exata.lower() in l.get("descricao", "").lower()
        ]
        
        if not lancamentos_filtrados:
            print(f"Nenhum lançamento encontrado para: '{busca_exata}'. Pulando.")
            continue
            
        print(f"Encontrados {len(lancamentos_filtrados)} lançamentos no total com essa descrição exata.")
            
        # Agrupar clientes por VALOR EXATO pago em Março
        # Dicionário: valor -> { 'clientes': set(), 'item_ref': dict, 'mapa_nomes': dict }
        grupos_por_valor = defaultdict(lambda: {"clientes": set(), "item_ref": None, "mapa_nomes": {}})
        
        for l in lancamentos_filtrados:
            pid = l.get("pessoa_id")
            if not pid:
                continue
                
            valor = abs(float(l.get("valor", 0)))
            
            # Adicionar ao grupo deste valor
            grupo = grupos_por_valor[valor]
            grupo["clientes"].add(pid)
            
            if grupo["item_ref"] is None:
                grupo["item_ref"] = l
                
            # Salvar nome para display
            if isinstance(l.get("pessoa"), dict) and l["pessoa"].get("nome"):
                grupo["mapa_nomes"][pid] = l["pessoa"]["nome"]
            else:
                grupo["mapa_nomes"][pid] = str(pid)
                
        print(f"Clientes divididos em {len(grupos_por_valor)} grupo(s) de valores distintos.\n")
        
        # Para cada grupo de valor (ex: o grupo de 16,00 e o grupo de 32,00)
        for valor_exato, dados_grupo in grupos_por_valor.items():
            clientes_ids = list(dados_grupo["clientes"])
            item_ref = dados_grupo["item_ref"]
            mapa_local = dados_grupo["mapa_nomes"]
            
            # ATENÇÃO: Ao passar um mapa_clientes pro GestorCobrancas original, 
            # ele vai tentar dobrar se achar a palavra 'casal'.
            # Como a API raramente retorna o nome modificado, geralmente ele não vai dobrar, 
            # MAS para garantir 100% que fiquemos livres dessa funcionalidade e usemos o valor EXATO,
            # vamos passar um dicionário vazio para o gestor.
            mapa_anti_casal = {pid: "Cliente" for pid in clientes_ids} 
            
            novo_item = {
                "descricao": item_ref["descricao"],
                "categoria_id": item_ref["categoria_id"],
                "valor": valor_exato
            }
            
            ccl_id = item_ref.get("centro_custo_lucro_id")
            if ccl_id and int(ccl_id) != 0:
                novo_item["centro_custo_lucro_id"] = int(ccl_id)
                
            print(f">>> Processando Grupo Valor: R${valor_exato:.2f} ({len(clientes_ids)} clientes)")
            print(f"    Item a ser copiado fielmente: {novo_item['descricao']} - Cat: {novo_item['categoria_id']}")
            
            # Chama a criação no mês de Abril
            gestor.adicionar_lancamento_a_cobrancas(
                clientes_ids=clientes_ids,
                data_inicio=data_destino_inicio,
                data_fim=data_destino_fim,
                novo_item=novo_item,
                conta_id=config.CONTA_ID_PADRAO,
                mapa_clientes=mapa_anti_casal, # Força com que 'casal' não seja ativado de forma invisível
                dias_para_emissao=None
            )
            print("----------------------------------------------------------------")
            
        print(f"Finalizado o agrupamento e replicação de: '{busca_exata}'\n")
        
    print("\n" + "="*70)
    print("SCRIPT CONCLUÍDO.")
    print("="*70 + "\n")

if __name__ == "__main__":
    duplicar_parcelamentos_corrigido()
