import sys
import os
import json
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.api.api_client import GranatumClient

def main():
    client = GranatumClient()
    print("Baixando categorias da API...")
    categorias = client.get("categorias")
    
    if not categorias:
        print("Erro ao baixar categorias (ou lista vazia).")
        return

    caminho = os.path.join(os.path.dirname(__file__), '../../data/categorias.json')
    caminho = os.path.abspath(caminho)
    
    print(f"Salvando {len(categorias)} categorias em: {caminho}")
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(categorias, f, indent=4, ensure_ascii=False)
    
    print("Categorias atualizadas com sucesso!")

    # Verificacao rapida do ID problematico
    id_problematico = 2148098
    for cat in categorias:
        if cat['id'] == id_problematico:
            print(f"\nVerificacao: A categoria ID {id_problematico} ('{cat['descricao']}') tem {len(cat.get('categorias_filhas', []))} filhas.")
            if cat.get('categorias_filhas'):
                print("  -> Agora o sistema vai conseguir auto-corrigir!")
            else:
                print("  -> ELA AINDA NAO TEM FILHAS NO JSON! Estranho...")
            break

if __name__ == "__main__":
    main()
