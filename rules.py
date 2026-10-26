"""Regras do diagnóstico e do plano metodológico de Design de Serviços.

Este módulo não depende do Flask: concentra o conteúdo do formulário,
a análise de divergência entre participantes e a geração do plano.
Para ajustar técnicas, limiares ou textos, altere apenas este arquivo.
"""
from collections import Counter
from statistics import median

ETAPAS = [
    "Alinhamento e Escopo",
    "Exploração do problema",
    "Ideação da Solução",
    "Prototipação da Solução",
    "Handover e integração com desenvolvimento paralelo",
    "Avaliação e Melhoria Contínua",
]
AL, EX, ID, PR, HO, AV = ETAPAS
# Etapas que existem em todo projeto (variam só em intensidade).
ETAPAS_SEMPRE = {AL, HO, AV}
# Etapas que podem ser dispensadas conforme o ponto de entrada.
ETAPAS_DISPENSAVEIS = [EX, ID, PR]

# Critérios que definem a intensidade de cada etapa.
MOTORES = {
    AL: ["C3", "C5", "C6"],
    EX: ["C1", "C2", "C7"],
    ID: ["C4", "C5", "C6"],
    PR: ["C4", "C7", "C8", "C9"],
    HO: ["C10", "C7"],
    AV: ["C8", "C9"],
}

# Técnicas de base, presentes sempre que a etapa está ativa.
TECNICAS_BASE = {
    AL: ["Termo de abertura do projeto"],
    EX: ["Reenquadramento do problema (“Como poderíamos…”)"],
    ID: [],
    PR: [],
    HO: ["Histórias de usuário com critérios de aceite de experiência"],
    AV: ["Indicadores de experiência e canal de feedback dos usuários"],
}

INTENSIDADE = {3: "Alta", 2: "Média", 1: "Baixa"}

# Como cada nível de cada critério é descrito no texto que justifica a intensidade.
FRASES = {
    "C1": ("o problema já está claramente delimitado", "ainda há dúvidas sobre as causas e a abrangência do problema",
           "o problema ainda não está delimitado"),
    "C2": ("há evidências suficientes sobre o problema", "as evidências disponíveis são incompletas ou desatualizadas",
           "faltam evidências estruturadas sobre o problema"),
    "C3": ("o escopo da demanda já está definido", "o escopo ainda precisa ser refinado",
           "a demanda está em fase inicial e o escopo precisa ser construído"),
    "C4": ("a solução já está definida e validada", "existe uma proposta de solução que precisa ser refinada e testada",
           "a solução ainda não está definida"),
    "C5": ("o público é restrito e homogêneo", "há diferentes grupos de usuários e áreas a considerar",
           "há múltiplos públicos e instituições com necessidades distintas"),
    "C6": ("os atores estão alinhados", "há divergências pontuais entre os atores",
           "há conflitos significativos de interesse entre os atores"),
    "C7": ("a mudança no serviço é pontual", "a mudança altera etapas específicas do serviço",
           "o serviço será transformado de ponta a ponta"),
    "C8": ("o risco institucional é baixo", "o risco institucional é moderado", "o risco institucional é elevado"),
    "C9": ("a solução se integra às rotinas atuais", "a solução exige adaptações moderadas nas rotinas",
           "a solução exige mudanças significativas de comportamento"),
    "C10": ("há poucas dependências técnicas e legais", "há dependências que exigem alinhamento com outras áreas",
            "há múltiplas dependências técnicas e normativas complexas"),
}

# Rótulo curto de cada nível, usado no lugar das letras a/b/c.
ROTULOS = {
    "C1": ("Claro", "Parcialmente claro", "Indefinido"),
    "C2": ("Suficientes", "Incompletas", "Inexistentes"),
    "C3": ("Estruturada", "Em refinamento", "Inicial"),
    "C4": ("Definida e validada", "Proposta a refinar", "Não definida"),
    "C5": ("Restrita", "Diversa", "Muito diversa"),
    "C6": ("Alinhados", "Divergências pontuais", "Conflito significativo"),
    "C7": ("Pontual", "Em etapas específicas", "De ponta a ponta"),
    "C8": ("Baixo", "Moderado", "Elevado"),
    "C9": ("Pouca", "Moderada", "Significativa"),
    "C10": ("Poucas", "Exigem alinhamento", "Complexas"),
}


def rotulo(cod, nivel):
    """Ex.: rotulo('C1', 2) -> 'Clareza do problema: parcialmente claro'."""
    if cod not in ROTULOS or nivel not in (1, 2, 3):
        return ""
    return f"{CRITERIOS_POR_CODIGO[cod]['titulo'].capitalize()}: {ROTULOS[cod][nivel - 1].lower()}"


# O que cada intensidade significa na prática. Toda etapa ativa é feita;
# a intensidade indica quanto esforço e validação ela exige.
DEFINICAO_INTENSIDADE = {
    "Alta": {"profundidade": "Frente de trabalho própria, combinando várias técnicas",
             "participantes": "Usuários finais e todas as áreas envolvidas",
             "ciclos": "Mais de um ciclo, revisando a partir do que se aprendeu",
             "validacao": "Com usuários e com o patrocinador"},
    "Média": {"profundidade": "Uma ou duas técnicas, focadas no que ainda está incerto",
              "participantes": "Representantes dos principais grupos",
              "ciclos": "Um ciclo",
              "validacao": "Com o patrocinador"},
    "Baixa": {"profundidade": "Revisão do que já existe, sem produzir material novo",
              "participantes": "Equipe do projeto e demandante",
              "ciclos": "Uma reunião de verificação",
              "validacao": "Confirmação do demandante"},
}

