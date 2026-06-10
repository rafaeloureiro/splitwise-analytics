"""
Aplicação de Análise de Fluxo de Caixa do Trello - v2
Melhorias: seletor de período, KPIs, formatação de datas,
gráfico de fornecedores, cache, tratamento de erros robusto.
"""

import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ──────────────────────────────────────────────
# CLASSE PRINCIPAL
# ──────────────────────────────────────────────

class TrelloCashFlowAnalyzer:
    def __init__(self):
        self.base_url = "https://api.trello.com/1"
        self.api_key = None
        self.token = None

    def load_credentials(self) -> bool:
        self.api_key = st.secrets.get("TRELLO_API_KEY")
        self.token = st.secrets.get("TRELLO_TOKEN")
        if not self.api_key or not self.token:
            st.error("❌ Credenciais TRELLO_API_KEY ou TRELLO_TOKEN não encontradas nos Secrets do Streamlit.")
            return False
        return True

    def extract_board_id(self, board_url: str) -> str:
        match = re.search(r'/b/([a-zA-Z0-9]+)/', board_url)
        if match:
            return match.group(1)
        raise ValueError(f"URL do board inválida: {board_url}")

    # ── Cache de 10 min para não bater na API a cada rerun ──
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_lists(_self, board_id: str) -> List[Dict]:
        url = f"{_self.base_url}/boards/{board_id}/lists"
        params = {"key": _self.api_key, "token": _self.token}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_cards(_self, list_id: str) -> List[Dict]:
        url = f"{_self.base_url}/lists/{list_id}/cards"
        params = {"key": _self.api_key, "token": _self.token}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_board_lists(self, board_url: str) -> List[Dict]:
        try:
            board_id = self.extract_board_id(board_url)
            return self._fetch_lists(board_id)
        except Exception as e:
            st.error(f"❌ Erro ao buscar listas do Trello: {e}")
            return []

    def identify_month_lists(self, lists: List[Dict], start_date: datetime, end_date: datetime) -> List[str]:
        months_pt = {
            1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
            5: "maio", 6: "junho", 7: "julho", 8: "agosto",
            9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
        }
        months_needed = set()
        current = start_date
        while current <= end_date:
            months_needed.add((months_pt[current.month], str(current.year)[2:]))
            current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)

        list_ids = []
        for lst in lists:
            name = lst["name"].lower().strip()
            for month_name, year_short in months_needed:
                if re.search(rf"{month_name}\s*/\s*{year_short}", name):
                    list_ids.append(lst["id"])
                    break
        return list_ids

    def get_cards_from_lists(self, list_ids: List[str]) -> List[Dict]:
        all_cards = []
        for list_id in list_ids:
            try:
                all_cards.extend(self._fetch_cards(list_id))
            except Exception:
                continue
        return all_cards

    def parse_card_title(self, title: str) -> Tuple[Optional[Tuple], Optional[str]]:
        """
        Retorna (parsed_tuple, None) em caso de sucesso,
        ou (None, motivo_do_erro) em caso de falha.
        """
        title = title.strip()
        parts = [p.strip() for p in title.split("-", 2)]

        if len(parts) < 3:
            return None, "Formato inválido — esperado: DD/MM/AA - R$ valor - nome"

        # Data
        try:
            date_obj = datetime.strptime(parts[0].strip(), "%d/%m/%y")
        except ValueError:
            return None, f"Data inválida: '{parts[0].strip()}' — use DD/MM/AA"

        # Valor
        value_str = re.sub(r"[R$\s]", "", parts[1].strip()).replace(".", "").replace(",", ".")
        if not value_str:
            return None, "Valor ausente ou ilegível"
        try:
            value = float(value_str)
        except ValueError:
            return None, f"Valor inválido: '{parts[1].strip()}'"

        name = parts[2].strip()
        return (date_obj, value, name), None

    def parse_all_cards(self, cards: List[Dict]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Retorna (df_validos, df_invalidos).
        df_invalidos contém titulo_original e motivo do erro.
        """
        validos, invalidos = [], []

        for card in cards:
            title = card["name"]
            parsed, error = self.parse_card_title(title)
            if parsed:
                date_obj, value, name = parsed
                validos.append({
                    "data": date_obj,
                    "valor": value,
                    "nome": name,
                    "titulo_original": title,
                })
            else:
                invalidos.append({
                    "titulo_original": title,
                    "motivo": error,
                })

        df_validos = pd.DataFrame(validos)
        if not df_validos.empty:
            df_validos = df_validos.sort_values("data").reset_index(drop=True)

        df_invalidos = pd.DataFrame(invalidos)
        return df_validos, df_invalidos

    def filter_by_range(self, df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
        if df.empty:
            return df
        return df[(df["data"] >= start) & (df["data"] <= end)].copy()

    def calculate_monthly_expenses(self, df: pd.DataFrame, today: datetime) -> float:
        if df.empty:
            return 0.0
        first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return df[(df["data"] >= first) & (df["data"] <= today)]["valor"].sum()

    def calculate_daily_totals(self, df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
        date_range = pd.date_range(start=start, end=end, freq="D")
        if not df.empty:
            daily = df.groupby("data")["valor"].sum().reset_index()
            daily.columns = ["data", "total_saidas"]
        else:
            daily = pd.DataFrame(columns=["data", "total_saidas"])

        result = pd.DataFrame({"data": date_range}).merge(daily, on="data", how="left")
        result["total_saidas"] = result["total_saidas"].fillna(0)
        result["saldo_acumulado"] = -result["total_saidas"].cumsum()
        result["data_formatada"] = result["data"].dt.strftime("%d/%m/%Y")
        result["dia_semana"] = result["data"].dt.day_name().map({
            "Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua",
            "Thursday": "Qui", "Friday": "Sex", "Saturday": "Sáb", "Sunday": "Dom",
        })
        return result

    def top_suppliers_chart(self, df: pd.DataFrame) -> go.Figure:
        """Gráfico de barras horizontais com top fornecedores/categorias."""
        if df.empty:
            return go.Figure()

        supplier_totals = (
            df.groupby("nome")["valor"]
            .sum()
            .sort_values(ascending=True)
            .tail(12)  # top 12
        )

        fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        fig = go.Figure(go.Bar(
            x=supplier_totals.values,
            y=supplier_totals.index,
            orientation="h",
            marker=dict(
                color=supplier_totals.values,
                colorscale=[[0, "#C9E8F4"], [1, "#2A7A9B"]],
            ),
            text=[fmt(v) for v in supplier_totals.values],
            textposition="outside",
        ))
        fig.update_layout(
            title="Gastos por Fornecedor / Categoria",
            xaxis=dict(title="Total (R$)", tickprefix="R$ ", showgrid=True, gridcolor="#F0F2F5"),
            yaxis=dict(title=""),
            height=420,
            plot_bgcolor="#FAFBFC",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=20, r=80, t=50, b=20),
        )
        return fig

    def generate_flow_chart(self, df_daily: pd.DataFrame, monthly_expenses: float) -> go.Figure:
        fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])

        x_labels = [
            f"{row['data_formatada']}<br><span style='font-size:11px;color:#8B95A5'>{row['dia_semana']}</span>"
            for _, row in df_daily.iterrows()
        ]

        fmt = lambda v: f"<b>R$ {v:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", ".")

        fig.add_trace(
            go.Bar(
                x=x_labels,
                y=df_daily["total_saidas"],
                name="Saídas do Dia",
                marker=dict(
                    color=df_daily["total_saidas"],
                    colorscale=[[0, "#E8F4F8"], [0.5, "#4FB3D4"], [1, "#2A7A9B"]],
                ),
                text=[fmt(v) if v > 0 else "" for v in df_daily["total_saidas"]],
                textposition="outside",
                width=0.65,
            ),
            secondary_y=False,
        )

        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=df_daily["saldo_acumulado"],
                name="Saldo Acumulado",
                mode="lines+markers",
                line=dict(color="#DC2626", width=3, shape="spline"),
                marker=dict(size=10, color="#DC2626", line=dict(color="white", width=2)),
            ),
            secondary_y=True,
        )

        monthly_fmt = f"{monthly_expenses:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        fig.update_layout(
            title=f"Gastos do Mês Atual: R$ {monthly_fmt}",
            xaxis=dict(showgrid=False),
            yaxis=dict(title="Saídas Diárias (R$)", tickprefix="R$ "),
            yaxis2=dict(title="Saldo Acumulado (R$)", tickprefix="R$ "),
            height=520,
            plot_bgcolor="#FAFBFC",
            paper_bgcolor="#FFFFFF",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        return fig


# ──────────────────────────────────────────────
# HELPERS DE FORMATAÇÃO
# ──────────────────────────────────────────────

def fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ──────────────────────────────────────────────
# APP STREAMLIT
# ──────────────────────────────────────────────

BOARD_URL = "https://trello.com/b/WgSarYPK/contas-a-pagar-25"

st.set_page_config(page_title="Fluxo de Caixa — Contas a Pagar", layout="wide")
st.title("📊 Fluxo de Caixa — Contas a Pagar")

analyzer = TrelloCashFlowAnalyzer()
if not analyzer.load_credentials():
    st.stop()

# ── Seletor de período (melhoria #2) ──────────────────────────────
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

with st.sidebar:
    st.header("⚙️ Configurações")
    date_range = st.date_input(
        "Período de análise",
        value=(today.date(), (today + timedelta(days=6)).date()),
        min_value=(today - timedelta(days=365)).date(),
        max_value=(today + timedelta(days=90)).date(),
        help="Selecione o intervalo de datas para visualizar os gastos.",
    )
    st.caption("💡 O cache é renovado a cada 10 minutos. Para forçar atualização, pressione **F5**.")

# Garante que o usuário selecionou as duas datas
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date = datetime.combine(date_range[0], datetime.min.time())
    end_date = datetime.combine(date_range[1], datetime.min.time())
else:
    start_date = today
    end_date = today + timedelta(days=6)

# ── Busca de dados ────────────────────────────────────────────────
with st.spinner("Conectando ao Trello…"):
    lists = analyzer.get_board_lists(BOARD_URL)

if not lists:
    st.warning("Nenhuma lista encontrada no board.")
    st.stop()

first_day_of_month = today.replace(day=1)
list_ids = analyzer.identify_month_lists(lists, first_day_of_month, end_date)
cards = analyzer.get_cards_from_lists(list_ids)

if not cards:
    st.warning("Nenhum card encontrado nas listas do período.")
    st.stop()

df_all, df_invalidos = analyzer.parse_all_cards(cards)
df_period = analyzer.filter_by_range(df_all, start_date, end_date)
df_daily = analyzer.calculate_daily_totals(df_period, start_date, end_date)
monthly_expenses = analyzer.calculate_monthly_expenses(df_all, today)

# ── KPIs (melhoria #3) ────────────────────────────────────────────
next7_total = df_period["valor"].sum() if not df_period.empty else 0.0
biggest_expense = df_period["valor"].max() if not df_period.empty else 0.0
biggest_name = (
    df_period.loc[df_period["valor"].idxmax(), "nome"]
    if not df_period.empty else "—"
)

col1, col2, col3 = st.columns(3)
col1.metric("💰 Total gasto no mês", fmt_brl(monthly_expenses))
col2.metric("📅 Total no período selecionado", fmt_brl(next7_total))
col3.metric(
    "🔺 Maior gasto individual",
    fmt_brl(biggest_expense),
    help=f"Referente a: {biggest_name}",
)

st.divider()

# ── Gráfico de fluxo ──────────────────────────────────────────────
fig_flow = analyzer.generate_flow_chart(df_daily, monthly_expenses)
st.plotly_chart(fig_flow, use_container_width=True)

# ── Gráfico de fornecedores (melhoria #5) ────────────────────────
if not df_period.empty:
    fig_suppliers = analyzer.top_suppliers_chart(df_period)
    st.plotly_chart(fig_suppliers, use_container_width=True)

st.divider()

# ── Tabela detalhada (melhoria #4 — data formatada) ──────────────
st.subheader("📋 Detalhamento dos Cards")

if not df_period.empty:
    df_display = df_period[["data", "valor", "nome"]].copy()
    df_display["data"] = df_display["data"].dt.strftime("%d/%m/%Y")
    df_display = df_display.rename(columns={"data": "Data", "valor": "Valor (R$)", "nome": "Descrição"})
    df_display["Valor (R$)"] = df_display["Valor (R$)"].apply(
        lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("Nenhum card no período selecionado.")

# ── Cards inválidos (melhoria #7) ─────────────────────────────────
if not df_invalidos.empty:
    with st.expander(f"⚠️ {len(df_invalidos)} card(s) com formato inválido — clique para ver"):
        st.caption(
            "Estes cards foram ignorados pois não seguem o padrão esperado: "
            "`DD/MM/AA - R$ valor - descrição`"
        )
        df_inv_display = df_invalidos.rename(
            columns={"titulo_original": "Título no Trello", "motivo": "Motivo do Erro"}
        )
        st.dataframe(df_inv_display, use_container_width=True, hide_index=True)
