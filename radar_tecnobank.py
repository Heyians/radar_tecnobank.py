#!/usr/bin/env python3
"""
Radar Governamental — Monitor de Diários Oficiais
Cliente: Tecnobank
Cobertura: DOU + todos os 27 estados brasileiros

Dependências:
    pip install requests beautifulsoup4 anthropic playwright pdfplumber pymupdf pytesseract
    playwright install chromium
"""

import os
import re
import sys
import time
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import anthropic

# ── Tenta importar libs opcionais ────────────────────────────────────────────

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz  # pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ── Constantes ────────────────────────────────────────────────────────────────

HOJE = datetime.now()
HOJE_STR = HOJE.strftime("%d/%m/%Y")
HOJE_FILENAME = HOJE.strftime("%Y%m%d")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

MAX_CHARS = 80_000   # limite por estado para não estourar contexto
DELAY = 2            # segundos entre requisições

# ── System prompt do analista ─────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um analista da Radar Governamental, especializado em monitoramento de diários oficiais para o setor financeiro e de crédito veicular no Brasil.

Seu cliente é a Tecnobank — empresa do setor de registradoras e financiamento de veículos que atua no registro eletrônico de contratos de financiamento junto aos DETRANs, no apontamento de gravames e na recuperação extrajudicial de veículos.