# Orientação específica de cada etapa em cada intensidade.
ORIENTACAO_ETAPA = {
    AL: {
        "Alta": "O alinhamento deve ser tratado como uma frente de trabalho, e não como uma reunião de abertura. Prever oficinas com o patrocinador e com cada área envolvida até chegar a um escopo e a um desafio aceitos por todos, com o rito de decisão registrado no termo de abertura.",
        "Média": "Uma oficina com o patrocinador e os representantes das áreas principais deve bastar para fechar o escopo e o desafio. O importante é registrar as decisões e o que fica fora do projeto.",
        "Baixa": "O escopo está claro e os atores estão alinhados. Uma reunião de abertura com o patrocinador é suficiente para confirmar o escopo e formalizar o termo de abertura.",
    },
    EX: {
        "Alta": "A exploração é o centro do projeto neste momento. Prever pesquisa de campo com usuários e operadores do serviço, em mais de uma rodada, antes de qualquer discussão sobre solução. A etapa termina quando o demandante validar o problema reenquadrado com base nas evidências reunidas.",
        "Média": "Já existe conhecimento sobre o problema, mas com lacunas. Concentrar a pesquisa nessas lacunas, combinando os dados disponíveis com algumas entrevistas, e validar o problema reenquadrado com o patrocinador.",
        "Baixa": "O problema e as evidências já são conhecidos. A etapa serve para reunir o material existente e confirmar o enquadramento do problema com o demandante.",
    },
    ID: {
        "Alta": "Gerar e comparar alternativas antes de escolher um caminho. Conduzir sessões de ideação com os diferentes públicos e priorizar as ideias com critérios combinados previamente com o patrocinador, para que a escolha seja compreendida e aceita.",
        "Média": "Já existe uma direção de solução. A ideação deve explorar variações dessa direção e verificar a viabilidade de cada uma, sem reabrir a discussão sobre o problema.",
        "Baixa": "A solução já está escolhida. A etapa se limita a registrar a escolha e as razões que a sustentam.",
    },
    PR: {
        "Alta": "Testar a solução com usuários reais em ciclos sucessivos, aumentando a fidelidade dos protótipos a cada rodada. O que for validado em cada ciclo já pode seguir para o desenvolvimento, sem esperar o fim da etapa.",
        "Média": "Um ciclo de testes com protótipos simples deve bastar para confirmar a proposta e ajustar os pontos críticos antes de entregá-la ao desenvolvimento.",
        "Baixa": "A solução já foi validada. A etapa serve para revisar as evidências dessa validação e confirmar que continuam válidas para o serviço.",
    },
    HO: {
        "Alta": "Acompanhar de perto o time de desenvolvimento, com rituais regulares, e entregar a solução por incrementos. Integrações e adequações normativas devem entrar no cronograma como marcos, para não bloquear a construção.",
        "Média": "Organizar a entrega ao desenvolvimento com histórias de usuário e critérios de aceite claros, e combinar pontos de acompanhamento para tirar dúvidas durante a construção.",
        "Baixa": "Uma reunião de passagem com o time responsável, apresentando as histórias de usuário e os critérios de aceite, é suficiente.",
        "sem_sistema": "Documentar o novo processo, capacitar quem vai operá-lo e combinar com a área responsável a data em que ela assume a operação.",
    },
    AV: {
        "Alta": "Começar com um piloto controlado, com plano de reversão, e acompanhar indicadores de experiência e de operação antes de ampliar. Programar ciclos periódicos de melhoria a partir do que for observado.",
        "Média": "Definir indicadores de acompanhamento e preparar comunicação e capacitação para quem usa e opera o serviço. Revisar os resultados depois de um período de uso e ajustar o que for necessário.",
        "Baixa": "Acompanhar poucos indicadores de experiência e manter um canal aberto para o retorno dos usuários.",
    },
}

# Alinhamento realizado na própria oficina: escopo, públicos e atores na situação
# mais simples e patrocinador definido. Resta apenas formalizar o termo de abertura.
ALINHAMENTO_NA_OFICINA = {
    "porque": ("Baixa intensidade porque o escopo da demanda já está definido, o público é restrito e homogêneo, "
               "os atores estão alinhados e a iniciativa tem patrocinador definido. A própria oficina de diagnóstico "
               "cumpriu o papel de alinhamento."),
    "orientacao": ("Resta formalizar o termo de abertura com o patrocinador, registrando o escopo, o desafio e o rito "
                   "de decisão combinados na oficina. Não é preciso nova reunião de alinhamento."),
    "entrada": ["Identificação e contextualização acordadas pelo grupo", "Diagnóstico consolidado na oficina"],
    "saida": ["Termo de abertura assinado, com escopo, desafio e rito de decisão"],
    "pronta_quando": "O patrocinador assina o termo de abertura.",
}


def alinhamento_na_oficina(niveis, condicoes):
    return (all(niveis.get(c) == 1 for c in ("C3", "C5", "C6"))
            and condicoes.get("T8") == "no")


