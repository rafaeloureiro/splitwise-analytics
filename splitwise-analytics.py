import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json
import time

# Configuração da página
st.set_page_config(
    page_title="Dashboard Splitwise com IA",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Categorias com emojis
CATEGORIAS = {
    "🏠 Moradia": ["aluguel", "condomínio", "iptu", "seguro residencial"],
    "💡 Contas": ["luz", "água", "gás", "internet", "telefone", "energia elétrica"],
    "🛒 Mercado": ["supermercado", "feira", "açougue", "padaria", "hortifruti"],
    "🍽️ Alimentação": ["restaurante", "lanche", "delivery", "ifood", "uber eats", "jantar", "almoço"],
    "🚗 Transporte": ["uber", "combustível", "gasolina", "estacionamento", "ônibus", "metrô"],
    "🏥 Saúde": ["farmácia", "médico", "dentista", "exame", "remédio", "consulta"],
    "🎉 Lazer": ["cinema", "show", "teatro", "viagem", "passeio", "festa", "bar"],
    "🏡 Casa": ["móveis", "decoração", "reforma", "manutenção", "limpeza"],
    "👤 Pessoal": ["roupa", "cabelo", "estética", "academia", "beleza"],
    "💻 Tecnologia": ["eletrônico", "streaming", "netflix", "spotify", "software"],
    "🐾 Pet": ["veterinário", "ração", "pet shop", "banho e tosa"],
    "📦 Outros": []
}

CATEGORIA_NOMES = list(CATEGORIAS.keys())

# Função de categorização por palavras-chave (fallback)
def categorizar_por_palavras_chave(descricao: str) -> Tuple[str, float]:
    """Categoriza descrição usando palavras-chave como fallback"""
    descricao_lower = descricao.lower()

    for categoria, palavras in CATEGORIAS.items():
        for palavra in palavras:
            if palavra in descricao_lower:
                return categoria, 0.6  # Confiança média para fallback

    return "📦 Outros", 0.3  # Baixa confiança para categoria genérica

# Cache para requisições da API
@st.cache_data(ttl=1800)
def buscar_grupos(api_key: str) -> List[Dict]:
    """Busca grupos do Splitwise"""
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            "https://secure.splitwise.com/api/v3.0/get_groups",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("groups", [])
    except Exception as e:
        st.error(f"Erro ao buscar grupos: {str(e)}")
        return []

@st.cache_data(ttl=1800)
def buscar_despesas(api_key: str, group_id: int, meses: int) -> List[Dict]:
    """Busca despesas do Splitwise"""
    try:
        data_inicio = datetime.now() - timedelta(days=meses * 30)
        headers = {"Authorization": f"Bearer {api_key}"}

        params = {
            "group_id": group_id,
            "dated_after": data_inicio.strftime("%Y-%m-%d"),
            "limit": 1000
        }

        response = requests.get(
            "https://secure.splitwise.com/api/v3.0/get_expenses",
            headers=headers,
            params=params,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        # Filtrar pagamentos
        despesas = [e for e in data.get("expenses", []) if not e.get("payment", False)]
        return despesas
    except Exception as e:
        st.error(f"Erro ao buscar despesas: {str(e)}")
        return []

def categorizar_com_groq(descricoes: List[str], api_key: str) -> List[Dict]:
    """Categoriza descrições usando Groq API"""
    try:
        prompt = f"""Você é um assistente especializado em categorizar despesas financeiras.

Categorias disponíveis:
{', '.join([c.split(' ', 1)[1] for c in CATEGORIA_NOMES])}

Analise as seguintes descrições de despesas e retorne um JSON array com objetos contendo:
- "descricao": a descrição original
- "categoria": a categoria (apenas o nome, sem emoji)
- "confianca": número entre 0 e 1 indicando confiança

Descrições:
{json.dumps(descricoes, ensure_ascii=False)}

IMPORTANTE: Retorne APENAS o JSON array, sem markdown, sem explicações, sem blocos de código."""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4096
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        resultado = response.json()
        texto_resposta = resultado["choices"][0]["message"]["content"].strip()

        # Remover markdown se presente
        if texto_resposta.startswith("```"):
            linhas = texto_resposta.split("\n")
            texto_resposta = "\n".join(linhas[1:-1])

        categorizacoes = json.loads(texto_resposta)

        # Adicionar emojis às categorias
        for cat in categorizacoes:
            nome_sem_emoji = cat["categoria"]
            for cat_completa in CATEGORIA_NOMES:
                if nome_sem_emoji in cat_completa:
                    cat["categoria"] = cat_completa
                    break

        return categorizacoes
    except Exception as e:
        st.warning(f"Erro na categorização com IA: {str(e)}. Usando fallback.")
        return []

def processar_despesas(despesas: List[Dict], groq_api_key: str) -> pd.DataFrame:
    """Processa despesas e categoriza com IA"""
    if not despesas:
        return pd.DataFrame()

    dados = []
    descricoes_para_categorizar = []
    indices_map = {}

    # Preparar dados
    for i, despesa in enumerate(despesas):
        descricao = despesa.get("description", "Sem descrição")
        custo = float(despesa.get("cost", 0))
        data = despesa.get("date", "")

        dados.append({
            "descricao": descricao,
            "valor": custo,
            "data": pd.to_datetime(data) if data else None,
            "categoria": None,
            "confianca": None
        })

        descricoes_para_categorizar.append(descricao)
        indices_map[descricao] = i

    # Categorizar em lotes
    progress_bar = st.progress(0)
    status_text = st.empty()

    batch_size = 50
    total_batches = (len(descricoes_para_categorizar) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(descricoes_para_categorizar), batch_size):
        batch = descricoes_para_categorizar[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        status_text.text(f"Categorizando lote {batch_num}/{total_batches}...")

        # Tentar categorizar com Groq
        categorizacoes = categorizar_com_groq(batch, groq_api_key)

        if categorizacoes:
            for cat in categorizacoes:
                idx = indices_map.get(cat["descricao"])
                if idx is not None:
                    dados[idx]["categoria"] = cat["categoria"]
                    dados[idx]["confianca"] = cat["confianca"]
        else:
            # Fallback para palavras-chave
            for desc in batch:
                idx = indices_map[desc]
                categoria, confianca = categorizar_por_palavras_chave(desc)
                dados[idx]["categoria"] = categoria
                dados[idx]["confianca"] = confianca

        progress = (batch_idx + len(batch)) / len(descricoes_para_categorizar)
        progress_bar.progress(progress)

        # Rate limiting
        time.sleep(0.5)

    progress_bar.empty()
    status_text.empty()

    df = pd.DataFrame(dados)

    # Adicionar colunas auxiliares
    df["mes"] = df["data"].dt.to_period("M").astype(str)
    df["status_confianca"] = df["confianca"].apply(
        lambda x: "Alta (≥80%)" if x >= 0.8 else "Média (50-79%)" if x >= 0.5 else "Baixa (<50%)"
    )
    df["confianca_percentual"] = (df["confianca"] * 100).round(1)

    # Colunas formatadas para exibição
    df["data_formatada"] = df["data"].dt.strftime("%d/%m/%Y")
    df["valor_formatado"] = df["valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    df["confianca_formatada"] = df["confianca_percentual"].apply(lambda x: f"{x}%")

    return df

# Interface principal
def main():
    st.title("💰 Dashboard Splitwise com Categorização por IA")
    st.markdown("Análise inteligente dos seus gastos usando Groq AI (Llama 3.3)")

    # Sidebar para configurações
    with st.sidebar:
        st.header("⚙️ Configurações")

        # API Keys
        st.subheader("🔑 API Keys")

        # Tentar obter das secrets
        splitwise_api_key = st.text_input(
            "Splitwise API Key",
            value=st.secrets.get("SPLITWISE_API_KEY", ""),
            type="password",
            help="Obtenha em https://secure.splitwise.com/apps"
        )

        groq_api_key = st.text_input(
            "Groq API Key",
            value=st.secrets.get("GROQ_API_KEY", ""),
            type="password",
            help="Obtenha em https://console.groq.com/ (100% GRATUITO)"
        )

        if not splitwise_api_key or not groq_api_key:
            st.warning("⚠️ Configure as API Keys para continuar")
            st.stop()

        st.divider()

        # Seleção de grupo
        st.subheader("👥 Grupo")
        grupos = buscar_grupos(splitwise_api_key)

        if not grupos:
            st.error("Nenhum grupo encontrado")
            st.stop()

        opcoes_grupos = {g["name"]: g["id"] for g in grupos}
        grupo_selecionado = st.selectbox(
            "Selecione o grupo",
            options=list(opcoes_grupos.keys())
        )
        grupo_id = opcoes_grupos[grupo_selecionado]

        # Período
        st.subheader("📅 Período")
        meses = st.slider(
            "Meses para análise",
            min_value=3,
            max_value=24,
            value=6,
            help="Quantidade de meses para buscar despesas"
        )

        st.divider()

        # Botão para processar
        processar = st.button("🔄 Processar Despesas", type="primary", use_container_width=True)

        # Exibir última atualização
        if "ultima_atualizacao" in st.session_state:
            st.caption(f"🕒 Última atualização: {st.session_state['ultima_atualizacao']}")

    # Área principal
    if processar:
        with st.spinner("Buscando despesas..."):
            despesas = buscar_despesas(splitwise_api_key, grupo_id, meses)

        if not despesas:
            st.warning("Nenhuma despesa encontrada no período selecionado")
            st.stop()

        st.success(f"✅ {len(despesas)} despesas encontradas")

        with st.spinner("Categorizando com IA..."):
            df = processar_despesas(despesas, groq_api_key)

        if df.empty:
            st.error("Erro ao processar despesas")
            st.stop()

        # Armazenar no session state
        st.session_state["df"] = df
        st.session_state["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    # Exibir análises se houver dados
    if "df" in st.session_state:
        df = st.session_state["df"]

        # Métricas principais
        st.header("📊 Resumo")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total de Gastos", f"{len(df):,}")

        with col2:
            st.metric("Valor Total", f"R$ {df['valor'].sum():,.2f}")

        with col3:
            alta_confianca = (df["confianca"] >= 0.8).sum()
            pct_alta = (alta_confianca / len(df) * 100)
            st.metric("Alta Confiança", f"{pct_alta:.1f}%")

        with col4:
            revisar = (df["confianca"] < 0.5).sum()
            st.metric("Itens para Revisar", f"{revisar:,}")

        st.divider()

        # Filtros
        st.header("🔍 Filtros e Dados")
        col1, col2, col3 = st.columns(3)

        with col1:
            filtro_status = st.multiselect(
                "Status de Confiança",
                options=["Alta (≥80%)", "Média (50-79%)", "Baixa (<50%)"],
                default=["Alta (≥80%)", "Média (50-79%)", "Baixa (<50%)"]
            )

        with col2:
            filtro_categoria = st.multiselect(
                "Categorias",
                options=CATEGORIA_NOMES,
                default=CATEGORIA_NOMES
            )

        with col3:
            busca_texto = st.text_input("🔎 Buscar na descrição", "")

        # Aplicar filtros
        df_filtrado = df[
            (df["status_confianca"].isin(filtro_status)) &
            (df["categoria"].isin(filtro_categoria))
        ]

        if busca_texto:
            df_filtrado = df_filtrado[
                df_filtrado["descricao"].str.contains(busca_texto, case=False, na=False)
            ]

        # Tabela interativa
        df_filtrado_ordenado = df_filtrado.sort_values("data", ascending=False).reset_index(drop=True)
        df_exibicao = df_filtrado_ordenado[["data_formatada", "descricao", "categoria", "valor_formatado", "confianca_formatada", "status_confianca"]].copy()
        df_exibicao.columns = ["Data", "Descrição", "Categoria", "Valor", "Confiança", "Status"]

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            height=400
        )

        # Botão de download
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"despesas_categorizadas_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

        st.divider()

        # Visualizações
        st.header("📈 Visualizações")

        # Gráfico de colunas empilhadas por mês
        st.subheader("Gastos por Mês e Categoria")
        df_mes_cat = df.groupby(["mes", "categoria"])["valor"].sum().reset_index()

        fig_mes = px.bar(
            df_mes_cat,
            x="mes",
            y="valor",
            color="categoria",
            title="Distribuição Mensal de Gastos",
            labels={"valor": "Valor (R$)", "mes": "Mês"},
            height=500
        )
        fig_mes.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_mes, use_container_width=True)

        # Gráfico de pizza
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Distribuição por Categoria")
            df_categoria = df.groupby("categoria")["valor"].sum().reset_index()

            fig_pizza = px.pie(
                df_categoria,
                values="valor",
                names="categoria",
                title="% do Total por Categoria",
                height=400
            )
            st.plotly_chart(fig_pizza, use_container_width=True)

        with col2:
            st.subheader("Evolução Temporal")
            df_evolucao = df.groupby("mes")["valor"].sum().reset_index()

            fig_linha = px.line(
                df_evolucao,
                x="mes",
                y="valor",
                title="Evolução dos Gastos",
                labels={"valor": "Valor (R$)", "mes": "Mês"},
                height=400,
                markers=True
            )
            st.plotly_chart(fig_linha, use_container_width=True)

        # Top categorias
        st.subheader("Top 5 Categorias por Valor")
        top5 = df.groupby("categoria")["valor"].sum().sort_values(ascending=False).head(5)

        fig_top5 = go.Figure(go.Bar(
            x=top5.values,
            y=top5.index,
            orientation='h',
            marker=dict(color='lightblue')
        ))
        fig_top5.update_layout(
            xaxis_title="Valor (R$)",
            yaxis_title="Categoria",
            height=300
        )
        st.plotly_chart(fig_top5, use_container_width=True)

if __name__ == "__main__":
    main()
