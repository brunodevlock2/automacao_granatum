from app.api.api_granatum import GranatumClient
import json

def teste_conexao():
    # 1. Instancia o nosso "motor" da API
    api = GranatumClient()
    
    # 2. Tenta buscar os clientes
    # O cliente genérico não tem listar_clientes, usamos get('clientes')
    clientes = api.get("clientes")
    
    # 3. Mostra o resultado
    if clientes:
        print(f"\n🎉 Sucesso! Encontrei {len(clientes)} clientes.")
        print("Aqui estão os 3 primeiros para conferência:")
        for cliente in clientes[:3]: # Pega só os 3 primeiros
            print(f"- ID: {cliente['id']} | Nome: {cliente['nome']}")
    else:
        print("⚠️ Nenhum cliente encontrado ou houve erro na conexão.")

if __name__ == "__main__":
    teste_conexao()