# O que cada critério pede de cada etapa (aparece quando o critério está em nível médio ou alto).
FOCO = {
    (AL, "C3"): "Refinar o escopo, deixando explícito o que fica dentro e fora do projeto.",
    (AL, "C5"): "Identificar todos os públicos e instituições envolvidos e definir como cada um vai participar.",
    (AL, "C6"): "Tornar explícitos os interesses em conflito e combinar como as decisões serão tomadas.",
    (EX, "C1"): "Investigar as causas do problema, separando o que é certeza do que é suposição.",
    (EX, "C2"): "Levantar dados e ouvir usuários para dimensionar o problema.",
    (EX, "C7"): "Mapear a jornada atual nos pontos que a mudança vai alcançar.",
    (ID, "C4"): "Explorar mais de uma alternativa de solução antes de escolher.",
    (ID, "C5"): "Envolver os diferentes públicos na criação das alternativas.",
    (ID, "C6"): "Usar critérios de priorização explícitos, para que a escolha seja aceita pelas partes.",
    (PR, "C4"): "Verificar se a solução resolve, de fato, o problema que motivou a demanda.",
    (PR, "C7"): "Detalhar no blueprint como a jornada e os canais de atendimento vão mudar.",
    (PR, "C8"): "Reduzir o risco institucional testando em ambiente controlado antes da implantação.",
    (PR, "C9"): "Testar com os operadores do serviço, que precisarão mudar suas rotinas.",
    (HO, "C10"): "Resolver integrações e adequações normativas antes que bloqueiem o desenvolvimento.",
    (HO, "C7"): "Garantir que o desenvolvimento reflita a nova jornada em todos os canais afetados.",
    (AV, "C8"): "Monitorar os riscos institucionais durante a implantação.",
    (AV, "C9"): "Apoiar usuários e operadores na mudança de rotina.",
}


def _juntar(frases):
    if len(frases) <= 1:
        return "".join(frases)
    return ", ".join(frases[:-1]) + " e " + frases[-1]


def _nota_peso(codigos):
    if not codigos:
        return ""
    nomes = _juntar(["a " + CRITERIOS_POR_CODIGO[c]["titulo"].lower() for c in codigos])
    return (f" Como {nomes} {'tem' if len(codigos) == 1 else 'têm'} peso dobrado no diagnóstico, "
            "essa situação já basta para elevar a intensidade.")


def justificar_intensidade(etapa, intensidade, niveis, efetivos, tem_sistema=True):
    """Explica a intensidade da etapa: por quê, o que fazer e em que focar."""
    if etapa == HO and not tem_sistema:
        focos = [FOCO[(HO, "C10")]] if (efetivos.get("C10") or 1) >= 2 else []
        return {"porque": "Baixa intensidade porque nenhum sistema foi informado: a mudança não depende de "
                          "desenvolvimento, e o handover se resume a transferir o novo processo para a área responsável.",
                "orientacao": ORIENTACAO_ETAPA[HO]["sem_sistema"], "focos": focos}
    alvo = {"Alta": 3, "Média": 2, "Baixa": 1}[intensidade]
    partes, pesados = [], []
    for cod in MOTORES[etapa]:
        real, ef = niveis.get(cod), efetivos.get(cod)
        if real is None or (ef or 1) != alvo:
            continue
        partes.append(FRASES[cod][real - 1])
        if ef != real:
            pesados.append(cod)
    porque = f"{intensidade} intensidade porque {_juntar(partes)}." + _nota_peso(pesados)
    focos = [FOCO[(etapa, cod)] for cod in sorted(MOTORES[etapa], key=lambda c: -(efetivos.get(c) or 1))
             if (efetivos.get(cod) or 1) >= 2 and (etapa, cod) in FOCO]
    return {"porque": porque, "orientacao": ORIENTACAO_ETAPA[etapa][intensidade], "focos": focos}


ETAPA_CURTA = {AL: "Alinhamento", EX: "Exploração", ID: "Ideação",
               PR: "Prototipação", HO: "Handover", AV: "Avaliação"}

