import sys
import os
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import requests
from app.config import config

class GranatumClient:
    def __init__(self):
        self.headers = {
            "User-Agent": "MinhaAutomacaoFinanceira/1.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.auth_params = {"access_token": config.TOKEN_GRANATUM}
        self.base_url = config.URL_BASE

    def get(self, endpoint, params=None):
        """Método genérico para buscar dados (GET)."""
        full_params = self.auth_params.copy()
        if params:
            full_params.update(params)
            
        print(f"📡 GET {endpoint}...", end="")
        response = requests.get(f"{self.base_url}/{endpoint}", params=full_params, headers=self.headers)
        
        if response.status_code == 200:
            print(" ✅")
            return response.json()
        else:
            print(f" ❌ {response.status_code}")
            return []

    def delete(self, endpoint):
        """Método genérico para apagar dados (DELETE)."""
        print(f"🔥 DELETE {endpoint}...", end="")
        response = requests.delete(f"{self.base_url}/{endpoint}", params=self.auth_params, headers=self.headers)
        
        if response.status_code == 200:
            print(" ✅")
            return True
        else:
            print(f" ❌ {response.status_code} - {response.text}")
            return False

    def post(self, endpoint, data):
        """Método genérico para enviar dados (POST)."""
        # Implementação futura se precisar criar lançamentos
        pass