import subprocess
import sys
import os

def build():
    # Garantir que PyInstaller está no PATH ou rodando no mesmo python
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name=GranatumBot",
        "--add-data=app/web/templates;app/web/templates",
        "--add-data=app/web/static;app/web/static",
        "--collect-all=uvicorn",
        "--collect-all=fastapi",
        "--collect-all=websockets",
        "app/web/server.py"
    ]
    
    print("Iniciando build do executável com PyInstaller...")
    print("Executando:", " ".join(cmd))
    
    try:
        # Executa o comando
        result = subprocess.run(cmd, check=True)
        print("\nBuild concluido com sucesso!")
        print("O arquivo GranatumBot.exe foi gerado na pasta 'dist/'.")
    except subprocess.CalledProcessError as e:
        print(f"\nErro durante o build: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