# Limiar de concordância: proporção mínima de participantes na mesma
# alternativa para considerar consenso.
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
# Cada técnica é (nome, etapa). Nível 2 ativa "n2"; nível 3 ativa "n2" + "n3".
# ---------------------------------------------------------------------------
CRITERIOS = [
    {
        "codigo": "C1", "titulo": "Clareza do Problema", "peso": 2, "bloco": "Problema",
        "pergunta": "O problema que motivou a iniciativa está claramente compreendido e delimitado, ou ainda é formulado apenas como um pedido de sistema/solução?",
        "opcoes": [
            "O problema está claramente descrito, com contexto, causas identificadas e impactos conhecidos.",
            "O problema é conhecido, mas ainda existem dúvidas sobre suas causas, abrangência ou públicos afetados.",
            "O problema ainda não está claramente delimitado, sendo necessário investigar suas causas e compreender seus impactos.",
        ],
        "checagem": "Validar a descrição do problema com o demandante.",
        "n2": [("Matriz CSD (certezas, suposições e dúvidas)", EX)],
        "n3": [("Pesquisa exploratória", EX), ("Árvore de problemas", EX), ("Análise de causa raiz (5 porquês)", EX)],
    },
    {
        "codigo": "C2", "titulo": "Evidências Disponíveis", "peso": 1, "bloco": "Problema",
        "pergunta": "Há dados, pesquisas, indicadores ou registros suficientes que comprovem e detalhem a existência do problema e o contexto do serviço?",
        "opcoes": [
            "Existem evidências suficientes, atualizadas e confiáveis que permitem compreender e dimensionar o problema.",
            "Existem algumas evidências, mas são incompletas, desatualizadas ou insuficientes, exigindo levantamento complementar.",
            "Não existem evidências estruturadas suficientes, sendo necessário realizar pesquisas e levantamentos para compreender o problema.",
        ],
        "checagem": "Reunir as evidências existentes como insumo do projeto.",
        "n2": [("Pesquisa documental (desk research)", EX), ("Análise de dados e registros existentes", EX)],
        "n3": [("Entrevistas em profundidade", EX), ("Observação de campo / shadowing", EX), ("Questionário (survey) com usuários", EX)],
    },
    {
        "codigo": "C3", "titulo": "Estágio da Demanda", "peso": 1, "bloco": "Maturidade",
        "pergunta": "Em que fase a iniciativa se encontra (ideia inicial, exploração de oportunidade, reestruturação ou melhoria contínua)?",
        "opcoes": [
            "A demanda está estruturada, com objetivos e escopo claramente definidos, voltada à implementação ou melhoria de uma solução conhecida.",
            "A demanda possui objetivos gerais definidos, mas ainda exige refinamento de escopo, requisitos ou oportunidades de melhoria.",
            "A demanda está em fase inicial de exploração, sendo necessário compreender o contexto, identificar oportunidades e estruturar seus objetivos.",
        ],
        "checagem": "Confirmar objetivos e escopo com o patrocinador.",
        "n2": [("Oficina de escopo", AL)],
        "n3": [("Definição do desafio de design", AL), ("Imersão no contexto do serviço", EX)],
    },
    {
        "codigo": "C4", "titulo": "Definição da Solução", "peso": 1, "bloco": "Maturidade",
        "pergunta": "A solução já está definida e validada ou ainda precisa ser explorada e construída?",
        "opcoes": [
            "A solução está claramente definida, com seus principais aspectos mapeados e validados.",
            "Existe uma proposta de solução, mas ainda são necessários refinamentos, validações ou análises de viabilidade.",
            "A solução ainda não está definida, sendo necessárias atividades de exploração, pesquisa e experimentação para identificar alternativas.",
        ],
        "checagem": "Registrar as validações já feitas da solução.",
        "n2": [("Análise de viabilidade das ideias", ID), ("Teste de conceito", PR), ("Protótipos de baixa fidelidade", PR)],
        "n3": [("Ideação estruturada (crazy 8s, brainwriting)", ID), ("Testes iterativos com usuários", PR)],
    },
    {
        "codigo": "C5", "titulo": "Diversidade de Públicos e Atores", "peso": 2, "bloco": "Atores",
        "pergunta": "Quantos e quão diversos são os grupos de usuários, unidades internas, órgãos ou instituições que precisam ser considerados e envolvidos no desenho?",
        "opcoes": [
            "A demanda envolve um grupo restrito e relativamente homogêneo de usuários ou uma única área responsável.",
            "A demanda envolve diferentes grupos de usuários ou algumas áreas, com necessidades distintas que exigem alinhamento.",
            "A demanda envolve múltiplos grupos de usuários, áreas, órgãos ou instituições, com necessidades e características significativamente diferentes.",
        ],
        "checagem": "Listar os usuários e a área responsável.",
        "n2": [("Mapa de stakeholders", AL), ("Personas", EX)],
        "n3": [("Mapa de ecossistema do serviço", AL), ("Personas por segmento de público", EX), ("Oficinas de cocriação", ID)],
    },
    {
        "codigo": "C6", "titulo": "Divergência de Atores", "peso": 1, "bloco": "Atores",
        "pergunta": "Existe conflito, desalinhamento de interesses ou visões opostas entre os públicos e áreas envolvidas na demanda?",
        "opcoes": [
            "Os atores apresentam interesses, prioridades e expectativas alinhados.",
            "Existem divergências pontuais entre os atores, mas elas podem ser resolvidas por meio de alinhamentos e negociações.",
            "Existem divergências significativas ou interesses conflitantes que podem comprometer as decisões e o andamento da iniciativa.",
        ],
        "checagem": "Confirmar o alinhamento entre as áreas no início do projeto.",
        "n2": [("Matriz poder × interesse", AL)],
        "n3": [("Oficinas mediadas e acordo de decisão", AL), ("Priorização com critérios explícitos", ID)],
    },
    {
        "codigo": "C7", "titulo": "Impacto no Serviço", "peso": 1, "bloco": "Alcance e risco",
        "pergunta": "Qual o alcance e a profundidade da mudança na prestação do serviço, na jornada do cidadão ou nos canais de atendimento?",
        "opcoes": [
            "A solução promove ajustes pontuais, sem alterações significativas na jornada dos usuários ou nos processos existentes.",
            "A solução modifica etapas específicas do serviço, exigindo adaptações em processos, canais ou articulação entre áreas.",
            "A solução transforma significativamente a jornada dos usuários, os processos ou os canais de atendimento, podendo envolver o redesenho do serviço de ponta a ponta.",
        ],
        "checagem": "Descrever os ajustes previstos no serviço.",
        "n2": [("Jornada do usuário no trecho afetado", EX)],
        "n3": [("Jornada completa atual (as-is)", EX), ("Jornada futura (to-be)", ID), ("Service blueprint to-be", PR)],
    },
    {
        "codigo": "C8", "titulo": "Risco Institucional", "peso": 1, "bloco": "Alcance e risco",
        "pergunta": "Qual o nível de exposição, criticidade ou risco reputacional/operacional para a organização caso a iniciativa falhe ou seja mal desenhada?",
        "opcoes": [
            "A iniciativa apresenta riscos baixos, com impactos limitados e facilmente controláveis.",
            "A iniciativa apresenta riscos moderados, que exigem identificação, acompanhamento e medidas de mitigação.",
            "A iniciativa apresenta riscos elevados, com potencial de gerar consequências institucionais, operacionais, jurídicas ou reputacionais significativas.",
        ],
        "checagem": "Registrar os riscos conhecidos no plano.",
        "n2": [("Matriz de riscos", PR), ("Monitoramento de riscos na operação", AV)],
        "n3": [("Protótipo de alta fidelidade", PR), ("Piloto controlado com plano de reversão", AV), ("Ciclos de melhoria programados", AV)],
    },
    {
        "codigo": "C9", "titulo": "Mudança de Comportamento", "peso": 1, "bloco": "Implantação",
        "pergunta": "Em que medida a solução exigirá mudanças de comportamento, hábitos ou rotinas dos usuários e operadores do serviço?",
        "opcoes": [
            "A solução se integra às práticas e rotinas existentes, exigindo pouca ou nenhuma mudança de comportamento.",
            "A solução exige adaptações moderadas nas rotinas, com necessidade de comunicação, capacitação ou acompanhamento.",
            "A solução exige mudanças significativas de hábitos, práticas ou cultura organizacional, sendo necessária uma estratégia estruturada de gestão da mudança.",
        ],
        "checagem": "Comunicar a mudança aos usuários e operadores.",
        "n2": [("Plano de comunicação e capacitação", AV)],
        "n3": [("Testes com operadores do serviço", PR), ("Estratégia de gestão da mudança", AV)],
    },
    {
        "codigo": "C10", "titulo": "Dependências Técnicas e Legais", "peso": 1, "bloco": "Implantação",
        "pergunta": "A demanda depende de adequações normativas, marcos regulatórios, integração de sistemas legados ou infraestrutura tecnológica específica?",
        "opcoes": [
            "A demanda possui poucas dependências técnicas ou legais, já identificadas e compreendidas, sem obstáculos relevantes à execução.",
            "A demanda possui dependências que exigem alinhamentos, adequações, integrações ou validações com outras áreas.",
            "A demanda possui múltiplas dependências técnicas, normativas ou institucionais complexas, com incertezas que podem comprometer significativamente sua execução.",
        ],
        "checagem": "Listar as dependências conhecidas.",
        "n2": [("Mapa de sistemas e normas envolvidos", HO), ("Rituais de acompanhamento com o time de desenvolvimento", HO)],
        "n3": [("Service blueprint com camada de bastidores (backstage)", HO), ("Análise de integrações e normativa", HO), ("Entregas por incrementos", HO)],
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
     "pergunta": "Envolve dados pessoais sensíveis, monitoramento ou perfilamento de pessoas?",
     "acao": "Consultar o encarregado de dados (DPO); elaborar o Relatório de Impacto à Proteção de Dados (RIPD); usar dados fictícios ou minimizados nos protótipos.",
     "etapa": "Exploração · Handover"},
    {"codigo": "T2", "titulo": "Segurança, Continuidade e Disponibilidade",
     "pergunta": "Falhas ou indisponibilidade podem impactar serviços essenciais ou a imagem institucional?",
     "acao": "Elaborar plano de contingência e realizar testes de disponibilidade antes do piloto.",
     "etapa": "Handover · Avaliação"},
    {"codigo": "T3", "titulo": "Direitos, Obrigações e Regulatório",
     "pergunta": "Afeta atos normativos, sanções, fiscalização ou obrigações contratuais não negociáveis?",
     "acao": "Realizar análise normativa com a área jurídica; incorporar as normas como restrições no blueprint.",
     "etapa": "Alinhamento · Handover"},
    {"codigo": "T4", "titulo": "Inteligência Artificial / Decisão Automatizada",
     "pergunta": "Aplica modelos analíticos ou algoritmos para tomar decisões sobre cidadãos ou usuários?",
     "acao": "Realizar avaliação de impacto algorítmico; prever revisão humana e canal de contestação das decisões.",
     "etapa": "Ideação · Prototipação"},
    {"codigo": "T5", "titulo": "Acessibilidade e Inclusão Digital",
     "pergunta": "Existem barreiras significativas para pessoas com deficiência, idosos ou pessoas de baixa conectividade?",
     "acao": "Testar com pessoas com deficiência, idosos e usuários de baixa conectividade; verificar conformidade com o eMAG; manter canal alternativo não digital.",
     "etapa": "Prototipação · Avaliação"},
    {"codigo": "T6", "titulo": "Transparência e Explicabilidade",
     "pergunta": "Os motivos dos resultados ou decisões precisam ser claramente compreendidos pelo público?",
     "acao": "Aplicar linguagem simples e testar a compreensão das mensagens de resultado e decisão.",
     "etapa": "Prototipação · Avaliação"},
    {"codigo": "T7", "titulo": "Contato com Usuários / Acesso Limitado",
     "pergunta": "Há risco de não ser possível validar hipóteses com o público final?",
     "acao": "Usar fontes substitutas (atendentes, ouvidoria, dados secundários) e registrar as hipóteses não validadas como risco.",
     "etapa": "Exploração"},
    {"codigo": "T8", "titulo": "Engajamento e Governança",
     "pergunta": "Há ausência de patrocinador ou responsável decisório claro, ou indisponibilidade de decisão?",
     "acao": "Formalizar termo de abertura com patrocinador nomeado e rito de decisão antes de sair do Alinhamento.",
     "etapa": "Alinhamento"},
]
CONDICOES_POR_CODIGO = {t["codigo"]: t for t in CONDICOES}

