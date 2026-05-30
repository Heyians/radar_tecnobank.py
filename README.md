# radar_tecnobank.py
#!/usr/bin/env python3
"""
Radar Governamental — Monitor de Diários Oficiais
Cliente: Tecnobank
Estados: Piauí, Ceará, Minas Gerais
"""

import anthropic
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import os

# ── Configuração ──────────────────────────────────────────────────────────────

ESTADOS = {
    "PIAUÍ": {
        "url": "https://www.diario.pi.gov.br/doe/",
        "estrategia": "pi",
    },
    "CEARÁ": {
        "url": "http://pesquisa.doe.seplag.ce.gov.br/doepesquisa/sead.do?page=ultimasEdicoes&cmd=11&action=Ultimas",
        "estrategia": "ce",
    },
    "MINAS GERAIS": {
        "url": "https://www.jornalminasgerais.mg.gov.br/",
        "estrategia": "mg",
    },
}

SYSTEM_PROMPT = """Você é um analista da Radar Governamental, empresa especializada em monitoramento de diários oficiais para o setor financeiro e de crédito veicular.

Seu cliente é a Tecnobank, empresa do setor de registradoras e financiamento de veículos.

Quando receber o texto de um diário oficial de um estado, você deve:
1. Ler o conteúdo integralmente
2. Identificar APENAS o que é relevante para a Tecnobank com base nos critérios abaixo
3. Entregar no formato padrão do relatório

---

TEMAS ESTRATÉGICOS DE INTERESSE:
- Registro de Contrato / Registro Eletrônico de Contrato
- Alienação Fiduciária / Apontamento de Gravame
- Contrato de financiamento de veículo
- Recuperação Extrajudicial / Execução Extrajudicial Veicular
- Marco legal das garantias
- Credenciamento de Instituição Credora junto ao DETRAN
- Interoperabilidade entre registradoras / RENAVE

---

PALAVRAS-CHAVE A MONITORAR:
DETRAN / Departamento Estadual de Trânsito / CET / Secretaria da Fazenda / SEFAZ /
nomeação / nomeia / nomear / exoneração / exonera / designa /
UFR / Unidade Fiscal de Referência / UPF / Unidade Padrão Fiscal /
Diretor / Presidente / Superintendente / Diretor Geral / Diretor Adjunto /
Tecnobank / financiamento / contrato de financiamento / veículo / automóvel /
credenciamento / registradora / registro de contrato / taxa fixa / preço público /
certificado de registro de veículo / transferência digital de veículo /
recuperação extrajudicial de veículo / Gravame / apontamento de gravame /
alienação fiduciária / RENAVE / interoperabilidade / instituição credora /
entidade credora / operações de crédito

---

CONCORRENTES A MONITORAR (se aparecerem, é relevante):
ABL System / Alias Tecnologia / Arqdigital / Auttis / Bunkertech / CBTI / Conecta /
EIG Mercados / ERDOC / Giro pagamentos / HD Soluções / Idea maker / Itrânsito /
Kenta / Liga sistemas / Logo IT / Infosolo / M.I Montreal / Megadata / NCK /
Nectar / OTC soluções / Place tecnologia / R30 registro eletrônico / Rain TI /
RB Alvim / Registra consultoria / Result one / Search informática / Serasa /
Siello / CNR Tecnologia / Technovid / Techpark / Tecnol / Thomas Greg & Sons /
Valid soluções / VB Tech / I9 tecnologia / Vetera / Viasoft / Victoria / Websis /
Work excellence / WTJ / CP3 Tecnologia / B3 / BB Leasing / CERC / RENACON /
Online Processamento / C4 Tecnologia / Systembank / DOCS

---

ÓRGÃOS MONITORADOS:
Detrans de todos os estados / Senatran / Contran / Assembleias Legislativas /
Secretaria da Fazenda / Casa Civil / Ministério dos Transportes / Tribunal de Contas

---

CONTEXTOS RELACIONAIS IMPORTANTES:
- Nomeação/Exoneração de Diretor, Presidente, Superintendente no DETRAN = SEMPRE relevante
- UFR/UPF → SEFAZ → preço público de registradora = relevante
- Credenciamento → registradora de contrato → prazo/vigência = relevante
- Concorrente aparecendo em qualquer ato oficial = relevante

---

ESTADOS EM ALERTA ESPECIAL:
- Alagoas — implantação de registradoras via DETRAN
- Amazonas — mudança de modelo de credenciamento
- Pará — mudança de modelo de credenciamento

---

MAPA DE STAKEHOLDERS — Diretores de DETRAN:
CE – Waldemir Catanho de Sena Júnior
MG – Rone Evaldo Barbosa
PI – Luana Maria Machado Barradas

---

O QUE NÃO É RELEVANTE (ignorar completamente):
- Portarias de trânsito sem relação com financiamento ou registro de veículo
- Infrações, multas, habilitação de condutores
- Licitações de obras, pavimentação, construção
- Nomeações em outros órgãos que não sejam DETRAN, SEFAZ ou órgãos monitorados
- Pensões, aposentadorias, benefícios previdenciários
- Contratos de saúde, educação, cultura, turismo

---

FORMATO DO RELATÓRIO DE SAÍDA:

Se houver achados relevantes:

[NOME DO ESTADO]
Diário Oficial do Estado de [X] — [data]

[Órgão]
[Tipo de ato]
[Descrição do ato]

Se não houver nada relevante:
[NOME DO ESTADO] — Não foram encontradas publicações de interesse prioritário.

Seja direto e objetivo. Não adicione introduções ou conclusões."""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── Extratores por estado ─────────────────────────────────────────────────────

