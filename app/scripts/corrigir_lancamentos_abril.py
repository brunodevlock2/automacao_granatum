import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.scripts.gestor_cobrancas import GestorCobrancas
from app.config import config

def corrigir_lancamentos_errados():
    print("\n" + "="*60)
    print("  REMOVER LANÇAMENTOS ERRADOS DE ABRIL")
    print("="*60 + "\n")

    gestor = GestorCobrancas()
    
    textos_para_remover = [
        "Taxa de Preparo - Núcleo Estrela Divina (R$48,00 por pessoa em 3x de R$16,00 - Mar, Abr, Maio)",
        "Contribuição salão de preparos e encontros da 3a região (8 parcelas de R$20,00 por pessoa - De Março a Outubro de 2026)"
    ]
    
    data_destino_inicio = "2026-04-01"
    data_destino_fim = "2026-04-30"
    
    for texto in textos_para_remover:
        print(f"\nProcurando clientes que possuem: '{texto}' em Abril...")
        
        # 1. Procurar os lançamentos em Abril com busca simples pra facilitar API
        busca_simples = texto.split("-")[0].strip() if "-" in texto else texto.split()[0]
        lancamentos_abril = gestor.buscar_lancamentos(
            conta_id=config.CONTA_ID_PADRAO,
            data_inicio=data_destino_inicio,
            data_fim=data_destino_fim,
            busca=busca_simples
        )
        
        # 2. Filtrar exatamente pelo texto completo
        lancamentos_filtrados = [
            l for l in lancamentos_abril 
            if texto.lower() in l.get("descricao", "").lower()
        ]
        
        if not lancamentos_filtrados:
            print(f"  Nenhum item encontrado para remover de: '{texto}'")
            continue
            
        clientes_ids = list(set([l["pessoa_id"] for l in lancamentos_filtrados if l.get("pessoa_id")]))
        
        print(f"  Encontrados em {len(clientes_ids)} clientes distintos. Iniciando remoção...\n")
        
        gestor.remover_lancamento_de_cobrancas(
            clientes_ids=clientes_ids,
            data_inicio=data_destino_inicio,
            data_fim=data_destino_fim,
            filtro_remocao={"descricao_contem": texto},
            conta_id=config.CONTA_ID_PADRAO
        )
        print("====================================")

    print("\n" + "="*60)
    print("REMOÇÃO CONCLUÍDA.")
    print("="*60 + "\n")

if __name__ == "__main__":
    corrigir_lancamentos_errados()