# Entrada e saída de cada etapa.
#   entrada: o que a etapa recebe quando vem depois de outra etapa ativa
#   entrada_direta: o que ela recebe quando é o ponto de entrada (etapas anteriores dispensadas)
#   saida: o que a etapa entrega
#   pronta_quando: condição para passar à etapa seguinte
ENTRADA_SAIDA = {
    AL: {"entrada": ["Demanda da unidade", "Diagnóstico consolidado na oficina"],
         "saida": ["Termo de abertura com patrocinador e rito de decisão", "Escopo e desafio aprovados", "Mapa de atores"],
         "pronta_quando": "O patrocinador aprova o escopo e o desafio."},
    EX: {"entrada": ["Escopo e desafio aprovados", "Mapa de atores"],
         "saida": ["Problema reenquadrado", "Evidências e relatório de pesquisa", "Personas", "Jornada atual (as-is)"],
         "pronta_quando": "O demandante valida o problema e as evidências."},
    ID: {"entrada": ["Problema reenquadrado", "Personas e jornada atual"],
         "entrada_direta": ["Escopo e desafio aprovados", "Problema e evidências já conhecidos"],
         "saida": ["Conceito de solução escolhido", "Jornada futura (to-be)"],
         "pronta_quando": "O patrocinador aprova o conceito."},
    PR: {"entrada": ["Conceito escolhido", "Jornada futura (to-be)"],
         "entrada_direta": ["Escopo aprovado", "Proposta de solução existente"],
         "saida": ["Solução testada com usuários", "Service blueprint"],
         "pronta_quando": "Os testes mostram que a solução resolve o problema."},
    HO: {"entrada": ["Solução validada"],
         "entrada_paralela": ["Partes da solução validadas na prototipação, por incrementos"],
         "entrada_direta": ["Escopo aprovado", "Solução definida e validada"],
         "saida": ["Histórias de usuário com critérios de aceite", "Blueprint para o time de desenvolvimento", "Acordo de integração"],
         "pronta_quando": "As entregas estão no backlog do desenvolvimento.",
         # Sem sistema envolvido, o handover é a transferência do processo à área responsável.
         "saida_sem_sistema": ["Novo processo documentado", "Área responsável capacitada"],
         "pronta_quando_sem_sistema": "A área responsável assume o novo processo."},
    AV: {"entrada": ["Solução em operação (piloto ou implantação)", "Indicadores definidos"],
         "saida": ["Indicadores medidos", "Backlog de melhorias"],
         "pronta_quando": "O próximo ciclo de melhoria está definido."},
}

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
def analisar_criterio(valores):
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

    if amplitude == 0 or (concordancia >= LIMIAR_CONSENSO and amplitude <= 1):
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


