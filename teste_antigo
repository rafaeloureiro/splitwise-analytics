"""
Aplicação de Análise de Fluxo de Caixa do Trello

Este script conecta-se a um board do Trello, coleta cards de contas a pagar,
e gera um relatório visual interativo em HTML com opção de envio por WhatsApp.

Autor: Claude Code
Data: 2025-11-24
"""

import os
import re
import sys

# Configurar encoding UTF-8 para o console do Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# pywhatkit é opcional - só funciona em ambiente com GUI (não funciona no Streamlit Cloud)
try:
    import pywhatkit as pwk
    PYWHATKIT_AVAILABLE = True
except (ImportError, KeyError):
    PYWHATKIT_AVAILABLE = False


class TrelloCashFlowAnalyzer:
    """Classe principal para análise de fluxo de caixa do Trello."""

    def __init__(self):
        """
        Inicializa o analisador com as credenciais do Trello.
        Carrega o .env da pasta atual do projeto.
        """
        # Obtém o diretório do script atual
        self.project_dir = Path(__file__).parent
        self.env_path = self.project_dir / ".env"
        self.outputs_dir = self.project_dir / "outputs"

        # Garante que a pasta outputs existe
        self.outputs_dir.mkdir(exist_ok=True)

        self.api_key = None
        self.token = None
        self.board_id = None
        self.base_url = "https://api.trello.com/1"

    def load_credentials(self, use_streamlit_secrets: bool = False) -> bool:
        """
        Carrega as credenciais do Streamlit secrets ou arquivo .env na pasta do projeto.

        Args:
            use_streamlit_secrets: Se True, tenta carregar do st.secrets primeiro

        Returns:
            True se as credenciais foram carregadas com sucesso, False caso contrário
        """
        try:
            # Tentar carregar do Streamlit secrets primeiro (se disponível)
            if use_streamlit_secrets:
                try:
                    import streamlit as st
                    self.api_key = st.secrets.get("TRELLO_API_KEY")
                    self.token = st.secrets.get("TRELLO_TOKEN")

                    if self.api_key and self.token:
                        print("✅ Credenciais carregadas do Streamlit secrets")
                        return True
                    else:
                        print("⚠️ Credenciais não encontradas no Streamlit secrets, tentando .env...")
                except Exception as e:
                    print(f"⚠️ Erro ao carregar do Streamlit secrets: {str(e)}, tentando .env...")

            # Fallback para .env
            print(f"📂 Carregando credenciais de: {self.env_path}")

            if not self.env_path.exists():
                print(f"❌ ERRO: Arquivo .env não encontrado em {self.env_path}")
                return False

            load_dotenv(self.env_path)
            self.api_key = os.getenv('TRELLO_API_KEY')
            self.token = os.getenv('TRELLO_TOKEN')

            if not self.api_key or not self.token:
                print("❌ ERRO: Credenciais TRELLO_API_KEY ou TRELLO_TOKEN não encontradas no .env")
                return False

            print("✅ Credenciais carregadas com sucesso")
            return True

        except Exception as e:
            print(f"❌ ERRO ao carregar credenciais: {str(e)}")
            return False

    def extract_board_id(self, board_url: str) -> str:
        """
        Extrai o ID do board a partir da URL.

        Args:
            board_url: URL do board do Trello

        Returns:
            ID do board
        """
        # URL format: https://trello.com/b/WgSarYPK/contas-a-pagar-25
        match = re.search(r'/b/([a-zA-Z0-9]+)/', board_url)
        if match:
            return match.group(1)
        raise ValueError(f"URL do board inválida: {board_url}")

    def get_board_lists(self, board_url: str) -> List[Dict]:
        """
        Obtém todas as listas do board.

        Args:
            board_url: URL do board do Trello

        Returns:
            Lista de dicionários com informações das listas
        """
        try:
            self.board_id = self.extract_board_id(board_url)

            url = f"{self.base_url}/boards/{self.board_id}/lists"
            params = {
                'key': self.api_key,
                'token': self.token
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            lists = response.json()
            print(f"✅ {len(lists)} listas encontradas no board")
            return lists

        except requests.exceptions.RequestException as e:
            print(f"❌ ERRO ao buscar listas do board: {str(e)}")
            return []
        except Exception as e:
            print(f"❌ ERRO inesperado: {str(e)}")
            return []

    def identify_month_lists(self, lists: List[Dict], start_date: datetime, end_date: datetime) -> List[str]:
        """
        Identifica as listas correspondentes aos meses necessários.

        Args:
            lists: Lista de dicionários com informações das listas
            start_date: Data inicial do período
            end_date: Data final do período

        Returns:
            Lista de IDs das listas identificadas
        """
        # Formatos possíveis: "Outubro/25", "Outubro / 25", "outubro/25", etc.
        months_pt = {
            1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }

        # Determinar quais meses precisamos
        months_needed = set()
        current_date = start_date
        while current_date <= end_date:
            month_name = months_pt[current_date.month].lower()
            year_short = str(current_date.year)[2:]  # "25" de 2025
            months_needed.add((month_name, year_short))

            # Próximo mês
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        print(f"📅 Meses necessários: {months_needed}")

        # Encontrar listas correspondentes
        list_ids = []
        for list_obj in lists:
            list_name = list_obj['name'].lower().strip()

            for month_name, year_short in months_needed:
                # Pattern: aceita espaços extras ao redor da barra
                pattern = rf'{month_name}\s*/\s*{year_short}'
                if re.search(pattern, list_name):
                    list_ids.append(list_obj['id'])
                    print(f"✅ Lista encontrada: '{list_obj['name']}' (ID: {list_obj['id']})")
                    break

        if not list_ids:
            print("⚠️ AVISO: Nenhuma lista encontrada para os meses necessários")

        return list_ids

    def get_cards_from_lists(self, list_ids: List[str]) -> List[Dict]:
        """
        Obtém todos os cards das listas especificadas.

        Args:
            list_ids: Lista de IDs das listas

        Returns:
            Lista de dicionários com informações dos cards
        """
        all_cards = []

        for list_id in list_ids:
            try:
                url = f"{self.base_url}/lists/{list_id}/cards"
                params = {
                    'key': self.api_key,
                    'token': self.token
                }

                response = requests.get(url, params=params)
                response.raise_for_status()

                cards = response.json()
                all_cards.extend(cards)
                print(f"✅ {len(cards)} cards obtidos da lista {list_id}")

            except requests.exceptions.RequestException as e:
                print(f"❌ ERRO ao buscar cards da lista {list_id}: {str(e)}")
                continue

        print(f"✅ Total de {len(all_cards)} cards coletados")
        return all_cards

    def parse_card_title(self, title: str) -> Optional[Tuple[datetime, float, str]]:
        """
        Faz o parsing do título do card.
        Formato esperado: "DD/MM/YY - R$VALOR - NOME"

        Args:
            title: Título do card

        Returns:
            Tupla (data, valor, nome) ou None se parsing falhar
        """
        try:
            # Remove espaços extras
            title = title.strip()

            # Split por "-"
            parts = [p.strip() for p in title.split('-')]

            if len(parts) < 3:
                print(f"⚠️ Formato inválido (menos de 3 partes): '{title}'")
                return None

            # Primeira parte: data
            date_str = parts[0].strip()
            date_obj = datetime.strptime(date_str, '%d/%m/%y')

            # Segunda parte: valor (R$791,36 ou R$6.136,28)
            value_str = parts[1].strip()
            # Remove "R$" e espaços
            value_str = re.sub(r'[R$\s]', '', value_str)

            # Verifica se há valor (trata caso "R$ - Nome" sem valor)
            if not value_str or value_str == '':
                print(f"⚠️ Card sem valor: '{title}'")
                return None

            # Remove pontos (separadores de milhar brasileiros)
            value_str = value_str.replace('.', '')
            # Substitui vírgula por ponto (separador decimal)
            value_str = value_str.replace(',', '.')
            value = float(value_str)

            # Terceira parte e seguintes: nome
            name = ' - '.join(parts[2:]).strip()

            return (date_obj, value, name)

        except Exception as e:
            print(f"⚠️ ERRO ao parsear card '{title}': {str(e)}")
            return None

    def parse_all_cards(self, cards: List[Dict]) -> pd.DataFrame:
        """
        Parseia TODOS os cards e retorna um DataFrame.

        Args:
            cards: Lista de dicionários com cards

        Returns:
            DataFrame com todos os cards parseados
        """
        parsed_cards = []

        print(f"🔍 Parseando {len(cards)} cards...")

        for card in cards:
            title = card['name']
            parsed = self.parse_card_title(title)

            if parsed:
                date_obj, value, name = parsed
                parsed_cards.append({
                    'data': date_obj,
                    'valor': value,
                    'nome': name,
                    'titulo_original': title
                })

        df = pd.DataFrame(parsed_cards)

        if not df.empty:
            df = df.sort_values('data')
            print(f"✅ {len(df)} cards parseados com sucesso")
        else:
            print("⚠️ Nenhum card foi parseado com sucesso")

        return df

    def filter_cards_by_date_range(self, df_all_cards: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Filtra DataFrame de cards pelo range de datas.

        Args:
            df_all_cards: DataFrame com todos os cards parseados
            start_date: Data inicial
            end_date: Data final

        Returns:
            DataFrame com os cards filtrados
        """
        if df_all_cards.empty:
            print("⚠️ Nenhum card para filtrar")
            return df_all_cards

        # Filtrar pelo range de datas
        df_filtered = df_all_cards[
            (df_all_cards['data'] >= start_date) &
            (df_all_cards['data'] <= end_date)
        ].copy()

        if not df_filtered.empty:
            print(f"✅ {len(df_filtered)} cards no período de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}")
        else:
            print("⚠️ Nenhum card encontrado no período especificado")

        return df_filtered

    def calculate_monthly_expenses(self, df_all_cards: pd.DataFrame, today: datetime) -> float:
        """
        Calcula os gastos totais do mês atual (do dia 01 até hoje).

        Args:
            df_all_cards: DataFrame com todos os cards parseados
            today: Data atual

        Returns:
            Total de gastos do mês atual
        """
        if df_all_cards.empty:
            return 0.0

        # Primeiro dia do mês atual
        first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Filtrar cards do mês atual (de 01 até hoje)
        df_month = df_all_cards[
            (df_all_cards['data'] >= first_day_of_month) &
            (df_all_cards['data'] <= today)
        ]

        total_month = df_month['valor'].sum()

        print(f"💰 Gastos do mês atual (01/{today.month:02d} até {today.strftime('%d/%m')}): R$ {total_month:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

        return total_month

    def calculate_daily_totals(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Calcula totais diários e saldo acumulado.

        Args:
            df: DataFrame com os cards
            start_date: Data inicial
            end_date: Data final

        Returns:
            DataFrame com totais por dia e saldo acumulado
        """
        # Criar range de todas as datas (incluindo dias sem movimentação)
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')

        # Agrupar por data e somar valores
        if not df.empty:
            daily_totals = df.groupby('data')['valor'].sum().reset_index()
            daily_totals.columns = ['data', 'total_saidas']
        else:
            daily_totals = pd.DataFrame(columns=['data', 'total_saidas'])

        # Criar DataFrame com todas as datas
        all_dates_df = pd.DataFrame({'data': date_range})

        # Merge para incluir dias sem movimentação
        result = all_dates_df.merge(daily_totals, on='data', how='left')
        result['total_saidas'] = result['total_saidas'].fillna(0)

        # Calcular saldo acumulado (saídas são negativas)
        result['saldo_acumulado'] = -result['total_saidas'].cumsum()

        # Formatar data para exibição
        result['data_formatada'] = result['data'].dt.strftime('%d/%m/%Y')
        result['dia_semana'] = result['data'].dt.day_name().map({
            'Monday': 'Seg', 'Tuesday': 'Ter', 'Wednesday': 'Qua',
            'Thursday': 'Qui', 'Friday': 'Sex', 'Saturday': 'Sáb', 'Sunday': 'Dom'
        })

        return result

    def generate_interactive_chart(self, df_daily: pd.DataFrame, monthly_expenses: float, today: datetime, output_path: str = None):
        """
        Gera gráfico HTML interativo com design moderno e minimalista.

        Args:
            df_daily: DataFrame com totais diários
            monthly_expenses: Total de gastos do mês atual
            today: Data atual
            output_path: Caminho para salvar o HTML (opcional)

        Returns:
            Figura Plotly gerada
        """
        # Criar figura com eixo secundário
        fig = make_subplots(
            rows=1, cols=1,
            specs=[[{"secondary_y": True}]]
        )

        # Labels simplificados para o eixo X
        x_labels = [f"{row['data_formatada']}<br><span style='font-size:11px; color:#8B95A5'>{row['dia_semana']}</span>"
                    for _, row in df_daily.iterrows()]

        # Barra de saídas diárias com gradiente moderno
        fig.add_trace(
            go.Bar(
                x=x_labels,
                y=df_daily['total_saidas'],
                name='Saídas do Dia',
                marker=dict(
                    color=df_daily['total_saidas'],
                    colorscale=[
                        [0, '#E8F4F8'],      # Azul muito claro
                        [0.5, '#4FB3D4'],    # Azul médio
                        [1, '#2A7A9B']       # Azul escuro
                    ],
                    line=dict(color='rgba(255,255,255,0.8)', width=1.5)
                ),
                text=df_daily['total_saidas'].apply(
                    lambda x: f"<b>R$ {x:,.2f}</b>".replace(',', 'X').replace('.', ',').replace('X', '.') if x > 0 else ''
                ),
                textposition='outside',
                textfont=dict(size=13, color='#1E293B', family='Inter, -apple-system, system-ui, sans-serif'),
                hovertemplate='<b>%{x}</b><br>' +
                              '<span style="font-size:14px">Saídas: <b>R$ %{y:,.2f}</b></span>' +
                              '<extra></extra>',
                width=0.65
            ),
            secondary_y=False
        )

        # Linha de saldo acumulado com estilo moderno
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=df_daily['saldo_acumulado'],
                name='Saldo Acumulado',
                mode='lines+markers',
                line=dict(
                    color='#DC2626',  # Vermelho moderno
                    width=3,
                    shape='spline'
                ),
                marker=dict(
                    size=10,
                    color='#DC2626',
                    symbol='circle',
                    line=dict(color='white', width=2)
                ),
                hovertemplate='<b>%{x}</b><br>' +
                              '<span style="font-size:14px">Saldo: <b>R$ %{y:,.2f}</b></span>' +
                              '<extra></extra>'
            ),
            secondary_y=True
        )

        # Calcular total do período (próximos 7 dias)
        total_periodo = df_daily['total_saidas'].sum()
        saldo_final = df_daily['saldo_acumulado'].iloc[-1]

        # Formatar valores
        monthly_fmt = f"{monthly_expenses:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        total_fmt = f"{total_periodo:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        saldo_fmt = f"{saldo_final:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        # Configurar layout moderno e minimalista com altura ajustada
        fig.update_layout(
            title={
                'text': (
                    f'<span style="font-size:28px; font-weight:600; color:#0F172A">Fluxo de Caixa</span><br>'
                    f'<span style="font-size:14px; color:#64748B; font-weight:400">Próximos 7 dias</span><br><br>'
                    f'<span style="font-size:16px; color:#DC2626; font-weight:600">'
                    f'Gastos do Mês Atual (01/{today.month:02d} até Hoje): R$ {monthly_fmt}</span><br><br>'
                    f'<span style="font-size:16px; color:#475569">'
                    f'Total do Período: <b style="color:#2A7A9B">R$ {total_fmt}</b> | '
                    f'Saldo Final: <b style="color:#DC2626">R$ {saldo_fmt}</b></span>'
                ),
                'x': 0.5,
                'xanchor': 'center',
                'y': 0.97,
                'yanchor': 'top',
                'font': {'family': 'Inter, -apple-system, system-ui, sans-serif'}
            },
            xaxis=dict(
                title='',
                showgrid=False,
                showline=True,
                linewidth=1,
                linecolor='#E2E8F0',
                tickfont=dict(size=12, color='#475569', family='Inter, sans-serif')
            ),
            yaxis=dict(
                title=dict(
                    text='Saídas Diárias',
                    font=dict(size=13, color='#64748B', family='Inter, sans-serif')
                ),
                showgrid=True,
                gridwidth=1,
                gridcolor='#F1F5F9',
                showline=False,
                tickfont=dict(size=11, color='#64748B'),
                tickformat=',.2f',
                tickprefix='R$ ',
                zeroline=True,
                zerolinewidth=1.5,
                zerolinecolor='#CBD5E1'
            ),
            yaxis2=dict(
                title=dict(
                    text='Saldo Acumulado',
                    font=dict(size=13, color='#64748B', family='Inter, sans-serif')
                ),
                showgrid=False,
                showline=False,
                tickfont=dict(size=11, color='#64748B'),
                tickformat=',.2f',
                tickprefix='R$ '
            ),
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor='white',
                font_size=13,
                font_family='Inter, sans-serif',
                bordercolor='#E2E8F0'
            ),
            height=700,  # Altura ajustada
            width=1400,  # Largura otimizada
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.12,
                xanchor="center",
                x=0.5,
                font=dict(size=13, color='#475569', family='Inter, sans-serif'),
                bgcolor='rgba(255,255,255,0.9)',
                bordercolor='#E2E8F0',
                borderwidth=1
            ),
            font=dict(family='Inter, -apple-system, system-ui, sans-serif'),
            plot_bgcolor='#FAFBFC',
            paper_bgcolor='#FFFFFF',
            margin=dict(t=240, b=90, l=80, r=80)  # Margem superior aumentada para o título
        )

        # Salvar HTML com configuração otimizada (apenas se output_path fornecido)
        if output_path:
            config = {
                'displayModeBar': True,
                'responsive': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'fluxo_caixa_{today.strftime("%Y%m%d")}',
                    'height': 700,
                    'width': 1400,
                    'scale': 2
                }
            }

            fig.write_html(output_path, config=config)
            print(f"✅ Gráfico salvo em: {output_path}")

        return fig

    def send_whatsapp_report(self, file_path: str, today: datetime) -> bool:
        """
        Envia o relatório HTML via WhatsApp Web (com confirmação do usuário).
        NOTA: Funcionalidade disponível apenas em ambiente local com GUI.

        Args:
            file_path: Caminho do arquivo HTML
            today: Data atual

        Returns:
            True se enviou com sucesso, False caso contrário
        """
        if not PYWHATKIT_AVAILABLE:
            print("\n⚠️ Envio via WhatsApp não disponível neste ambiente (requer GUI)")
            print("💡 Execute o script localmente para usar esta funcionalidade")
            return False

        try:
            print("\n" + "="*70)
            resposta = input("📱 Deseja enviar o relatório para o sócio via WhatsApp? (s/n): ").strip().lower()

            if resposta not in ['s', 'sim', 'yes', 'y']:
                print("⚠️ Envio cancelado. Relatório salvo localmente.")
                return False

            print("\n📤 Enviando relatório via WhatsApp...")
            print("⏳ Aguarde, isso pode levar alguns segundos...")
            print("⚠️ IMPORTANTE: O WhatsApp Web será aberto automaticamente. Não feche a janela!")

            # Número do sócio
            phone_number = "+5521991998872"

            # Mensagem que acompanha o arquivo
            message = f"📊 Fluxo de Caixa Atualizado - {today.strftime('%d/%m/%Y')}"

            # Enviar mensagem via WhatsApp Web
            # pywhatkit usa o formato: hora, minuto, tempo de espera
            now = datetime.now()
            hour = now.hour
            minute = now.minute + 2  # Envia em 2 minutos

            # Ajusta se os minutos passarem de 59
            if minute >= 60:
                minute = minute - 60
                hour = hour + 1

            # Enviar mensagem
            pwk.sendwhatmsg(phone_number, message, hour, minute, wait_time=15, tab_close=False)

            print("\n✅ Mensagem enviada com sucesso!")
            print("⚠️ ATENÇÃO: Você precisará anexar manualmente o arquivo HTML no WhatsApp Web")
            print(f"   Arquivo: {file_path}")
            print("   1. Na janela do WhatsApp Web que foi aberta, clique no ícone de anexo (📎)")
            print("   2. Selecione 'Documento'")
            print(f"   3. Navegue até: {file_path}")
            print("   4. Envie o arquivo")

            input("\nPressione ENTER após enviar o arquivo manualmente...")

            return True

        except Exception as e:
            print(f"\n❌ ERRO ao enviar pelo WhatsApp: {str(e)}")
            print("⚠️ Possíveis causas:")
            print("   - WhatsApp Web não está conectado")
            print("   - Navegador não abriu corretamente")
            print("   - Problema de conexão com a internet")
            print(f"\n💡 Você pode enviar manualmente o arquivo: {file_path}")
            return False

    def print_summary(self, df_daily: pd.DataFrame, df_cards: pd.DataFrame, df_all_cards: pd.DataFrame, monthly_expenses: float, today: datetime):
        """
        Imprime resumo no console.

        Args:
            df_daily: DataFrame com totais diários
            df_cards: DataFrame com os cards individuais filtrados
            df_all_cards: DataFrame com TODOS os cards das listas
            monthly_expenses: Total de gastos do mês atual
            today: Data atual
        """
        print("\n" + "="*70)
        print("📊 RESUMO DA ANÁLISE DE FLUXO DE CAIXA")
        print("="*70)

        # Mostrar estatísticas de coleta
        if df_all_cards is not None and not df_all_cards.empty:
            print(f"\n📦 Total de cards nas listas: {len(df_all_cards)}")
            print(f"🎯 Cards no período de 7 dias: {len(df_cards)}")

            # Datas dos cards nas listas
            data_min = df_all_cards['data'].min().strftime('%d/%m/%Y')
            data_max = df_all_cards['data'].max().strftime('%d/%m/%Y')
            print(f"📅 Range de datas nas listas: {data_min} até {data_max}")

        # Mostrar gastos do mês atual
        monthly_fmt = f"R$ {monthly_expenses:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        print(f"\n💰 GASTOS DO MÊS ATUAL (01/{today.month:02d} até {today.strftime('%d/%m')}): {monthly_fmt}")

        print("\n📅 TOTAL POR DIA (Próximos 7 dias):")
        print("-"*70)
        for _, row in df_daily.iterrows():
            valor_fmt = f"R$ {row['total_saidas']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            saldo_fmt = f"R$ {row['saldo_acumulado']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            print(f"{row['data_formatada']} ({row['dia_semana']}): {valor_fmt:>15} | Saldo: {saldo_fmt:>15}")

        print("\n" + "-"*70)
        total_periodo = df_daily['total_saidas'].sum()
        total_fmt = f"R$ {total_periodo:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        print(f"💰 TOTAL CONSOLIDADO DO PERÍODO (7 dias): {total_fmt}")

        saldo_final = df_daily['saldo_acumulado'].iloc[-1]
        saldo_final_fmt = f"R$ {saldo_final:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        print(f"📉 SALDO FINAL ACUMULADO: {saldo_final_fmt}")

        print("\n📋 DETALHAMENTO DOS CARDS NO PERÍODO:")
        print("-"*70)
        if not df_cards.empty:
            for _, card in df_cards.iterrows():
                valor_fmt = f"R$ {card['valor']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                print(f"{card['data'].strftime('%d/%m/%Y')}: {valor_fmt:>12} - {card['nome']}")
        else:
            print("Nenhum card encontrado no período.")

        print("="*70 + "\n")

    def run_analysis(self, board_url: str, days_ahead: int = 7):
        """
        Executa a análise completa.

        Args:
            board_url: URL do board do Trello
            days_ahead: Número de dias à frente para análise
        """
        print("🚀 Iniciando análise de fluxo de caixa...")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        print(f"📅 Data de hoje: {today.strftime('%d/%m/%Y')}")
        print(f"📆 Período de análise: {days_ahead} dias\n")

        # 1. Carregar credenciais
        if not self.load_credentials():
            return

        # 2. Definir datas
        end_date = today + timedelta(days=days_ahead - 1)

        print(f"📅 Período (próximos 7 dias): {today.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n")

        # 3. Obter listas do board
        lists = self.get_board_lists(board_url)
        if not lists:
            return

        # 4. Identificar listas dos meses necessários (incluindo mês atual para calcular gastos mensais)
        first_day_of_month = today.replace(day=1)
        # Precisamos das listas desde o mês atual até o mês que contém end_date
        list_ids = self.identify_month_lists(lists, first_day_of_month, end_date)
        if not list_ids:
            return

        print()

        # 5. Obter cards das listas
        cards = self.get_cards_from_lists(list_ids)
        if not cards:
            print("⚠️ Nenhum card encontrado nas listas")
            return

        print()

        # 6. Parsear TODOS os cards das listas
        df_all_cards = self.parse_all_cards(cards)
        if df_all_cards.empty:
            print("⚠️ Nenhum card foi parseado com sucesso")
            return

        print()

        # 7. Calcular gastos do mês atual (do dia 01 até hoje)
        monthly_expenses = self.calculate_monthly_expenses(df_all_cards, today)

        # 8. Filtrar cards pelo período de 7 dias
        df_cards = self.filter_cards_by_date_range(df_all_cards, today, end_date)
        if df_cards.empty:
            print("⚠️ Nenhum card encontrado no período especificado (próximos 7 dias)")
            # Não retornamos aqui, pois queremos mostrar os gastos mensais mesmo sem cards nos próximos 7 dias

        print()

        # 9. Calcular totais diários
        df_daily = self.calculate_daily_totals(df_cards, today, end_date)

        # 10. Gerar nome do arquivo com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"fluxo_caixa_{timestamp}.html"
        output_path = self.outputs_dir / output_filename

        # 11. Gerar gráfico
        self.generate_interactive_chart(df_daily, monthly_expenses, today, str(output_path))

        # 12. Imprimir resumo
        self.print_summary(df_daily, df_cards, df_all_cards, monthly_expenses, today)

        print(f"✅ Análise concluída! Gráfico disponível em: {output_path}")

        # 13. Perguntar sobre envio via WhatsApp
        self.send_whatsapp_report(str(output_path), today)


def main():
    """Função principal."""
    try:
        # Configurações
        BOARD_URL = "https://trello.com/b/WgSarYPK/contas-a-pagar-25"
        DAYS_AHEAD = 7

        # Criar analisador e executar
        analyzer = TrelloCashFlowAnalyzer()
        analyzer.run_analysis(BOARD_URL, DAYS_AHEAD)

    except KeyboardInterrupt:
        print("\n⚠️ Análise interrompida pelo usuário")
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