def extrair_pi():
    """Extrai o diário do Piauí"""
    try:
        r = requests.get(ESTADOS["PIAUÍ"]["url"], headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        # Pega o link da edição mais recente
        links = soup.find_all("a", href=True)
        diario_link = None
        for link in links:
            href = link.get("href", "")
            if "diario" in href.lower() or "doe" in href.lower() or "edicao" in href.lower():
                diario_link = href
                break
        if diario_link:
            if not diario_link.startswith("http"):
                diario_link = "https://www.diario.pi.gov.br" + diario_link
            r2 = requests.get(diario_link, headers=HEADERS, timeout=30)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            texto = soup2.get_text(separator="\n", strip=True)
            return texto[:50000]  # limita para não estourar contexto
        else:
            # Tenta pegar o texto da página principal
            return soup.get_text(separator="\n", strip=True)[:50000]
    except Exception as e:
        return f"ERRO ao acessar diário do Piauí: {e}"


def extrair_ce():
    """Extrai o diário do Ceará"""
    try:
        r = requests.get(ESTADOS["CEARÁ"]["url"], headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        # Busca link para a edição mais recente
        links = soup.find_all("a", href=True)
        diario_link = None
        for link in links:
            texto_link = link.get_text().lower()
            href = link.get("href", "")
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
            r2 = requests.get(diario_link, headers=HEADERS, timeout=30)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            texto = soup2.get_text(separator="\n", strip=True)
            return texto[:50000]
        else:
            return soup.get_text(separator="\n", strip=True)[:50000]
    except Exception as e:
        return f"ERRO ao acessar diário do Ceará: {e}"


def extrair_mg():
    """Extrai o diário de Minas Gerais"""
    try:
        r = requests.get(ESTADOS["MINAS GERAIS"]["url"], headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)
        diario_link = None
        for link in links:
            href = link.get("href", "")
            texto_link = link.get_text().lower()
            if any(x in texto_link for x in ["hoje", "atual", "última", "edição", "diário"]):
                diario_link = href
                break
            if any(x in href.lower() for x in ["edicao", "diario", "caderno"]):
                diario_link = href
                break
        if diario_link:
            if not diario_link.startswith("http"):
                diario_link = "https://www.jornalminasgerais.mg.gov.br" + diario_link
            r2 = requests.get(diario_link, headers=HEADERS, timeout=30)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            texto = soup2.get_text(separator="\n", strip=True)
            return texto[:50000]
        else:
            return soup.get_text(separator="\n", strip=True)[:50000]
    except Exception as e:
        return f"ERRO ao acessar diário de Minas Gerais: {e}"


# ── Análise via Claude ────────────────────────────────────────────────────────

def analisar_com_claude(estado, texto):
    """Envia o texto do diário para o Claude analisar"""
    client = anthropic.Anthropic()
    
    mensagem = f"""Analise o diário oficial abaixo do estado do {estado} e identifique o que é relevante para a Tecnobank.

DATA DE HOJE: {datetime.now().strftime('%d/%m/%Y')}

TEXTO DO DIÁRIO:
{texto}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": mensagem}]
    )
    
    return response.content[0].text


# ── Geração do relatório ──────────────────────────────────────────────────────

def gerar_relatorio(resultados):
    """Monta o relatório final em texto"""
    hoje = datetime.now().strftime('%d/%m/%Y')
    
    linhas = [
        "=" * 60,
        f"RADAR GOVERNAMENTAL — TECNOBANK",
        f"Relatório diário — {hoje}",
        "=" * 60,
        "",
    ]
    
    for estado, resultado in resultados.items():
        linhas.append(resultado)
        linhas.append("")
        linhas.append("-" * 40)
        linhas.append("")
    
    linhas.append("=" * 60)
    linhas.append("Fim do relatório")
    linhas.append("=" * 60)
    
    return "\n".join(linhas)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n🔍 Radar Governamental — Tecnobank")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"🗺️  Estados: Piauí, Ceará, Minas Gerais")
    print("=" * 50)
    
    extratores = {
        "PIAUÍ": extrair_pi,
        "CEARÁ": extrair_ce,
        "MINAS GERAIS": extrair_mg,
    }
    
    resultados = {}
    
    for estado, extrator in extratores.items():
        print(f"\n📰 Acessando diário do {estado}...")
        
        texto = extrator()
        
        if texto.startswith("ERRO"):
            print(f"   ⚠️  {texto}")
            resultados[estado] = f"{estado} — Erro ao acessar o diário: {texto}"
            continue
        
        print(f"   ✅ {len(texto)} caracteres extraídos")
        print(f"   🤖 Analisando com Claude...")
        
        resultado = analisar_com_claude(estado, texto)
        resultados[estado] = resultado
        
        print(f"   ✅ Análise concluída")
        time.sleep(2)  # respeita rate limit
    
    # Gera e salva o relatório
    relatorio = gerar_relatorio(resultados)
    
    nome_arquivo = f"tecnobank_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    caminho = f"/mnt/user-data/outputs/{nome_arquivo}"
    
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(relatorio)
    
    print(f"\n✅ Relatório salvo: {nome_arquivo}")
    print("\n" + "=" * 50)
    print(relatorio)
    
    return caminho


if __name__ == "__main__":
    main()