def analisar_condicao(valores):
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

    if len(set(valores)) == 1 or (concordancia >= LIMIAR_CONSENSO and not conflito):
        status = "consenso"
    elif conflito:
        status = "alta"
    else:
        status = "moderada"
    sugestao = max(modas, key=lambda k: PRECAUCAO_T[k])
    return {"n": n, "dist": dist, "status": status, "sugestao": sugestao,
            "concordancia": round(concordancia * 100)}


def analisar_oficina(respostas_participantes):
    """respostas_participantes: lista de dicts {codigo: valor} dos que enviaram."""
    analise = {}
    for c in CRITERIOS:
        analise[c["codigo"]] = analisar_criterio(
            [r.get(c["codigo"]) for r in respostas_participantes if r.get(c["codigo"])])
    for t in CONDICOES:
        analise[t["codigo"]] = analisar_condicao(
            [r.get(t["codigo"]) for r in respostas_participantes if r.get(t["codigo"])])
    return analise


# ---------------------------------------------------------------------------
# Geração do plano metodológico
# ---------------------------------------------------------------------------
def niveis_efetivos(niveis):
    """Critérios de peso 2 (C1 e C5) no nível b passam a valer como c."""
    efetivos = {}
    for cod, nivel in niveis.items():
        crit = CRITERIOS_POR_CODIGO.get(cod)
        if crit and crit["peso"] > 1 and nivel == 2:
            efetivos[cod] = 3
        else:
            efetivos[cod] = nivel
    return efetivos


def ponto_entrada(niveis):
    """Etapa em que o trabalho continua depois do Alinhamento e Escopo.

    Recebe os níveis consolidados; aplica internamente a regra de peso.
    """
    ef = niveis_efetivos(niveis)
    c1, c2, c3, c4 = (ef.get(k) for k in ("C1", "C2", "C3", "C4"))
    if c1 == 3 or c2 == 3 or c3 == 3:
        motivos, pesados = [], []
        for cod in ("C1", "C2", "C3"):
            if ef.get(cod) == 3:
                motivos.append(FRASES[cod][niveis[cod] - 1])
                if niveis[cod] != 3:
                    pesados.append(cod)
        texto = ("Depois do alinhamento, o trabalho segue para a exploração do problema, porque "
                 + _juntar(motivos) + ".")
        if pesados:
            texto += " A clareza do problema tem peso dobrado no diagnóstico, por isso qualquer dúvida sobre ela já leva à exploração."
        return EX, texto
    if c4 == 3:
        return ID, ("O problema já está compreendido, mas a solução ainda não está definida. Depois do alinhamento, "
                    "o trabalho segue para a ideação, para gerar e comparar alternativas.")
    if c4 == 2:
        return PR, ("Já existe uma proposta de solução que precisa ser refinada e testada. Depois do alinhamento, "
                    "o trabalho segue para a prototipação, sem necessidade de nova exploração ou ideação.")
    return HO, ("A solução já está definida e validada. Depois do alinhamento, o trabalho segue "
                "diretamente para o handover ao desenvolvimento.")


def _separar_itens(texto):
    if not texto:
        return []
    partes = []
    for linha in str(texto).replace(";", "\n").splitlines():
        linha = linha.strip(" -•\t")
        if linha:
            partes.append(linha)
    return partes


