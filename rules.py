"""Conteúdo do questionário e análise das respostas dos participantes.

As regras que transformam o diagnóstico em plano metodológico NÃO ficam aqui:
estão no conjunto de regras editável (ver motor.py e regras_padrao.json).
"""
from collections import Counter
from statistics import median

# Limiar padrão de consenso; o valor usado de fato vem das regras editáveis.
LIMIAR_CONSENSO = 2 / 3

# ---------------------------------------------------------------------------
# Campos de identificação e contextualização (preenchidos em grupo)
# ---------------------------------------------------------------------------
CAMPOS_IDENTIFICACAO = [
    ("nome_iniciativa", "Nome da iniciativa", "text", True),
    ("unidade_demandante", "Unidade demandante", "text", True),
    ("gestor_responsavel", "Gestor(a) responsável", "text", False),
    ("responsavel_tecnico", "Responsável técnico", "text", False),
    ("facilitador_sessao", "Facilitador(a) da sessão", "text", False),
    ("data_aplicacao", "Data de aplicação", "date", True),
]

CAMPOS_CONTEXTO = [
    ("situacao_atual", "Situação atual", "Descreva como o serviço ou processo funciona atualmente."),
    ("problema_resolver", "Problema a ser resolvido", "Descreva o problema, suas causas e consequências conhecidas."),
    ("resultado_esperado", "Resultado esperado", "Indique as melhorias ou resultados pretendidos."),
]

PUBLICOS = ["Público interno", "Cidadãos", "Empresas", "Prestadores de serviço",
            "Outros órgãos públicos", "Outros"]

CAMPOS_ENVOLVIDOS = [
    ("sistemas_envolvidos", "Sistemas envolvidos"),
    ("bases_dados_envolvidas", "Bases de dados envolvidas"),
    ("processos_envolvidos", "Processos envolvidos"),
    ("unidades_envolvidas", "Unidades envolvidas"),
    ("instituicoes_externas", "Instituições externas envolvidas"),
    ("normas_dispositivos", "Normas ou dispositivos legais relacionados"),
]

