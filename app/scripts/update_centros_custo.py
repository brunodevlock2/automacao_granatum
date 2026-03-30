import sys
import os
import json
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.api.api_client import GranatumClient

def contar_folhas(itens):
    """Conta recursivamente quantos centros de custo folha (sem filhos) existem."""
    total = 0
    for item in itens:
        filhos = item.get("centros_custo_lucro_filhos", [])
        if not filhos:
            total += 1
        else:
            total += contar_folhas(filhos)
    return total

def main():
    client = GranatumClient()
    print("Baixando centros de custo da API...")
    centros = client.get("centros_custo_lucro")

    if not centros:
        print("Erro ao baixar centros de custo (ou lista vazia).")
        return

    caminho = os.path.join(os.path.dirname(__file__), '../../data/centros_de_custo.json')
    caminho = os.path.abspath(caminho)

    print(f"Salvando {len(centros)} centros de custo (raiz) em: {caminho}")
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(centros, f, indent=4, ensure_ascii=False)

    total_folhas = contar_folhas(centros)
    print(f"Centros de custo atualizados com sucesso! ({total_folhas} entradas selecionáveis no total)")

if __name__ == "__main__":
    main()