def gerar_plano(contexto, niveis, condicoes, registro=None):
    """
    contexto: dict com os campos de identificação/contextualização.
    niveis: {"C1": 1..3, ...} valores consolidados.
    condicoes: {"T1": "yes"|..., ...} valores consolidados.
    registro: {"C1": {"status":..., "justificativa":..., "concordancia":...}, ...}
    """
    registro = registro or {}
    ef = niveis_efetivos(niveis)
    entrada, justificativa = ponto_entrada(niveis)
    tem_sistema = bool(_separar_itens(contexto.get("sistemas_envolvidos")))

    # Situação de cada etapa
    situacao = {}
    for etapa in ETAPAS:
        if etapa in ETAPAS_SEMPRE:
            situacao[etapa] = "ativa"
        elif ETAPAS.index(etapa) < ETAPAS.index(entrada):
            situacao[etapa] = "dispensada"
        else:
            situacao[etapa] = "ativa"
    # Uma etapa dispensável que vem antes da entrada transfere suas técnicas para a entrada.
    destino_preparatorio = entrada if entrada in ETAPAS_DISPENSAVEIS else HO

    tecnicas = {e: {} for e in ETAPAS}

    # Todas as técnicas são sugestões; "prioridade" só ordena a lista (nível c antes do b).
    def adicionar(nome, etapa, prioridade, origem):
        preparatoria = situacao[etapa] == "dispensada"
        destino = destino_preparatorio if preparatoria else etapa
        item = tecnicas[destino].setdefault(nome, {"nome": nome, "origens": [], "prioridade": prioridade,
                                                   "preparatoria": preparatoria})
        if origem and origem not in item["origens"]:
            item["origens"].append(origem)
        item["prioridade"] = min(item["prioridade"], prioridade)
        item["preparatoria"] = item["preparatoria"] and preparatoria

    for etapa in ETAPAS:
        if situacao[etapa] == "ativa":
            base = TECNICAS_BASE[etapa]
            if etapa == HO and not tem_sistema:
                base = ["Transferência do novo processo à área responsável (procedimentos e capacitação)"]
            for nome in base:
                adicionar(nome, etapa, 0, None)

    checagens = []
    for c in CRITERIOS:
        nivel = ef.get(c["codigo"])
        if nivel is None:
            continue
        if nivel == 1:
            checagens.append((c["codigo"], c["titulo"], c["checagem"]))
            continue
        if nivel == 2:
            lista = [(nome, etapa, 2) for nome, etapa in c["n2"]]
        else:
            lista = [(nome, etapa, 1) for nome, etapa in c["n2"] + c["n3"]]
        for nome, etapa, prioridade in lista:
            if etapa == HO and not tem_sistema and nome != "Análise de integrações e normativa":
                continue
            adicionar(nome, etapa, prioridade, c["codigo"])

    # Intensidade de cada etapa
    percurso = []
    for etapa in ETAPAS:
        motores = MOTORES[etapa]
        maximo = max((ef.get(m) or 1) for m in motores)
        intensidade = INTENSIDADE[maximo]
        motivo = ", ".join(f"{m} = {letra(niveis.get(m))}" + (" (peso 2)" if ef.get(m) != niveis.get(m) else "")
                           for m in motores if (ef.get(m) or 1) == maximo) if maximo > 1 else "todos os critérios no nível a"
        if etapa == HO and not tem_sistema:
            intensidade, motivo = "Baixa", "nenhum sistema envolvido informado"
        if situacao[etapa] == "dispensada":
            intensidade, motivo = None, "anterior ao ponto de entrada"
        itens = sorted(tecnicas[etapa].values(),
                       key=lambda i: (i["prioridade"], i["preparatoria"], (i["origens"] or ["C0"])[0]))
        # Entrada e saída da etapa
        es = ENTRADA_SAIDA[etapa]
        if etapa == entrada and "entrada_direta" in es:
            entrada_itens = es["entrada_direta"]
        elif etapa == HO and situacao[PR] == "ativa":
            entrada_itens = es["entrada_paralela"]
        else:
            entrada_itens = es["entrada"]
        saida_itens, pronta = es["saida"], es["pronta_quando"]
        if etapa == HO and not tem_sistema:
            saida_itens, pronta = es["saida_sem_sistema"], es["pronta_quando_sem_sistema"]
        percurso.append({
            "fase": etapa,
            "ativa": situacao[etapa] == "ativa",
            "entrada": etapa == entrada,
            "inicio": etapa == AL,
            "na_oficina": False,
            "sempre": etapa in ETAPAS_SEMPRE,
            "intensidade": intensidade,
            "motivo_intensidade": motivo,
            "texto_intensidade": (justificar_intensidade(etapa, intensidade, niveis, ef, tem_sistema)
                                  if intensidade else None),
            "motores": motores,
            "tecnicas": itens,
            "curta": ETAPA_CURTA[etapa],
            "entrada_itens": entrada_itens,
            "saida_itens": saida_itens,
            "pronta_quando": pronta,
        })

    paralelo = situacao[PR] == "ativa"

    # Alinhamento já feito na oficina
    na_oficina = alinhamento_na_oficina(niveis, condicoes)
    if na_oficina:
        al = percurso[0]
        al.update({
            "na_oficina": True,
            "intensidade": "Baixa",
            "texto_intensidade": {"porque": ALINHAMENTO_NA_OFICINA["porque"],
                                  "orientacao": ALINHAMENTO_NA_OFICINA["orientacao"], "focos": []},
            "entrada_itens": ALINHAMENTO_NA_OFICINA["entrada"],
            "saida_itens": ALINHAMENTO_NA_OFICINA["saida"],
            "pronta_quando": ALINHAMENTO_NA_OFICINA["pronta_quando"],
            "tecnicas": [t for t in al["tecnicas"] if not t["origens"]],  # só o termo de abertura
        })

    # Envolvimento de atores (com a regra de peso aplicada a C5)
    c5, c6 = ef.get("C5"), ef.get("C6")
    envolvimento = {
        1: "Consulta pontual aos usuários e à área responsável.",
        2: "Entrevistas e validações com cada grupo de usuários e áreas envolvidas.",
        3: "Cocriação contínua com os diferentes públicos ao longo de todas as etapas.",
    }.get(c5, "")
    if c6 == 2:
        envolvimento += " Prever rodadas de alinhamento entre as áreas antes das decisões."
    elif c6 == 3:
        envolvimento += " Conduzir as decisões em oficinas mediadas, com acordo de decisão registrado."

    atores = []
    for p in contexto.get("publicos_afetados", []) or []:
        if p == "Outros":
            for o in _separar_itens(contexto.get("publicos_outros")):
                atores.append({"nome": o, "tipo": "Público afetado"})
        else:
            atores.append({"nome": p, "tipo": "Público afetado"})
    for u in _separar_itens(contexto.get("unidades_envolvidas")):
        atores.append({"nome": u, "tipo": "Unidade envolvida"})
    for i in _separar_itens(contexto.get("instituicoes_externas")):
        atores.append({"nome": i, "tipo": "Instituição externa"})

    # Salvaguardas
    salvaguardas = []
    for t in CONDICOES:
        resp = condicoes.get(t["codigo"])
        if resp not in ("yes", "unknown", "partial"):
            continue
        salvaguardas.append({**t, "resposta": RESPOSTAS_T[resp], "presente": resp in ("yes", "unknown"),
                             "avaliacao_pendente": resp == "unknown"})

    # Riscos derivados automaticamente do diagnóstico
    riscos = []
    if niveis.get("C8") == 3:
        riscos.append(("Risco institucional elevado",
                       "Uma falha pode trazer consequências institucionais, jurídicas ou de imagem. Implantar primeiro em piloto controlado, com plano de reversão, antes de ampliar."))
    if niveis.get("C10") == 3:
        riscos.append(("Dependências técnicas e normativas complexas",
                       "Integrações e adequações normativas podem travar o desenvolvimento. Tratá-las como marcos do handover e acompanhá-las com o time de desenvolvimento."))
    if niveis.get("C6") == 3:
        riscos.append(("Conflito de interesses entre os atores",
                       "Divergências entre as áreas podem paralisar as decisões. Registrar no alinhamento quem decide e como as divergências serão resolvidas."))
    if niveis.get("C9") == 3:
        riscos.append(("Resistência à mudança",
                       "A solução muda hábitos de usuários e operadores. Envolver os operadores desde os testes e preparar uma estratégia de gestão da mudança."))
    if paralelo:
        riscos.append(("Desenvolvimento à frente da validação",
                       "Como prototipação e handover correm juntos, o desenvolvimento pode construir algo ainda não testado. Entregar ao time apenas o que já foi validado, por incrementos."))
    for cod, reg in registro.items():
        if reg.get("status") == "alta" and cod in CRITERIOS_POR_CODIGO:
            riscos.append((f"Grupo dividido sobre {CRITERIOS_POR_CODIGO[cod]['titulo'].lower()}",
                           "Na oficina houve respostas opostas sobre este ponto. Revisar a decisão ao final da primeira etapa após o alinhamento, à luz das evidências levantadas."))

    atencao = []
    for s_ in salvaguardas:
        if s_["avaliacao_pendente"]:
            detalhe = "O grupo não soube avaliar. Tratar como presente até haver avaliação especializada."
        elif s_["presente"]:
            detalhe = "O grupo identificou esta condição na iniciativa."
        else:
            detalhe = "O grupo identificou indícios desta condição."
        atencao.append({"titulo": s_["titulo"], "acao": s_["acao"], "etapa": s_["etapa"], "detalhe": detalhe})
    atencao += [{"titulo": r, "acao": m, "etapa": "", "detalhe": ""} for r, m in riscos]

    perfil = [{"codigo": c["codigo"], "titulo": c["titulo"], "bloco": c["bloco"], "peso": c["peso"],
               "nivel": niveis.get(c["codigo"]), "letra": letra(niveis.get(c["codigo"])),
               "rotulo": ROTULOS[c["codigo"]][niveis[c["codigo"]] - 1] if niveis.get(c["codigo"]) else "",
               "peso_aplicado": ef.get(c["codigo"]) != niveis.get(c["codigo"]),
               "texto": c["opcoes"][niveis[c["codigo"]] - 1] if niveis.get(c["codigo"]) else "",
               "status": registro.get(c["codigo"], {}).get("status"),
               "concordancia": registro.get(c["codigo"], {}).get("concordancia")}
              for c in CRITERIOS]

    return {
        "ponto_entrada": entrada,
        "justificativa_entrada": justificativa,
        "fases_ativas": [p["fase"] for p in percurso if p["ativa"]],
        "perfil": perfil,
        "percurso": percurso,
        "checagens": checagens,
        "paralelo": paralelo,
        "alinhamento_na_oficina": na_oficina,
        "sem_sistema": not tem_sistema,
        "envolvimento": envolvimento.strip(),
        "cocriacao_transversal": c5 == 3,
        "atores": atores,
        "salvaguardas": salvaguardas,
        "riscos": riscos,
        "atencao": atencao,
    }