# ---------------------------------------------------------------------------
# Critérios C1–C10
# ---------------------------------------------------------------------------
CRITERIOS = [
    {
        "codigo": "C1", "titulo": "Clareza do Problema", "bloco": "Problema",
        "pergunta": "O problema que motivou a iniciativa está claramente compreendido e delimitado, ou ainda é formulado apenas como um pedido de sistema/solução?",
        "opcoes": [
            "O problema está claramente descrito, com contexto, causas identificadas e impactos conhecidos.",
            "O problema é conhecido, mas ainda existem dúvidas sobre suas causas, abrangência ou públicos afetados.",
            "O problema ainda não está claramente delimitado, sendo necessário investigar suas causas e compreender seus impactos.",
        ],
    },
    {
        "codigo": "C2", "titulo": "Evidências Disponíveis", "bloco": "Problema",
        "pergunta": "Há dados, pesquisas, indicadores ou registros suficientes que comprovem e detalhem a existência do problema e o contexto do serviço?",
        "opcoes": [
            "Existem evidências suficientes, atualizadas e confiáveis que permitem compreender e dimensionar o problema.",
            "Existem algumas evidências, mas são incompletas, desatualizadas ou insuficientes, exigindo levantamento complementar.",
            "Não existem evidências estruturadas suficientes, sendo necessário realizar pesquisas e levantamentos para compreender o problema.",
        ],
    },
    {
        "codigo": "C3", "titulo": "Estágio da Demanda", "bloco": "Maturidade",
        "pergunta": "Em que fase a iniciativa se encontra (ideia inicial, exploração de oportunidade, reestruturação ou melhoria contínua)?",
        "opcoes": [
            "A demanda está estruturada, com objetivos e escopo claramente definidos, voltada à implementação ou melhoria de uma solução conhecida.",
            "A demanda possui objetivos gerais definidos, mas ainda exige refinamento de escopo, requisitos ou oportunidades de melhoria.",
            "A demanda está em fase inicial de exploração, sendo necessário compreender o contexto, identificar oportunidades e estruturar seus objetivos.",
        ],
    },
    {
        "codigo": "C4", "titulo": "Definição da Solução", "bloco": "Maturidade",
        "pergunta": "A solução já está definida e validada ou ainda precisa ser explorada e construída?",
        "opcoes": [
            "A solução está claramente definida, com seus principais aspectos mapeados e validados.",
            "Existe uma proposta de solução, mas ainda são necessários refinamentos, validações ou análises de viabilidade.",
            "A solução ainda não está definida, sendo necessárias atividades de exploração, pesquisa e experimentação para identificar alternativas.",
        ],
    },
    {
        "codigo": "C5", "titulo": "Diversidade de Públicos e Atores", "bloco": "Atores",
        "pergunta": "Quantos e quão diversos são os grupos de usuários, unidades internas, órgãos ou instituições que precisam ser considerados e envolvidos no desenho?",
        "opcoes": [
            "A demanda envolve um grupo restrito e relativamente homogêneo de usuários ou uma única área responsável.",
            "A demanda envolve diferentes grupos de usuários ou algumas áreas, com necessidades distintas que exigem alinhamento.",
            "A demanda envolve múltiplos grupos de usuários, áreas, órgãos ou instituições, com necessidades e características significativamente diferentes.",
        ],
    },
    {
        "codigo": "C6", "titulo": "Divergência de Atores", "bloco": "Atores",
        "pergunta": "Existe conflito, desalinhamento de interesses ou visões opostas entre os públicos e áreas envolvidas na demanda?",
        "opcoes": [
            "Os atores apresentam interesses, prioridades e expectativas alinhados.",
            "Existem divergências pontuais entre os atores, mas elas podem ser resolvidas por meio de alinhamentos e negociações.",
            "Existem divergências significativas ou interesses conflitantes que podem comprometer as decisões e o andamento da iniciativa.",
        ],
    },
    {
        "codigo": "C7", "titulo": "Impacto no Serviço", "bloco": "Alcance e risco",
        "pergunta": "Qual o alcance e a profundidade da mudança na prestação do serviço, na jornada do cidadão ou nos canais de atendimento?",
        "opcoes": [
            "A solução promove ajustes pontuais, sem alterações significativas na jornada dos usuários ou nos processos existentes.",
            "A solução modifica etapas específicas do serviço, exigindo adaptações em processos, canais ou articulação entre áreas.",
            "A solução transforma significativamente a jornada dos usuários, os processos ou os canais de atendimento, podendo envolver o redesenho do serviço de ponta a ponta.",
        ],
    },
    {
        "codigo": "C8", "titulo": "Risco Institucional", "bloco": "Alcance e risco",
        "pergunta": "Qual o nível de exposição, criticidade ou risco reputacional/operacional para a organização caso a iniciativa falhe ou seja mal desenhada?",
        "opcoes": [
            "A iniciativa apresenta riscos baixos, com impactos limitados e facilmente controláveis.",
            "A iniciativa apresenta riscos moderados, que exigem identificação, acompanhamento e medidas de mitigação.",
            "A iniciativa apresenta riscos elevados, com potencial de gerar consequências institucionais, operacionais, jurídicas ou reputacionais significativas.",
        ],
    },
    {
        "codigo": "C9", "titulo": "Mudança de Comportamento", "bloco": "Implantação",
        "pergunta": "Em que medida a solução exigirá mudanças de comportamento, hábitos ou rotinas dos usuários e operadores do serviço?",
        "opcoes": [
            "A solução se integra às práticas e rotinas existentes, exigindo pouca ou nenhuma mudança de comportamento.",
            "A solução exige adaptações moderadas nas rotinas, com necessidade de comunicação, capacitação ou acompanhamento.",
            "A solução exige mudanças significativas de hábitos, práticas ou cultura organizacional, sendo necessária uma estratégia estruturada de gestão da mudança.",
        ],
    },
    {
        "codigo": "C10", "titulo": "Dependências Técnicas e Legais", "bloco": "Implantação",
        "pergunta": "A demanda depende de adequações normativas, marcos regulatórios, integração de sistemas legados ou infraestrutura tecnológica específica?",
        "opcoes": [
            "A demanda possui poucas dependências técnicas ou legais, já identificadas e compreendidas, sem obstáculos relevantes à execução.",
            "A demanda possui dependências que exigem alinhamentos, adequações, integrações ou validações com outras áreas.",
            "A demanda possui múltiplas dependências técnicas, normativas ou institucionais complexas, com incertezas que podem comprometer significativamente sua execução.",
        ],
    },
]
CRITERIOS_POR_CODIGO = {c["codigo"]: c for c in CRITERIOS}

# ---------------------------------------------------------------------------
# Condições especiais T1–T8
# ---------------------------------------------------------------------------
RESPOSTAS_T = {
    "yes": "Sim",
    "no": "Não",
    "partial": "Parcialmente / Há indícios",
    "unknown": "Não sei / Precisa de avaliação",
}
# Ordem de precaução usada para desempate (maior = mais precavido).
PRECAUCAO_T = {"no": 0, "partial": 1, "unknown": 2, "yes": 3}