Ao receber o texto de um diário oficial, você deve:
1. Ler o conteúdo integralmente
2. Identificar APENAS o que é relevante para a Tecnobank, com base nos critérios abaixo
3. Responder no formato padrão do relatório

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEMAS ESTRATÉGICOS (sempre relevante):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Registro de Contrato / Registro Eletrônico de Contrato
- Alienação Fiduciária / Apontamento de Gravame
- Contrato de financiamento de veículo
- Recuperação Extrajudicial / Execução Extrajudicial Veicular
- Marco legal das garantias
- Credenciamento de Instituição Credora junto ao DETRAN
- Descredenciamento de registradora
- Interoperabilidade entre registradoras / RENAVE / SNG

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PALAVRAS-CHAVE A MONITORAR:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETRAN / Departamento Estadual de Trânsito / CET / Secretaria da Fazenda / SEFAZ /
nomeação / nomeia / nomear / exoneração / exonera / designa /
UFR / Unidade Fiscal de Referência / UPF / Unidade Padrão Fiscal /
Diretoria / Diretor / Presidente / Superintendente / Diretor Geral / Diretor Adjunto / Diretor Presidente /
Tecnobank / financiamento / contrato de financiamento / veículo / automóvel /
credenciamento / registradora / registradora de contrato / registro de contrato /
taxa fixa / preço público / certificado de licenciamento anual / certificado de registro de veículo /
transferência digital de veículo / recuperação extrajudicial de veículo /
Gravame / apontamento de gravame / alienação fiduciária / RENAVE / interoperabilidade /
instituição credora / entidade credora / crédito / operações de crédito /
Resolução Contran 807 / Resolução Contran 1016 / Resolução Contran 1018 /
Portaria Senatran / Senatran / Contran

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCORRENTES (qualquer menção em ato oficial = relevante — marcar com "(CONCORRENTE)"):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABL System / Alias Tecnologia / Arqdigital / Auttis Tecnologias / Bunkertech /
CBTI - CIA Brasileira / Conecta gestão em tecnologia / EIG Mercados / ERDOC /
Giro pagamentos / HD Soluções / Idea maker / Itrânsito tecnologia / Kenta informática /
Liga sistemas / Logo IT / Infosolo informática / M.I Montreal Informática /
Megadata computações / NCK gestão da informação / Nectar / OTC soluções /
Place tecnologia / R30 registro eletrônico / Rain TI / RB Alvim /
Registra consultoria / Result one / Search informática / Serasa / Siello tecnologia /
CNR Tecnologia / Technovid / Techpark / Tecnol / Thomas Greg & Sons /
Valid soluções / VB Tech / I9 tecnologia / Vetera tecnologia / Viasoft /
Victoria prestação de serviços / Websis tecnologia / Work excellence / WTJ tecnologia /
CP3 Tecnologia / B3 / BB Leasing / CERC / RENACON / Online Processamento /
C4 Tecnologia / Systembank / DOCS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTITUIÇÕES FINANCEIRAS (monitorar credenciamento/descredenciamento nos DETRANs):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BV / Santander / Itaú / PAN / Bradesco / Safra / Banco C6 /
Banco Volkswagen / GMAC / Omni / Daycoval / Banco Digimais /
Honda / Yamaha / Toyota / Renault RCI / Banco do Brasil / CEF /
Alfa / Administradora de Consórcio RCI Brasil / Honda Consórcio

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTOS RELACIONAIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Nomeação/Exoneração + cargo de direção + DETRAN = SEMPRE relevante
2. UFR/UPF + SEFAZ = relevante (impacta preço público das registradoras)
3. Credenciamento + registradora + DETRAN = relevante
4. Recuperação extrajudicial + veículo + portaria/edital = relevante
5. Concorrente + qualquer ato oficial = relevante (inteligência competitiva)
6. Preço público + registradora + tabela/portaria = relevante

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTADOS EM ALERTA ESPECIAL (destacar com "(ALERTA)"):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ALAGOAS — Portaria 315/2024 DETRAN/AL prevê registro de contrato via DETRAN direto
- AMAZONAS — Mudança de modelo de credenciamento em curso
- PARÁ — Mudança de modelo de credenciamento em curso

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAPA DE STAKEHOLDERS — Diretores de DETRAN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AC — Taynara Martins Barbosa (Presidente)
AL — Marco Antônio De Araújo Fireman / Adrualdo de Lima Catão (Diretor Presidente)
AM — Thanny Monik de Gusmão Silva / David Fernandes dos Santos (Diretor Presidente)
AP — Edvaldo Lima Mafra (Diretor Presidente)
BA — Max Adolfo Passos Mendes (Diretor Geral)
CE — Waldemir Catanho de Sena Júnior (Superintendente)
DF — Marcu Antônio de Souza Bellini (Diretor Geral) / Marcu Aurélio de Souza Marinho (Diretor Geral Adjunto)
ES — Givaldo Vieira da Silva / Gilbran Bolzan
GO — Odair José Soares (Presidente)
MA — Diego Fernando Mendes Rolim (Diretor Geral)
MG — Rone Evaldo Barbosa (Diretor Geral)
MS — Rudel Espíndola Trindade Júnior (Presidente)
MT — Gustavo Reis Lobo de Vasconcelos (Presidente)
PA — Renata Mirella Freitas Guimarães de Souza Coelho (Diretora)
PB — Isaias José Dantas Gualberto (Diretor Superintendente)
PE — Vladimir Lacerda Melquiades / Bruno Rafaell Silva dos Santos
PI — Luana Maria Machado Barradas (Diretora Geral)
PR — Hilton Santin Roveda (Diretor Presidente)
RJ — Carlos Eduardo Sarmento da Costa (Presidente)
RN — Jonielson Pereira de Oliveira (Diretor Geral)
RO — Sandro Ricardo Rocha dos Santos (Diretor Geral)
RR — Antonio Diego Parente Aragão / Gueres Pereira Mesquita (Diretor Presidente)
RS — Isabel Cristina dos Reis Friski (Diretora Geral Adjunta)
SC — Cristiano Medeiros (Presidente)
SE — Naleide de Andrade Santos (Presidente)
SP — Eduardo Aggio de Sá (Presidente)
TO — Hercy Ayres Rodrigues Filho (Presidente)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O QUE NÃO É RELEVANTE (ignorar completamente):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Portarias de trânsito sobre infrações, multas ou habilitação de condutores
- Licitações de obras de pavimentação, construção civil, saneamento
- Nomeações em secretarias que não sejam DETRAN ou SEFAZ
- Pensões, aposentadorias e benefícios previdenciários
- Contratos de saúde, educação, turismo, cultura, esporte
- Convênios de pavimentação ou obras municipais
- Concursos públicos sem relação com DETRAN ou SEFAZ
- Licenças ambientais
- Transferências de servidores em órgãos não monitorados

Regra geral: se não tiver relação direta com veículos + financiamento + registro + gravame + DETRAN + SEFAZ, ignore.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DO RELATÓRIO DE SAÍDA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Se houver achados relevantes:

[NOME DO ESTADO]
Diário Oficial do Estado de [X] — [data]

[Órgão]
[Tipo de ato]
[Descrição objetiva do ato, com número do instrumento quando disponível]

Se não houver nada relevante:
[NOME DO ESTADO] — Não foram encontradas publicações de interesse prioritário.

