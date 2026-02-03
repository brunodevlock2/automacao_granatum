import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime, timedelta
from api_client import GranatumClient
import os
import config

class AnalisadorGranatum:
    def __init__(self, client: GranatumClient):
        self.client = client
        self.output_dir = "relatorios"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def obter_lancamentos(self, data_inicio, data_fim, tipo_lancamento):
        """
        Busca todos os lançamentos pagos (Receitas ou Despesas) em um determinado período.
        
        :param data_inicio: Data de início (YYYY-MM-DD)
        :param data_fim: Data de fim (YYYY-MM-DD)
        :param tipo_lancamento: 'R' para Receitas (LR) ou 'D' para Despesas (LP)
        """
        print("Buscando lançamentos no Granatum...")
        todos_lancamentos = []

        # Mapeia a escolha do usuário para o parâmetro da API
        tipo_param = 'LR' if tipo_lancamento == 'R' else 'LP'

        params = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "tipo": tipo_param,
            "conta_id": config.CONTA_ID_PADRAO,
            "tipo_view": "detail",
            "limit": 500  # Máximo permitido pela API
        }
        
        offset = 0
        while True:
            params['start'] = offset
            try:
                resposta = self.client.get('lancamentos', params=params)
                
                if resposta and len(resposta) > 0:
                    todos_lancamentos.extend(resposta)
                    # Se a resposta tiver menos itens que o limite, é a última página
                    if len(resposta) < params["limit"]:
                        break
                    offset += params["limit"]
                else:
                    break # Sai do loop se não houver mais lançamentos
            except Exception as e:
                print(f"Erro ao buscar lançamentos: {e}")
                break

        print(f"{len(todos_lancamentos)} lançamentos encontrados.")
        if not todos_lancamentos:
            return pd.DataFrame()

        df = pd.DataFrame(todos_lancamentos)
        # Adiciona a coluna 'tipo_lancamento' que não vem da API, para uso interno
        df['tipo_lancamento'] = tipo_lancamento
        return self._processar_dataframe(df)

    def _carregar_mapa_categorias(self):
        """Carrega 'categorias.json' e retorna um mapa de ID para descricao."""
        try:
            # Reutiliza a função de `main_cobrancas` se possível, ou reimplementa
            from main_cobrancas import carregar_categorias_flat
            categorias = carregar_categorias_flat()
            return {c['id']: c['descricao'] for c in categorias}
        except (ImportError, FileNotFoundError):
            print("Aviso: Nao foi possivel carregar 'categorias.json'. As descricoes das categorias nao estarao disponiveis.")
            return {}

    def _carregar_mapa_centros_custo(self):
        """Carrega 'centros_de_custo.json' e retorna um mapa de ID para descricao."""
        try:
            # Reutiliza a função de `main_cobrancas` se possível, ou reimplementa
            from main_cobrancas import carregar_centros_custo_flat
            centros = carregar_centros_custo_flat()
            return {c['id']: c['descricao'] for c in centros}
        except (ImportError, FileNotFoundError):
            print("Aviso: Nao foi possivel carregar 'centros_de_custo.json'. As descricoes dos centros de custo nao estarao disponiveis.")
            return {}

    def _processar_dataframe(self, df):
        """
        Processa o DataFrame bruto, convertendo tipos, limpando dados e
        enriquecendo com descrições de categoria e centro de custo.
        """
        if df.empty:
            return df

        # Converte colunas de data
        for col in ['data_vencimento', 'data_pagamento', 'data_competencia']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        # Converte coluna de valor
        if 'valor' in df.columns:
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')

        # Remove linhas onde a conversão de dados essenciais falhou
        df.dropna(subset=['data_pagamento', 'valor'], inplace=True)

        # Carrega mapas de ID para descrição
        mapa_categorias = self._carregar_mapa_categorias()
        mapa_centros_custo = self._carregar_mapa_centros_custo()
        
        # Adiciona colunas com as descrições legíveis
        if 'categoria_id' in df.columns and mapa_categorias:
            df['categoria_descricao'] = df['categoria_id'].map(mapa_categorias).fillna('Sem Categoria')
        else:
            df['categoria_descricao'] = 'N/A'
            
        if 'centro_custo_lucro_id' in df.columns and mapa_centros_custo:
            df['centro_custo_descricao'] = df['centro_custo_lucro_id'].map(mapa_centros_custo).fillna('Sem Centro de Custo')
        else:
            df['centro_custo_descricao'] = 'N/A'

        return df

    def gerar_relatorio_agrupado(self, df, agrupar_por, titulo):
        """
        Gera um relatório de texto e um gráfico de barras.
        """
        if df.empty:
            print(f"Nenhum dado para gerar o relatório '{titulo}'.")
            return

        agrupado = df.groupby(agrupar_por)['valor'].sum().reset_index()
        agrupado = agrupado.sort_values('valor', ascending=False)

        print("\n--- Relatório: " + titulo + " ---")
        print(agrupado.to_string(index=False))

        # Gerar gráfico
        plt.figure(figsize=(12, 7))
        # Adicionado hue e legend=False para resolver o FutureWarning
        sns.barplot(data=agrupado, x=agrupar_por, y='valor', palette='viridis', hue=agrupar_por, legend=False)
        plt.title(titulo)
        plt.xlabel(agrupar_por)
        plt.ylabel("Valor Total (R$)")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        nome_arquivo = f"{titulo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.png"
        caminho_arquivo = os.path.join(self.output_dir, nome_arquivo)
        plt.savefig(caminho_arquivo)
        plt.close()
        print(f"Gráfico salvo em: {caminho_arquivo}")

    def gerar_relatorio_tendencia_temporal(self, df, titulo):
        """
        Gera um relatório de tendência temporal (série temporal).
        """
        if df.empty or 'data_pagamento' not in df.columns:
            print(f"Nenhum dado para gerar o relatório de tendência '{titulo}'.")
            return
            
        # Alterado de 'M' para 'ME' para corrigir erro de depreciação do Pandas
        df_temporal = df.set_index('data_pagamento').resample('ME')['valor'].sum().reset_index()
        df_temporal['mes'] = df_temporal['data_pagamento'].dt.strftime('%Y-%m')

        print("\n--- Relatório de Tendência: " + titulo + " ---")
        print(df_temporal[['mes', 'valor']].to_string(index=False))

        # Gerar gráfico
        plt.figure(figsize=(12, 7))
        sns.lineplot(data=df_temporal, x='mes', y='valor', marker='o')
        plt.title(titulo)
        plt.xlabel("Mês")
        plt.ylabel("Valor Total (R$)")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        # Adicionar linha de tendência (projeção linear simples)
        if len(df_temporal) > 1:
            x = np.arange(len(df_temporal))
            y = df_temporal['valor']
            m, b = np.polyfit(x, y, 1)
            plt.plot(x, m*x + b, color='red', linestyle='--', label='Linha de Tendência')
            plt.legend()

        nome_arquivo = f"{titulo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.png"
        caminho_arquivo = os.path.join(self.output_dir, nome_arquivo)
        plt.savefig(caminho_arquivo)
        plt.close()
        print(f"Gráfico de tendência salvo em: {caminho_arquivo}")

    def gerar_relatorio_top_n(self, df, agrupar_por, titulo, n=12):
        """
        Gera um relatório de texto e um gráfico de barras para os Top N itens,
        agrupando os demais em "Outros".
        """
        if df.empty:
            print(f"Nenhum dado para gerar o relatório '{titulo}'.")
            return

        agrupado = df.groupby(agrupar_por)['valor'].sum().sort_values(ascending=False)

        if len(agrupado) > n:
            top_n = agrupado.head(n)
            soma_outros = agrupado.iloc[n:].sum()
            
            # Usando pd.concat para adicionar a linha "Outros"
            outros_row = pd.DataFrame([{agrupar_por: 'Outros', 'valor': soma_outros}])
            final_df = pd.concat([top_n.reset_index(), outros_row], ignore_index=True)
        else:
            final_df = agrupado.reset_index()

        print("\n--- Relatório: " + titulo + " ---")
        print(final_df.to_string(index=False))

        # Gerar gráfico
        plt.figure(figsize=(12, 7))
        sns.barplot(data=final_df, x=agrupar_por, y='valor', palette='viridis', hue=agrupar_por, legend=False)
        plt.title(titulo)
        plt.xlabel(agrupar_por)
        plt.ylabel("Valor Total (R$)")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        nome_arquivo = f"{titulo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.png"
        caminho_arquivo = os.path.join(self.output_dir, nome_arquivo)
        plt.savefig(caminho_arquivo)
        plt.close()
        print(f"Gráfico salvo em: {caminho_arquivo}")

    def gerar_relatorio_sazonal(self, df, agrupar_por, itens_selecionados, titulo):
        """
        Gera um relatório e um gráfico de análise sazonal para uma lista de
        categorias ou centros de custo.
        """
        if df.empty:
            print(f"Nenhum dado para gerar o relatório '{titulo}'.")
            return

        # Filtra o DataFrame para incluir apenas os itens selecionados
        df_filtrado = df[df[agrupar_por].isin(itens_selecionados)].copy()
        
        if df_filtrado.empty:
            print(f"Nenhum dado encontrado para os itens selecionados: {', '.join(itens_selecionados)}")
            return

        # Prepara o DataFrame para a tabela dinâmica
        df_filtrado['mes'] = df_filtrado['data_pagamento'].dt.to_period('M')

        # Cria a tabela dinâmica
        pivot_table = pd.pivot_table(
            df_filtrado,
            values='valor',
            index=agrupar_por,
            columns='mes',
            aggfunc=np.sum,
            fill_value=0
        )

        # Adiciona colunas de resumo
        pivot_table['Total'] = pivot_table.sum(axis=1)
        pivot_table['Media_Mensal'] = pivot_table.iloc[:, :-1].mean(axis=1)

        print("\n--- Relatório: " + titulo + " ---")
        # Formata os valores como moeda para melhor visualização
        print(pivot_table.to_string(float_format="R$ {:,.2f}".format))

        # --- Geração do Gráfico ---
        # Prepara os dados para o gráfico (remove as colunas de resumo)
        df_plot = pivot_table.drop(columns=['Total', 'Media_Mensal']).T
        df_plot.index = df_plot.index.to_timestamp() # Converte Period para Timestamp para plotar

        plt.figure(figsize=(15, 8))
        sns.lineplot(data=df_plot, markers=True)
        
        plt.title(titulo)
        plt.xlabel("Mês")
        plt.ylabel("Valor Total (R$)")
        plt.xticks(rotation=45, ha='right')
        plt.legend(title=agrupar_por)
        plt.tight_layout()
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)

        nome_arquivo = f"{titulo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.png"
        caminho_arquivo = os.path.join(self.output_dir, nome_arquivo)
        plt.savefig(caminho_arquivo)
        plt.close()
        print(f"\nGráfico salvo em: {caminho_arquivo}")