CONDICOES = [
    {"codigo": "T1", "titulo": "Proteção de Dados e Privacidade (LGPD)",
     "pergunta": "Envolve dados pessoais sensíveis, monitoramento ou perfilamento de pessoas?"},
    {"codigo": "T2", "titulo": "Segurança, Continuidade e Disponibilidade",
     "pergunta": "Falhas ou indisponibilidade podem impactar serviços essenciais ou a imagem institucional?"},
    {"codigo": "T3", "titulo": "Direitos, Obrigações e Regulatório",
     "pergunta": "Afeta atos normativos, sanções, fiscalização ou obrigações contratuais não negociáveis?"},
    {"codigo": "T4", "titulo": "Inteligência Artificial / Decisão Automatizada",
     "pergunta": "Aplica modelos analíticos ou algoritmos para tomar decisões sobre cidadãos ou usuários?"},
    {"codigo": "T5", "titulo": "Acessibilidade e Inclusão Digital",
     "pergunta": "Existem barreiras significativas para pessoas com deficiência, idosos ou pessoas de baixa conectividade?"},
    {"codigo": "T6", "titulo": "Transparência e Explicabilidade",
     "pergunta": "Os motivos dos resultados ou decisões precisam ser claramente compreendidos pelo público?"},
    {"codigo": "T7", "titulo": "Contato com Usuários / Acesso Limitado",
     "pergunta": "Há risco de não ser possível validar hipóteses com o público final?"},
    {"codigo": "T8", "titulo": "Engajamento e Governança",
     "pergunta": "Há ausência de patrocinador ou responsável decisório claro, ou indisponibilidade de decisão?"},
]
CONDICOES_POR_CODIGO = {t["codigo"]: t for t in CONDICOES}

ROTULO_STATUS = {
    "consenso": "Consenso",
    "moderada": "Divergência moderada",
    "alta": "Divergência alta",
    "sem_respostas": "Sem respostas",
}


def letra(nivel):
    return {1: "a", 2: "b", 3: "c"}.get(nivel, "–")


# ---------------------------------------------------------------------------
# Análise de divergência
# ---------------------------------------------------------------------------
def analisar_criterio(valores, limiar=LIMIAR_CONSENSO):
    """valores: lista de inteiros 1–3 (um por participante)."""
    valores = [int(v) for v in valores if v in (1, 2, 3, "1", "2", "3")]
    n = len(valores)
    if n == 0:
        return {"n": 0, "dist": {1: 0, 2: 0, 3: 0}, "status": "sem_respostas",
                "sugestao": None, "concordancia": 0, "amplitude": 0, "mediana": None}
    cont = Counter(valores)
    dist = {k: cont.get(k, 0) for k in (1, 2, 3)}
    maior = max(dist.values())
    modas = [k for k in (1, 2, 3) if dist[k] == maior]
    concordancia = maior / n
    amplitude = max(valores) - min(valores)
    med = median(valores)

    if amplitude == 0 or (concordancia >= limiar and amplitude <= 1):
        status = "consenso"
    elif amplitude == 2:
        status = "alta"
    else:
        status = "moderada"

    # Sugestão: moda única; empate → mediana arredondada para cima
    # (princípio de precaução: na dúvida, mais rigor metodológico).
    if len(modas) == 1:
        sugestao = modas[0]
    else:
        sugestao = int(-(-med // 1))
        if sugestao not in modas:
            sugestao = max(modas)
    return {"n": n, "dist": dist, "status": status, "sugestao": sugestao,
            "concordancia": round(concordancia * 100), "amplitude": amplitude, "mediana": med}


def analisar_condicao(valores, limiar=LIMIAR_CONSENSO):
    """valores: lista de 'yes' | 'no' | 'partial' | 'unknown'."""
    valores = [v for v in valores if v in RESPOSTAS_T]
    n = len(valores)
    dist = {k: 0 for k in RESPOSTAS_T}
    if n == 0:
        return {"n": 0, "dist": dist, "status": "sem_respostas", "sugestao": None, "concordancia": 0}
    for v in valores:
        dist[v] += 1
    maior = max(dist.values())
    modas = [k for k in dist if dist[k] == maior]
    concordancia = maior / n
    conflito = dist["no"] > 0 and (dist["yes"] > 0 or dist["unknown"] > 0)

    if len(set(valores)) == 1 or (concordancia >= limiar and not conflito):
        status = "consenso"
    elif conflito:
        status = "alta"
    else:
        status = "moderada"
    sugestao = max(modas, key=lambda k: PRECAUCAO_T[k])
    return {"n": n, "dist": dist, "status": status, "sugestao": sugestao,
            "concordancia": round(concordancia * 100)}


def analisar_oficina(respostas_participantes, limiar=LIMIAR_CONSENSO):
    """respostas_participantes: lista de dicts {codigo: valor} dos que enviaram."""
    analise = {}
    for c in CRITERIOS:
        analise[c["codigo"]] = analisar_criterio(
            [r.get(c["codigo"]) for r in respostas_participantes if r.get(c["codigo"])], limiar)
    for t in CONDICOES:
        analise[t["codigo"]] = analisar_condicao(
            [r.get(t["codigo"]) for r in respostas_participantes if r.get(t["codigo"])], limiar)
    return analise