Seja direto e objetivo. Não adicione introduções ou conclusões fora do formato.
Se um concorrente aparecer, marque com "(CONCORRENTE)".
Se for estado em alerta especial, marque com "(ALERTA)".
Inclua sempre o número da portaria, extrato ou instrumento quando disponível."""

# ── Catálogo de portais ───────────────────────────────────────────────────────

PORTAIS = {
    "DOU": {
        "nome": "Diário Oficial da União",
        "url": "https://www.in.gov.br/servicos/diario-oficial-da-uniao",
        "estrategia": "dou",
        "regiao": "NACIONAL",
    },
    "SP": {
        "nome": "São Paulo",
        "url": "https://doe.sp.gov.br/sumario",
        "estrategia": "sp",
        "regiao": "SUDESTE",
    },
    "RJ": {
        "nome": "Rio de Janeiro",
        "url": "https://portal.ioerj.com.br/",
        "estrategia": "generico",
        "regiao": "SUDESTE",
    },
    "MG": {
        "nome": "Minas Gerais",
        "url": "https://www.jornalminasgerais.mg.gov.br/",
        "estrategia": "generico",
        "regiao": "SUDESTE",
    },
    "ES": {
        "nome": "Espírito Santo",
        "url": "https://ioes.dio.es.gov.br/portal/visualizacoes/diario_oficial",
        "estrategia": "generico",
        "regiao": "SUDESTE",
    },
    "PR": {
        "nome": "Paraná",
        "url": "https://www.documentos.dioe.pr.gov.br/dioe/consultaPublicaPDF.do?action=pgLocalizar",
        "estrategia": "pr",
        "regiao": "SUL",
    },
    "SC": {
        "nome": "Santa Catarina",
        "url": "https://doe.sea.sc.gov.br/v2.43.01/#/portal",
        "estrategia": "playwright",
        "regiao": "SUL",
    },
    "RS": {
        "nome": "Rio Grande do Sul",
        "url": "https://www.diariooficial.rs.gov.br/",
        "estrategia": "generico",
        "regiao": "SUL",
    },
    "MT": {
        "nome": "Mato Grosso",
        "url": "https://www.iomat.mt.gov.br/",
        "estrategia": "generico",
        "regiao": "CENTRO-OESTE",
    },
    "MS": {
        "nome": "Mato Grosso do Sul",
        "url": "https://www.diariooficial.ms.gov.br/",
        "estrategia": "generico",
        "regiao": "CENTRO-OESTE",
    },
    "GO": {
        "nome": "Goiás",
        "url": "https://diariooficial.abc.go.gov.br/",
        "estrategia": "generico",
        "regiao": "CENTRO-OESTE",
    },
    "DF": {
        "nome": "Distrito Federal",
        "url": "https://dodf.df.gov.br/",
        "estrategia": "df",
        "regiao": "CENTRO-OESTE",
    },
    "BA": {
        "nome": "Bahia",
        "url": "https://dool.egba.ba.gov.br/",
        "estrategia": "generico",
        "regiao": "NORDESTE",
    },
    "SE": {
        "nome": "Sergipe",
        "url": "https://iose.se.gov.br/diario-oficial",
        "estrategia": "generico",
        "regiao": "NORDESTE",
    },
    "AL": {
        "nome": "Alagoas",
        "url": "https://diario.imprensaoficial.al.gov.br/",
        "estrategia": "generico",
        "regiao": "NORDESTE",
        "alerta": True,
    },
    "PE": {
        "nome": "Pernambuco",
        "url": "https://diariooficial.cepe.com.br/diariooficialweb/#/home?diario=MQ%3D%3D",
        "estrategia": "playwright",
        "regiao": "NORDESTE",
    },
    "PB": {
        "nome": "Paraíba",
        "url": "https://auniao.pb.gov.br/doe",
        "estrategia": "generico",
        "regiao": "NORDESTE",
    },
    "RN": {
        "nome": "Rio Grande do Norte",
        "url": "https://www.diariooficial.rn.gov.br/dei/dorn3/",
        "estrategia": "generico",
        "regiao": "NORDESTE",
    },
    "CE": {
        "nome": "Ceará",
        "url": "http://pesquisa.doe.seplag.ce.gov.br/doepesquisa/sead.do?page=ultimasEdicoes&cmd=11&action=Ultimas",
        "estrategia": "ce",
        "regiao": "NORDESTE",
    },
    "PI": {
        "nome": "Piauí",
        "url": "https://www.diario.pi.gov.br/doe/",
        "estrategia": "pi",
        "regiao": "NORDESTE",
    },
    "MA": {
        "nome": "Maranhão",
        "url": "https://diariooficial.ma.gov.br/",
        "estrategia": "generico",
        "regiao": "NORDESTE",
    },
    "PA": {
        "nome": "Pará",
        "url": "https://www.ioepa.com.br/portal/",
        "estrategia": "generico",
        "regiao": "NORTE",
        "alerta": True,
    },
    "AM": {
        "nome": "Amazonas",
        "url": "https://diario.imprensaoficial.am.gov.br/",
        "estrategia": "generico",
        "regiao": "NORTE",
        "alerta": True,
    },
    "RO": {
        "nome": "Rondônia",
        "url": "https://diof.ro.gov.br/",
        "estrategia": "generico",
        "regiao": "NORTE",
    },
    "AC": {
        "nome": "Acre",
        "url": "https://diario.ac.gov.br/",
        "estrategia": "generico",
        "regiao": "NORTE",
    },
    "RR": {
        "nome": "Roraima",
        "url": "https://www.imprensaoficial.rr.gov.br/app/_inicial/",
        "estrategia": "generico",
        "regiao": "NORTE",
    },
    "AP": {
        "nome": "Amapá",
        "url": "https://diofe.portal.ap.gov.br/",
        "estrategia": "generico",
        "regiao": "NORTE",
    },
    "TO": {
        "nome": "Tocantins",
        "url": "https://diariooficial.to.gov.br/",
        "estrategia": "generico",
        "regiao": "NORTE",
    },
}

# Ordem de exibição das regiões no relatório
ORDEM_REGIOES = ["NACIONAL", "SUDESTE", "SUL", "CENTRO-OESTE", "NORDESTE", "NORTE"]

# ── Utilitários ────────────────────────────────────────────────────────────────

def _get(url, timeout=30, **kwargs):
    """GET com headers padrão e tratamento de erro."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        raise RuntimeError(f"GET {url} falhou: {e}")


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def _texto_da_soup(soup, limite=MAX_CHARS):
    return soup.get_text(separator="\n", strip=True)[:limite]


