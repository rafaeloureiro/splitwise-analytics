"""
Aplicação de Análise de Fluxo de Caixa do Trello - Adaptada para Streamlit Cloud
"""

import os
import re
import sys
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

class TrelloCashFlowAnalyzer:
    def __init__(self):
        self.base_url = "https://api.trello.com/1"
        self.api_key = None
        self.token = None

    def load_credentials(self) -> bool:
        # Puxa direto dos Secrets do Streamlit que você configurou
        self.api_key = st.secrets.get("TRELLO_API_KEY")
        self.token = st.secrets.get("TRELLO_TOKEN")
        
        if not self.api_key or not self.token:
            st.error("❌ ERRO: Credenciais TRELLO_API_KEY ou TRELLO_TOKEN não encontradas nos Secrets do Streamlit.")
            return False
        return True

    def extract_board_id(self, board_url: str) -> str:
        match = re.search(r'/b/([a-zA-Z0-9]+)/', board_url)
        if match:
            return match.group(1)
        raise ValueError(f"URL do board inválida: {board_url}")

    def get_board_lists(self, board_url: str) -> List[Dict]:
        try:
            board_id = self.extract_board_id(board_url)
            url = f"{self.base_url}/boards/{board_id}/lists"
            params = {'key': self.api_key, 'token': self.token}
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"❌ Erro ao buscar listas: {str(e)}")
            return []

    def identify_month_lists(self, lists: List[Dict], start_date: datetime, end_date: datetime) -> List[str]:
        months_pt = {
            1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }
        months_needed = set()
        current_date = start_date
        while current_date <= end_date:
            month_name = months_pt[current_date.month].lower()
            year_short = str(current_date.year)[2:]
            months_needed.add((month_name, year_short))
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        list_ids = []
        for list_obj in lists:
            list_name = list_obj['name'].lower().strip()
            for month_name, year_short in months_needed:
                pattern = rf'{month_name}\s*/\s*{year_short}'
                if re.search(pattern, list_name):
                    list_ids.append(list_obj['id'])
                    break
        return list_ids

    def get_cards_from_lists(self, list_ids: List[str]) -> List[Dict]:
        all_cards = []
        for list_id in list_ids:
            try:
                url = f"{self.base_url}/lists/{list_id}/cards"
                params = {'key': self.api_key, 'token': self.token}
                response = requests.get(url, params=params)
                response.raise_for_status()
                all_cards.extend(response.json())
            except Exception:
                continue
        return all_cards

    def parse_card_title(self, title: str) -> Optional[Tuple[datetime, float, str]]:
        try:
            title = title.strip()
            parts = [p.strip() for p in title.split('-')]
            if len(parts) < 3:
                return None
            date_str = parts[0].strip()
            date_obj = datetime.strptime(date_str, '%d/%m/%y')
            value_str = parts[1].strip()
            value_str = re.sub(r'[R$\s]', '', value_str)
            if not value_str:
                return None
            value_str = value_str.replace('.', '').replace(',', '.')
            value = float(value_str)
            name = ' - '.join(parts[2:]).strip()
            return (date_obj, value, name)
        except Exception:
            return None

    def parse_all_cards(self, cards: List[Dict]) -> pd.DataFrame:
        parsed_cards = []
        for card in cards:
            title = card['name']
            parsed = self.parse_card_title(title)
            if parsed:
                date_obj, value, name = parsed
                parsed_cards.append({'data': date_obj, 'valor': value, 'nome': name, 'titulo_original': title})
        df = pd.DataFrame(parsed_cards)
        if not df.empty:
            df = df.sort_values('data')
        return df

    def filter_cards_by_date_range(self, df_all_cards: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        if df_all_cards.empty:
            return df_all_cards
        return df_all_cards[(df_all_cards['data'] >= start_date) & (df_all_cards['data'] <= end_date)].copy()

    def calculate_monthly_expenses(self, df_all_cards: pd.DataFrame, today: datetime) -> float:
        if df_all_cards.empty:
            return 0.0
        first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        df_month = df_all_cards[(df_all_cards['data'] >= first_day_of_month) & (df_all_cards['data'] <= today)]
        return df_month['valor'].sum()

    def calculate_daily_totals(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        if not df.empty:
            daily_totals = df.groupby('data')['valor'].sum().reset_index()
            daily_totals.columns = ['data', 'total_saidas']
        else:
            daily_totals = pd.DataFrame(columns=['data', 'total_saidas'])
        all_dates_df = pd.DataFrame({'data': date_range})
        result = all_dates_df.merge(daily_totals, on='data', how='left')
        result['total_saidas'] = result['total_saidas'].fillna(0)
        result['saldo_acumulado'] = -result['total_saidas'].cumsum()
        result['data_formatada'] = result['data'].dt.strftime('%d/%m/%Y')
        result['dia_semana'] = result['data'].dt.day_name().map({
            'Monday': 'Seg', 'Tuesday': 'Ter', 'Wednesday': 'Qua',
            'Thursday': 'Qui', 'Friday': 'Sex', 'Saturday': 'Sáb', 'Sunday': 'Dom'
        })
        return result

    def generate_interactive_chart(self, df_daily: pd.DataFrame, monthly_expenses: float, today: datetime):
        fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
        x_labels = [f"{row['data_formatada']}<br><span style='font-size:11px; color:#8B95A5'>{row['dia_semana']}</span>" for _, row in df_daily.iterrows()]

        fig.add_trace(
            go.Bar(
                x=x_labels, y=df_daily['total_saidas'], name='Saídas do Dia',
                marker=dict(color=df_daily['total_saidas'], colorscale=[[0, '#E8F4F8'], [0.5, '#4FB3D4'], [1, '#2A7A9B']]),
                text=df_daily['total_saidas'].apply(lambda x: f"<b>R$ {x:,.2f}</b>".replace(',', 'X').replace('.', ',').replace('X', '.') if x > 0 else ''),
                textposition='outside', width=0.65
            ),
            secondary_y=False
        )

        fig.add_trace(
            go.Scatter(
                x=x_labels, y=df_daily['saldo_acumulado'], name='Saldo Acumulado', mode='lines+markers',
                line=dict(color='#DC2626', width=3, shape='spline'),
                marker=dict(size=10, color='#DC2626', line=dict(color='white', width=2))
            ),
            secondary_y=True
        )

        monthly_fmt = f"{monthly_expenses:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        fig.update_layout(
            title=f"Gastos do Mês Atual: R$ {monthly_fmt}",
            xaxis=dict(showgrid=False),
            yaxis=dict(title='Saídas Diárias', tickprefix='R$ '),
            yaxis2=dict(title='Saldo Acumulado', tickprefix='R$ '),
            height=600, plot_bgcolor='#FAFBFC', paper_bgcolor='#FFFFFF'
        )
        return fig

# --- EXECUÇÃO DO STREAMLIT ---
st.set_page_config(page_title="Fluxo de Caixa Trello - Nov/25", layout="wide")
st.title("📊 Painel de Teste: Versão Novembro/2025")

BOARD_URL = "https://trello.com/b/WgSarYPK/contas-a-pagar-25"
analyzer = TrelloCashFlowAnalyzer()

if analyzer.load_credentials():
    with st.spinner("Conectando ao Trello e calculando dados..."):
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today + timedelta(days=6)
        
        lists = analyzer.get_board_lists(BOARD_URL)
        if lists:
            first_day_of_month = today.replace(day=1)
            list_ids = analyzer.identify_month_lists(lists, first_day_of_month, end_date)
            cards = analyzer.get_cards_from_lists(list_ids)
            
            if cards:
                df_all_cards = analyzer.parse_all_cards(cards)
                monthly_expenses = analyzer.calculate_monthly_expenses(df_all_cards, today)
                df_cards = analyzer.filter_cards_by_date_range(df_all_cards, today, end_date)
                df_daily = analyzer.calculate_daily_totals(df_cards, today, end_date)
                
                # Renderiza o gráfico direto na página web do Streamlit!
                fig = analyzer.generate_interactive_chart(df_daily, monthly_expenses, today)
                st.plotly_chart(fig, use_container_width=True)
                
                # Mostra a tabelinha de detalhes logo abaixo
                st.subheader("📋 Detalhamento dos Cards vindo do Trello")
                if not df_cards.empty:
                    st.dataframe(df_cards[['data', 'valor', 'nome']])
                else:
                    st.info("Nenhum card agendado para os próximos 7 dias.")
            else:
                st.warning("Nenhum card encontrado nas listas do Trello.")
