import sys
import os
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import requests
from app.config import config

class GranatumClient:
    def __init__(self):
        # Headers padrão exigidos pela documentação
        self.headers = {
            "User-Agent": "MinhaAutomacao/2.0",
        }
        self.token = config.TOKEN_GRANATUM
        self.base_url = config.URL_BASE
        self.silent = False

    def _auth_params(self, params=None):
        """Mistura os parâmetros do usuário com o Token de segurança."""
        payload = {"access_token": self.token}
        if params:
            payload.update(params)
        return payload

    def get(self, endpoint, params=None):
        """Busca dados (GET). Retorna a lista ou dicionário."""
        url = f"{self.base_url}/{endpoint}"
        if not self.silent:
            print(f"📡 GET {endpoint}...", end="")

        try:
            response = requests.get(url, params=self._auth_params(params), headers=self.headers)
            response.raise_for_status() # Avisa se der erro 400/500
            if not self.silent:
                print(" ✅ OK")
            return response.json()
        except requests.exceptions.RequestException as e:
            if not self.silent:
                print(f" ❌ Falha: {e}")
            return []

    def post(self, endpoint, data):
        """Envia dados (POST). Retorna o item criado."""
        url = f"{self.base_url}/{endpoint}"
        # No POST, o token vai na URL (query string) e os dados no corpo (data)
        url_auth = f"{url}?access_token={self.token}"

        try:
            response = requests.post(url_auth, json=data, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if not self.silent:
                print(f" ❌ Erro ao criar: {e}")
                try:
                    if e.response is not None:
                        print(f"    Detalhe: {e.response.text}")
                except Exception:
                    pass
            
            # Se for erro de validação (422), retorna o JSON para tratamento
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 422:
                try:
                    return e.response.json()
                except:
                    pass
            return None

    def delete(self, endpoint, params=None):
        """Apaga dados (DELETE). Aceita params extras (ex: excluir_lancamentos)."""
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.delete(url, params=self._auth_params(params), headers=self.headers)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return True
        except requests.exceptions.RequestException as e:
            if not self.silent:
                print(f" ❌ Erro ao deletar: {e}")
            return False