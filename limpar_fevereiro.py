from api_granatum import GranatumAPI
import config  # <--- ADICIONAMOS ISSO
import json
import time

def executar_limpeza():
    api = GranatumAPI()
    
    # Datas de Fevereiro
    inicio = "2026-02-01"
    fim = "2026-02-28"
    
    # <--- MUDANÇA AQUI: Agora passamos a conta padrão do seu config.py
    print(f"🔍 Buscando lançamentos na conta {config.CONTA_ID_PADRAO}...")
    lancamentos = api.listar_lancamentos(inicio, fim, conta_id=config.CONTA_ID_PADRAO)
    
    qtd = len(lancamentos)
    if qtd == 0:
        print("✅ Nenhum lançamento encontrado neste período. Tudo limpo!")
        return

    print(f"⚠️ ENCONTREI {qtd} LANÇAMENTOS.")
    
    # Salvar Backup
    nome_backup = f"backup_antes_deletar_{inicio}.json"
    with open(nome_backup, 'w', encoding='utf-8') as f:
        json.dump(lancamentos, f, indent=4)
    print(f"💾 Backup salvo em: {nome_backup}")
    
    confirmacao = input(f"\nTem certeza que deseja APAGAR os {qtd} lançamentos? (Digite 'SIM' para continuar): ")
    
    if confirmacao != 'SIM':
        print("🚫 Operação cancelada.")
        return

    print("\n🚀 Iniciando exclusão...")
    sucessos = 0
    erros = 0
    
    for item in lancamentos:
        id_lancamento = item['id']
        descricao = item.get('descricao', 'Sem descrição')
        
        print(f"🗑️ Deletando ID {id_lancamento} ({descricao})...", end="")
        
        if api.deletar_lancamento(id_lancamento):
            print(" Feito!")
            sucessos += 1
        else:
            print(" Falhou.")
            erros += 1
            
        time.sleep(1) 

    print("\n" + "="*30)
    print(f"✅ Apagados: {sucessos}")
    print(f"❌ Falhas: {erros}")
    print("="*30)

if __name__ == "__main__":
    executar_limpeza()