def _extrair_pdf_bytes(pdf_bytes):
    """Extrai texto de bytes de PDF usando pdfplumber ou pymupdf."""
    texto = ""
    if HAS_PDFPLUMBER:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texto += t + "\n"
    elif HAS_PYMUPDF:
        import fitz
        import io
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            texto += page.get_text() + "\n"
    else:
        texto = "[PDF encontrado mas pdfplumber/pymupdf não instalados — não foi possível extrair texto]"
    return texto[:MAX_CHARS]


def _playwright_get(url):
    """Renderiza página JS com Playwright e retorna texto."""
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright não instalado")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60_000)
        page.wait_for_load_state("networkidle", timeout=30_000)
        html = page.content()
        browser.close()
    return _texto_da_soup(_soup(html))


def _primeiro_link_pdf(soup, base_url=""):
    """Retorna a URL do primeiro link que aponta para um PDF."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            if not href.startswith("http"):
                href = base_url.rstrip("/") + "/" + href.lstrip("/")
            return href
    return None


def _baixar_e_extrair_pdf(url):
    r = _get(url, timeout=60)
    return _extrair_pdf_bytes(r.content)


# ── Extratores específicos ────────────────────────────────────────────────────

def extrair_dou():
    """DOU — in.gov.br"""
    try:
        # A API do DOU fornece edições por data
        data_api = HOJE.strftime("%Y-%m-%d")
        url_api = f"https://www.in.gov.br/leiturajornal?data={data_api}&jornal=1"
        r = _get(url_api)
        soup = _soup(r.text)
        # Busca todos os itens de matéria
        texto = _texto_da_soup(soup)
        if len(texto) < 200:
            # Tenta a página principal
            r2 = _get(PORTAIS["DOU"]["url"])
            texto = _texto_da_soup(_soup(r2.text))
        return texto
    except Exception as e:
        return f"ERRO: {e}"


def extrair_sp():
    """SP — doe.sp.gov.br"""
    try:
        r = _get(PORTAIS["SP"]["url"])
        soup = _soup(r.text)
        # Procura link de PDF do sumário do dia
        pdf_url = _primeiro_link_pdf(soup, "https://doe.sp.gov.br")
        if pdf_url:
            return _baixar_e_extrair_pdf(pdf_url)
        return _texto_da_soup(soup)
    except Exception as e:
        return f"ERRO: {e}"


def extrair_pr():
    """PR — dioe.pr.gov.br (formulário de busca por data)"""
    try:
        data_pr = HOJE.strftime("%d/%m/%Y")
        url = (
            "https://www.documentos.dioe.pr.gov.br/dioe/consultaPublicaPDF.do"
            f"?action=pgLocalizar&dataEdicao={data_pr}"
        )
        r = _get(url)
        soup = _soup(r.text)
        pdf_url = _primeiro_link_pdf(soup, "https://www.documentos.dioe.pr.gov.br")
        if pdf_url:
            return _baixar_e_extrair_pdf(pdf_url)
        return _texto_da_soup(soup)
    except Exception as e:
        return f"ERRO: {e}"


def extrair_df():
    """DF — dodf.df.gov.br"""
    try:
        # Tenta API JSON do DODF
        data_df = HOJE.strftime("%d-%m-%Y")
        url_api = f"https://dodf.df.gov.br/list?nome={data_df}"
        r = _get(url_api)
        soup = _soup(r.text)
        pdf_url = _primeiro_link_pdf(soup, "https://dodf.df.gov.br")
        if pdf_url:
            return _baixar_e_extrair_pdf(pdf_url)
        return _texto_da_soup(soup)
    except Exception as e:
        return f"ERRO: {e}"


def extrair_ce():
    """CE — pesquisa.doe.seplag.ce.gov.br"""
    try:
        r = _get(PORTAIS["CE"]["url"])
        soup = _soup(r.text)
        links = soup.find_all("a", href=True)
        diario_link = None
        for link in links:
            texto_link = link.get_text().lower()
            href = link["href"]
            if any(x in texto_link for x in ["hoje", "última", "atual", "edição"]):
                diario_link = href
                break
            if any(x in href.lower() for x in ["edicao", "diario", "doe"]):
                diario_link = href
                break
        if diario_link:
            base = "http://pesquisa.doe.seplag.ce.gov.br"
            if not diario_link.startswith("http"):
                diario_link = base + diario_link
            r2 = _get(diario_link)
            soup2 = _soup(r2.text)
            pdf_url = _primeiro_link_pdf(soup2, base)
            if pdf_url:
                return _baixar_e_extrair_pdf(pdf_url)
            return _texto_da_soup(soup2)
        return _texto_da_soup(soup)
    except Exception as e:
        return f"ERRO: {e}"


def extrair_pi():
    """PI — diario.pi.gov.br"""
    try:
        r = _get(PORTAIS["PI"]["url"])
        soup = _soup(r.text)
        links = soup.find_all("a", href=True)
        diario_link = None
        for link in links:
            href = link["href"]
            if any(x in href.lower() for x in ["diario", "doe", "edicao", ".pdf"]):
                diario_link = href
                break
        if diario_link:
            if not diario_link.startswith("http"):
                diario_link = "https://www.diario.pi.gov.br" + diario_link
            if diario_link.lower().endswith(".pdf"):
                return _baixar_e_extrair_pdf(diario_link)
            r2 = _get(diario_link)
            soup2 = _soup(r2.text)
            pdf_url = _primeiro_link_pdf(soup2, "https://www.diario.pi.gov.br")
            if pdf_url:
                return _baixar_e_extrair_pdf(pdf_url)
            return _texto_da_soup(soup2)
        return _texto_da_soup(soup)
    except Exception as e:
        return f"ERRO: {e}"


def extrair_playwright(sigla):
    """Extrai diário usando Playwright (para sites com JS pesado)."""
    try:
        return _playwright_get(PORTAIS[sigla]["url"])
    except Exception as e:
        return f"ERRO: {e}"


def extrair_generico(sigla):
    """Extrator genérico: tenta HTML, depois PDF se encontrar link."""
    cfg = PORTAIS[sigla]
    url = cfg["url"]
    try:
        r = _get(url)
        soup = _soup(r.text)
        # Tenta PDF primeiro
        pdf_url = _primeiro_link_pdf(soup, url)
        if pdf_url:
            try:
                return _baixar_e_extrair_pdf(pdf_url)
            except Exception:
                pass
        # Tenta navegar para link mais recente
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text().lower()
            if any(x in txt for x in ["hoje", "atual", "última edição", "última edicao"]):
                if not href.startswith("http"):
                    href = url.rstrip("/") + "/" + href.lstrip("/")
                try:
                    r2 = _get(href)
                    soup2 = _soup(r2.text)
                    pdf_url2 = _primeiro_link_pdf(soup2, url)
                    if pdf_url2:
                        return _baixar_e_extrair_pdf(pdf_url2)
                    return _texto_da_soup(soup2)
                except Exception:
                    pass
        return _texto_da_soup(soup)
    except Exception as e:
        # Tenta Playwright como fallback
        if HAS_PLAYWRIGHT:
            try:
                return _playwright_get(url)
            except Exception:
                pass
        return f"ERRO: {e}"


# ── Dispatcher ────────────────────────────────────────────────────────────────

def extrair(sigla):
    """Despacha para o extrator correto com base na estratégia configurada."""
    cfg = PORTAIS[sigla]
    estrategia = cfg.get("estrategia", "generico")
    try:
        if estrategia == "dou":
            return extrair_dou()
        elif estrategia == "sp":
            return extrair_sp()
        elif estrategia == "pr":
            return extrair_pr()
        elif estrategia == "df":
            return extrair_df()
        elif estrategia == "ce":
            return extrair_ce()
        elif estrategia == "pi":
            return extrair_pi()
        elif estrategia == "playwright":
            return extrair_playwright(sigla)
        else:
            return extrair_generico(sigla)
    except Exception as e:
        return f"ERRO inesperado: {e}\n{traceback.format_exc()}"


# ── Análise via Claude ────────────────────────────────────────────────────────

def analisar(sigla, texto):
    """Envia o texto do diário para o Claude e retorna o trecho relevante."""
    cfg = PORTAIS[sigla]
    nome = cfg["nome"]
    alerta = cfg.get("alerta", False)

    client = anthropic.Anthropic()

    user_msg = (
        f"Analise o diário oficial abaixo do estado {'do ' if sigla != 'DOU' else 'da União / '}"
        f"{nome} e identifique o que é relevante para a Tecnobank.\n\n"
        f"DATA DE HOJE: {HOJE_STR}\n"
        f"{'ESTADO EM ALERTA ESPECIAL: SIM' if alerta else ''}\n\n"
        f"TEXTO DO DIÁRIO:\n{texto}"
    )

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text


# ── Montagem do relatório ─────────────────────────────────────────────────────

def montar_relatorio(resultados):
    """Agrupa os resultados por região e monta o texto final."""
    linhas = [
        "═" * 56,
        "RADAR GOVERNAMENTAL — TECNOBANK",
        f"Relatório diário — {HOJE_STR}",
        "═" * 56,
        "",
    ]

    por_regiao = {r: [] for r in ORDEM_REGIOES}
    for sigla, resultado in resultados.items():
        regiao = PORTAIS[sigla]["regiao"]
        por_regiao[regiao].append((sigla, resultado))

    for regiao in ORDEM_REGIOES:
        itens = por_regiao.get(regiao, [])
        if not itens:
            continue
        linhas.append(regiao)
        linhas.append("─" * 56)
        linhas.append("")
        for sigla, resultado in itens:
            linhas.append(resultado)
            linhas.append("")
        linhas.append("")

    linhas += [
        "═" * 56,
        "Fim do relatório",
        "═" * 56,
    ]

    return "\n".join(linhas)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nRadar Governamental — Tecnobank")
    print(f"Data: {HOJE_STR}")
    print(f"Estados: {len(PORTAIS)} portais monitorados")
    print("=" * 56)

    resultados = {}

    for sigla, cfg in PORTAIS.items():
        nome = cfg["nome"]
        print(f"\n[{sigla}] Acessando {nome}...")

        texto = extrair(sigla)

        if texto.startswith("ERRO"):
            print(f"      {texto}")
            resultados[sigla] = (
                f"{nome.upper()} — Diário não disponibilizado no período de confecção do relatório.\n"
                f"({texto})"
            )
            time.sleep(DELAY)
            continue

        chars = len(texto)
        print(f"      {chars:,} caracteres extraídos. Analisando com Claude...")

        try:
            resultado = analisar(sigla, texto)
            resultados[sigla] = resultado
            print(f"      Análise concluída.")
        except Exception as e:
            print(f"      ERRO na análise: {e}")
            resultados[sigla] = f"{nome.upper()} — Erro na análise via IA: {e}"

        time.sleep(DELAY)

    # Monta e salva o relatório
    relatorio = montar_relatorio(resultados)

    output_dir = Path("/mnt/user-data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"tecnobank_{HOJE_FILENAME}.txt"
    caminho = output_dir / nome_arquivo

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(relatorio)

    print(f"\nRelatório salvo: {caminho}")
    print("\n" + "=" * 56)
    print(relatorio)

    return str(caminho)


if __name__ == "__main__":
    main()
