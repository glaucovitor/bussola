"""Motor do plano metodológico, guiado por um conjunto de regras editável.

As regras ficam num dicionário (JSON) com a estrutura de `regras_padrao.json`.
Este módulo não guarda nenhuma regra própria: tudo o que decide o plano —
ponto de entrada, intensidade, técnicas, focos, exceções, riscos e textos —
vem do dicionário recebido. Cada decisão tomada é registrada em linguagem
simples, para que o plano mostre quais regras foram aplicadas.
"""
import copy
import json
import os
import re

import rules

CAMINHO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regras_padrao.json")

INTENSIDADES = {3: "Alta", 2: "Média", 1: "Baixa"}
NIVEL_INTENSIDADE = {"Alta": 3, "Média": 2, "Baixa": 1}
CONTEXTOS = {
    "sem_sistema": "nenhum sistema envolvido foi informado",
    "com_sistema": "há sistema envolvido informado",
    "paralelo": "a prototipação e o handover correm em paralelo",
}
MODOS = {"todas": "todas as condições", "qualquer": "qualquer uma das condições"}
CODIGOS_C = [c["codigo"] for c in rules.CRITERIOS]
CODIGOS_T = [t["codigo"] for t in rules.CONDICOES]


# ---------------------------------------------------------------------------
# Carregar, normalizar e validar
# ---------------------------------------------------------------------------
def regras_padrao():
    with open(CAMINHO_PADRAO, encoding="utf-8") as f:
        return json.load(f)


def normalizar(R):
    """Completa campos ausentes com os valores padrão (versões antigas ou importadas)."""
    base = regras_padrao()
    R = copy.deepcopy(R or {})
    for chave, valor in base.items():
        if chave not in R:
            R[chave] = copy.deepcopy(valor)
    for cod, dados in base["criterios"].items():
        R["criterios"].setdefault(cod, copy.deepcopy(dados))
        for k, v in dados.items():
            R["criterios"][cod].setdefault(k, copy.deepcopy(v))
    for cod, dados in base["condicoes_especiais"].items():
        R["condicoes_especiais"].setdefault(cod, copy.deepcopy(dados))
    campos_etapa = base["etapas"][0].keys()
    for e in R["etapas"]:
        for k in campos_etapa:
            e.setdefault(k, [] if k in ("entrada", "entrada_direta", "entrada_paralela", "saida",
                                         "tecnicas_base", "criterios_intensidade") else "")
        e.setdefault("orientacao", {})
        for nivel in ("Alta", "Média", "Baixa"):
            e["orientacao"].setdefault(nivel, "")
    for ex in R["excecoes"]:
        for k, v in {"rotulo_percurso": "", "selo": "", "porque": "", "orientacao": "", "entrada": [],
                     "saida": [], "avanca_quando": "", "tecnicas_base": [], "tecnicas_criterios": "manter",
                     "tecnicas_manter": [], "focos": "manter", "focos_manter": [], "intensidade": ""}.items():
            ex.setdefault(k, v)
    for r in R["ponto_entrada"]["regras"]:
        r.setdefault("texto_peso", "")
    for k, v in base["mapa"].items():
        R["mapa"].setdefault(k, copy.deepcopy(v))
    for k in ("rotulo_menor", "rotulo_maior"):
        if not str(R["mapa"].get(k) or "").strip():
            R["mapa"][k] = base["mapa"][k]
    for q, v in base["mapa"]["quadrantes"].items():
        R["mapa"]["quadrantes"].setdefault(q, copy.deepcopy(v))
    for eixo in ("eixo_x", "eixo_y"):
        R["mapa"][eixo].setdefault("pesos", {})
        for cod in CODIGOS_C:
            R["mapa"][eixo]["pesos"].setdefault(cod, 0)
    return R


def validar(R):
    """Devolve uma lista de problemas encontrados (vazia se estiver tudo certo)."""
    erros = []
    try:
        etapas = [e["codigo"] for e in R["etapas"]]
    except (KeyError, TypeError):
        return ["A lista de etapas está ausente ou mal formada."]
    if len(set(etapas)) != len(etapas):
        erros.append("Há etapas com o mesmo código.")
    for e in R["etapas"]:
        if not str(e.get("nome", "")).strip():
            erros.append(f"A etapa {e.get('codigo')} está sem nome.")
        for c in e.get("criterios_intensidade", []):
            if c not in CODIGOS_C:
                erros.append(f"A etapa {e['nome']} usa um critério inexistente: {c}.")

    def checar_condicoes(onde, conds, obrigatorio=True):
        if obrigatorio and not conds:
            erros.append(f"{onde}: precisa de pelo menos uma condição.")
        for c in conds or []:
            tipo = c.get("tipo")
            if tipo == "criterio":
                if c.get("criterio") not in CODIGOS_C:
                    erros.append(f"{onde}: critério inexistente ({c.get('criterio')}).")
                if not c.get("niveis") or any(n not in (1, 2, 3) for n in c["niveis"]):
                    erros.append(f"{onde}: escolha ao menos um nível válido para {c.get('criterio')}.")
            elif tipo == "condicao":
                if c.get("condicao") not in CODIGOS_T:
                    erros.append(f"{onde}: condição especial inexistente ({c.get('condicao')}).")
                if not c.get("respostas") or any(r not in rules.RESPOSTAS_T for r in c["respostas"]):
                    erros.append(f"{onde}: escolha ao menos uma resposta válida para {c.get('condicao')}.")
            elif tipo == "contexto":
                if c.get("contexto") not in CONTEXTOS:
                    erros.append(f"{onde}: contexto desconhecido ({c.get('contexto')}).")
            else:
                erros.append(f"{onde}: tipo de condição desconhecido ({tipo}).")

    for i, r in enumerate(R["ponto_entrada"]["regras"], 1):
        onde = f"Ponto de entrada, regra {i} ({r.get('nome') or 'sem nome'})"
        if r.get("etapa") not in etapas:
            erros.append(f"{onde}: etapa inexistente.")
        if r.get("modo") not in MODOS:
            erros.append(f"{onde}: modo deve ser 'todas' ou 'qualquer'.")
        checar_condicoes(onde, r.get("condicoes"))
    if R["ponto_entrada"].get("padrao", {}).get("etapa") not in etapas:
        erros.append("Ponto de entrada padrão: etapa inexistente.")

    for ex in R["excecoes"]:
        onde = f"Exceção “{ex.get('nome') or ex.get('id')}”"
        if ex.get("etapa") not in etapas:
            erros.append(f"{onde}: etapa inexistente.")
        if ex.get("intensidade") not in ("", "Alta", "Média", "Baixa"):
            erros.append(f"{onde}: intensidade inválida.")
        checar_condicoes(onde, ex.get("condicoes"))
    for t in R["tecnicas"]:
        onde = f"Técnica “{t.get('nome') or 'sem nome'}”"
        if not str(t.get("nome", "")).strip():
            erros.append("Há uma técnica sem nome.")
        if t.get("etapa") not in etapas:
            erros.append(f"{onde}: etapa inexistente.")
        if t.get("criterio") not in CODIGOS_C:
            erros.append(f"{onde}: critério inexistente.")
        if not t.get("niveis") or any(n not in (2, 3) for n in t["niveis"]):
            erros.append(f"{onde}: marque em quais níveis (médio e/ou alto) ela é sugerida.")
    for f in R["focos"]:
        onde = f"Foco “{str(f.get('texto', ''))[:40]}”"
        if f.get("etapa") not in etapas or f.get("criterio") not in CODIGOS_C:
            erros.append(f"{onde}: etapa ou critério inexistente.")
        if not f.get("niveis"):
            erros.append(f"{onde}: marque ao menos um nível.")
    for r in R["riscos"]:
        checar_condicoes(f"Risco “{r.get('titulo') or 'sem título'}”", r.get("condicoes"))
    for r in R["envolvimento"]:
        checar_condicoes(f"Envolvimento “{str(r.get('texto', ''))[:40]}”", r.get("condicoes"))
    for cod, d in R["criterios"].items():
        if len(d.get("rotulos", [])) != 3 or len(d.get("frases", [])) != 3:
            erros.append(f"{cod}: são necessários 3 rótulos e 3 frases.")
    par = R.get("paralelo") or {}
    if par.get("ativo") and (par.get("de") not in etapas or par.get("para") not in etapas):
        erros.append("Etapas em paralelo: escolha etapas existentes.")
    mapa = R.get("mapa") or {}
    if mapa.get("ativo"):
        for eixo, nome in (("eixo_x", "horizontal"), ("eixo_y", "vertical")):
            pesos = (mapa.get(eixo) or {}).get("pesos") or {}
            try:
                valores = [float(v) for v in pesos.values()]
            except (TypeError, ValueError):
                erros.append(f"Mapa do diagnóstico: pesos inválidos no eixo {nome}.")
                continue
            if any(v < 0 for v in valores):
                erros.append(f"Mapa do diagnóstico: os pesos do eixo {nome} não podem ser negativos.")
            if not any(v > 0 for v in valores):
                erros.append(f"Mapa do diagnóstico: o eixo {nome} precisa de pelo menos um critério com peso.")
            if any(c not in CODIGOS_C for c in pesos):
                erros.append(f"Mapa do diagnóstico: critério inexistente no eixo {nome}.")
        for q in QUADRANTES:
            if not str(((mapa.get("quadrantes") or {}).get(q) or {}).get("nome", "")).strip():
                erros.append(f"Mapa do diagnóstico: dê um nome ao quadrante {NOME_QUADRANTE_POSICAO[q]}.")
    try:
        limiar = float(R["consenso"]["limiar"])
        if not 0.5 <= limiar <= 1:
            erros.append("O limiar de consenso deve ficar entre 50% e 100%.")
    except (KeyError, TypeError, ValueError):
        erros.append("Limiar de consenso inválido.")
    return erros


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
class _Seguro(dict):
    def __missing__(self, chave):
        return "{" + chave + "}"


def preencher(modelo, **valores):
    """Substitui {marcadores} no texto; marcadores desconhecidos ficam como estão."""
    return str(modelo or "").format_map(_Seguro(**valores))


def juntar(itens):
    itens = [i for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def titulo_criterio(cod):
    return rules.CRITERIOS_POR_CODIGO[cod]["titulo"]


def titulo_condicao(cod):
    return rules.CONDICOES_POR_CODIGO[cod]["titulo"]


def rotulo_nivel(R, cod, nivel):
    try:
        return R["criterios"][cod]["rotulos"][nivel - 1]
    except (KeyError, IndexError, TypeError):
        return rules.letra(nivel)


def descrever_condicao(R, c):
    """Descrição abstrata, usada na página de regras. Ex.: 'Clareza do Problema: Indefinido'."""
    if c["tipo"] == "criterio":
        niveis = " ou ".join(rotulo_nivel(R, c["criterio"], n) for n in sorted(c["niveis"]))
        return f"{titulo_criterio(c['criterio'])}: {niveis}"
    if c["tipo"] == "condicao":
        resp = " ou ".join(rules.RESPOSTAS_T[r] for r in c["respostas"])
        return f"{titulo_condicao(c['condicao'])}: {resp}"
    return CONTEXTOS.get(c.get("contexto"), c.get("contexto", "")).capitalize()


def descrever_regra(R, modo, condicoes):
    partes = [descrever_condicao(R, c) for c in condicoes]
    if len(partes) == 1:
        return partes[0]
    ligacao = " e " if modo == "todas" else " ou "
    return ligacao.join(partes)


# ---------------------------------------------------------------------------
# Avaliação das condições
# ---------------------------------------------------------------------------
class Situacao:
    """Respostas consolidadas e contexto, com o peso dobrado já aplicado."""

    def __init__(self, R, contexto, niveis, condicoes):
        self.R = R
        self.niveis = {k: v for k, v in niveis.items() if v in (1, 2, 3)}
        self.condicoes = condicoes
        self.tem_sistema = bool(_separar_itens(contexto.get("sistemas_envolvidos")))
        self.paralelo = False
        self.efetivos = {}
        for cod, nivel in self.niveis.items():
            pesa = R["criterios"].get(cod, {}).get("peso_dobrado")
            self.efetivos[cod] = 3 if (pesa and nivel == 2) else nivel

    def ef(self, cod):
        return self.efetivos.get(cod)

    def pelo_peso(self, cod):
        return cod in self.niveis and self.efetivos[cod] != self.niveis[cod]

    def descrever_valor(self, cod):
        """Ex.: 'Clareza do Problema: Parcialmente claro (conta como Indefinido pelo peso dobrado)'."""
        real = self.niveis.get(cod)
        if real is None:
            return f"{titulo_criterio(cod)}: sem resposta"
        texto = f"{titulo_criterio(cod)}: {rotulo_nivel(self.R, cod, real)}"
        if self.pelo_peso(cod):
            texto += f" (conta como {rotulo_nivel(self.R, cod, self.efetivos[cod])} pelo peso dobrado)"
        return texto

    def atende(self, c):
        if c["tipo"] == "criterio":
            return self.ef(c["criterio"]) in c["niveis"]
        if c["tipo"] == "condicao":
            return self.condicoes.get(c["condicao"]) in c["respostas"]
        if c["tipo"] == "contexto":
            return {"sem_sistema": not self.tem_sistema, "com_sistema": self.tem_sistema,
                    "paralelo": self.paralelo}.get(c["contexto"], False)
        return False

    def avaliar(self, modo, condicoes):
        """Retorna (verdadeiro?, condições atendidas, descrição do que foi verificado)."""
        atendidas = [c for c in condicoes if self.atende(c)]
        ok = (len(atendidas) == len(condicoes)) if modo == "todas" else bool(atendidas)
        return ok and bool(condicoes), atendidas

    def explicar(self, c):
        """Descrição do valor real que levou a condição a ser atendida."""
        if c["tipo"] == "criterio":
            return self.descrever_valor(c["criterio"])
        if c["tipo"] == "condicao":
            return f"{titulo_condicao(c['condicao'])}: {rules.RESPOSTAS_T.get(self.condicoes.get(c['condicao']), 'sem resposta')}"
        return CONTEXTOS.get(c["contexto"], "").capitalize()


def _separar_itens(texto):
    if not texto:
        return []
    return [p.strip(" -•\t") for p in str(texto).replace(";", "\n").splitlines() if p.strip(" -•\t")]


# ---------------------------------------------------------------------------
# Geração do plano
# ---------------------------------------------------------------------------
def _ponto_entrada(R, S):
    for i, regra in enumerate(R["ponto_entrada"]["regras"], 1):
        ok, atendidas = S.avaliar(regra["modo"], regra["condicoes"])
        if not ok:
            continue
        crit = [c["criterio"] for c in atendidas if c["tipo"] == "criterio"]
        motivos = juntar([R["criterios"][c]["frases"][S.niveis[c] - 1] for c in crit if c in S.niveis])
        texto = preencher(regra["texto"], motivos=motivos)
        pesados = [c for c in crit if S.pelo_peso(c)]
        if pesados and regra.get("texto_peso"):
            texto += preencher(regra["texto_peso"], criterios=juntar(["a " + titulo_criterio(c).lower() for c in pesados]),
                               tem="tem" if len(pesados) == 1 else "têm")
        return regra["etapa"], texto, {
            "regra": regra.get("nome") or regra.get("id"), "ordem": i, "padrao": False,
            "condicao": descrever_regra(R, regra["modo"], regra["condicoes"]),
            "motivos": [S.explicar(c) for c in atendidas]}
    p = R["ponto_entrada"]["padrao"]
    return p["etapa"], preencher(p["texto"], motivos=""), {
        "regra": p.get("nome") or "Regra padrão", "ordem": None, "padrao": True,
        "condicao": "Nenhuma das regras anteriores se aplicou", "motivos": []}


def gerar_plano(R, contexto, niveis, condicoes, registro=None):
    """Gera o plano a partir das regras R e das respostas consolidadas do grupo.

    contexto: campos de identificação e contextualização da oficina.
    niveis: {"C1": 1..3, ...}; condicoes: {"T1": "yes"|"no"|"partial"|"unknown", ...}
    registro: situação da consolidação de cada item (para riscos de divergência).
    """
    registro = registro or {}
    S = Situacao(R, contexto, niveis, condicoes)
    etapas = R["etapas"]
    por_codigo = {e["codigo"]: e for e in etapas}
    ordem = [e["codigo"] for e in etapas]

    # 1. Ponto de entrada
    entrada, texto_entrada, rastro_entrada = _ponto_entrada(R, S)
    idx_entrada = ordem.index(entrada)

    # 2. Etapas ativas e dispensadas
    situacao, por_que_situacao = {}, {}
    for i, e in enumerate(etapas):
        cod = e["codigo"]
        if e["sempre_presente"]:
            situacao[cod], por_que_situacao[cod] = "ativa", "Etapa marcada como sempre presente."
        elif i < idx_entrada:
            situacao[cod], por_que_situacao[cod] = "dispensada", f"Vem antes do ponto de entrada ({por_codigo[entrada]['nome']})."
        elif i == idx_entrada:
            situacao[cod], por_que_situacao[cod] = "ativa", "É o ponto de entrada do percurso."
        else:
            situacao[cod], por_que_situacao[cod] = "ativa", "Vem depois do ponto de entrada."

    par = R.get("paralelo") or {}
    S.paralelo = bool(par.get("ativo") and situacao.get(par.get("de")) == "ativa"
                      and situacao.get(par.get("para")) == "ativa")

    # 3. Exceções que se aplicam
    excecoes = {}
    for ex in R["excecoes"]:
        ok, atendidas = S.avaliar(ex["modo"], ex["condicoes"])
        if ok and situacao.get(ex["etapa"]) == "ativa":
            excecoes[ex["etapa"]] = (ex, atendidas)

    # 4. Técnicas
    tecnicas = {c: {} for c in ordem}

    def adicionar(nome, etapa, prioridade, origem, nivel_origem=None):
        preparatoria = situacao[etapa] == "dispensada"
        destino = entrada if preparatoria else etapa
        item = tecnicas[destino].setdefault(nome, {"nome": nome, "origens": [], "prioridade": prioridade,
                                                   "preparatoria": preparatoria, "etapa_original": etapa,
                                                   "motivos": []})
        if origem and origem not in item["origens"]:
            item["origens"].append(origem)
            item["motivos"].append(S.descrever_valor(origem))
        item["prioridade"] = min(item["prioridade"], prioridade)
        item["preparatoria"] = item["preparatoria"] and preparatoria

    for e in etapas:
        if situacao[e["codigo"]] != "ativa":
            continue
        base = e["tecnicas_base"]
        ex = excecoes.get(e["codigo"], (None,))[0]
        if ex and ex["tecnicas_base"]:
            base = ex["tecnicas_base"]
        for nome in base:
            adicionar(nome, e["codigo"], 0, None)

    for t in R["tecnicas"]:
        nivel = S.ef(t["criterio"])
        if nivel not in t["niveis"] or t["etapa"] not in situacao:
            continue
        ex = excecoes.get(t["etapa"], (None,))[0]
        if ex and situacao[t["etapa"]] == "ativa":
            if ex["tecnicas_criterios"] == "remover":
                continue
            if ex["tecnicas_criterios"] == "manter_algumas" and t["nome"] not in ex["tecnicas_manter"]:
                continue
        adicionar(t["nome"], t["etapa"], 1 if nivel == 3 else 2, t["criterio"])

    # 5. Percurso: intensidade, textos, entrada e saída
    textos_int = R["intensidade"]
    percurso = []
    for i, e in enumerate(etapas):
        cod = e["codigo"]
        ativa = situacao[cod] == "ativa"
        motores = [m for m in e["criterios_intensidade"] if m in CODIGOS_C]
        maximo = max([S.ef(m) or 1 for m in motores] or [1])
        intensidade = INTENSIDADES[maximo] if ativa else None
        regras_aplicadas = [{"rotulo": "Situação", "texto": por_que_situacao[cod]}]
        texto = None
        focos = []
        if ativa:
            no_max = [m for m in motores if (S.ef(m) or 1) == maximo]
            partes = [R["criterios"][m]["frases"][S.niveis[m] - 1] for m in no_max if m in S.niveis]
            pesados = [m for m in no_max if S.pelo_peso(m)]
            porque = preencher(textos_int["texto_porque"], intensidade=intensidade, motivos=juntar(partes))
            if pesados:
                porque += preencher(textos_int["texto_peso"],
                                    criterios=juntar(["a " + titulo_criterio(m).lower() for m in pesados]),
                                    tem="tem" if len(pesados) == 1 else "têm")
            if motores:
                regras_aplicadas.append({"rotulo": "Intensidade", "chave": "intensidade",
                                         "texto": f"{intensidade}: maior nível entre os critérios da etapa.",
                                         "itens": [S.descrever_valor(m) for m in motores]})
            else:
                regras_aplicadas.append({"rotulo": "Intensidade", "chave": "intensidade",
                                         "texto": "Baixa: a etapa não tem critérios de intensidade definidos."})
            # focos
            ordem_motor = {m: k for k, m in enumerate(motores)}
            candidatos = [(k, f) for k, f in enumerate(R["focos"])
                          if f["etapa"] == cod and S.ef(f["criterio"]) in f["niveis"]]
            candidatos.sort(key=lambda kf: (-(S.ef(kf[1]["criterio"]) or 1),
                                            ordem_motor.get(kf[1]["criterio"], 99), kf[0]))
            focos = [f for _, f in candidatos]
            texto = {"porque": porque, "orientacao": e["orientacao"].get(intensidade, ""), "focos": []}

        # entrada da etapa
        if cod == entrada and e["entrada_direta"]:
            entrada_itens = e["entrada_direta"]
            regras_aplicadas.append({"rotulo": "Entrada", "texto": "Usada a lista “quando é o ponto de entrada”."})
        elif S.paralelo and cod == par.get("para") and e["entrada_paralela"]:
            entrada_itens = e["entrada_paralela"]
            regras_aplicadas.append({"rotulo": "Entrada", "texto": "Usada a lista “em paralelo”, pois a etapa corre "
                                     f"junto com {por_codigo[par['de']]['nome']}."})
        else:
            entrada_itens = e["entrada"]
        saida_itens, avanca = e["saida"], e["avanca_quando"]

        item = {"codigo": cod, "fase": e["nome"], "curta": e["curta"], "ativa": ativa,
                "entrada": cod == entrada, "inicio": i == 0, "sempre": e["sempre_presente"],
                "na_oficina": False, "rotulo_percurso": "", "selo": "",
                "em_paralelo": S.paralelo and cod == par.get("para"),
                "paralelo_com": por_codigo[par["de"]]["nome"] if (S.paralelo and cod == par.get("para")) else "",
                "intensidade": intensidade, "motores": motores, "texto_intensidade": texto,
                "entrada_itens": entrada_itens, "saida_itens": saida_itens, "pronta_quando": avanca}

        # exceção da etapa
        if cod in excecoes:
            ex, atendidas = excecoes[cod]
            texto_ex = f"“{ex['nome']}”, porque " + "; ".join(S.explicar(c).lower() if c["tipo"] == "contexto"
                                                              else S.explicar(c) for c in atendidas) + "."
            if ex["intensidade"] and ex["intensidade"] != item["intensidade"]:
                texto_ex += f" A exceção define a intensidade como {ex['intensidade'].lower()}."
                for r in regras_aplicadas:
                    if r.get("chave") == "intensidade":
                        r["texto"] = r["texto"].replace(": maior", " pela regra geral: maior", 1) \
                            + " Substituída pela exceção abaixo."
            regras_aplicadas.append({"rotulo": "Exceção", "texto": texto_ex})
            if ex["intensidade"]:
                item["intensidade"] = ex["intensidade"]
            if ex["porque"]:
                item["texto_intensidade"]["porque"] = ex["porque"]
            if ex["orientacao"]:
                item["texto_intensidade"]["orientacao"] = ex["orientacao"]
            if ex["entrada"]:
                item["entrada_itens"] = ex["entrada"]
            if ex["saida"]:
                item["saida_itens"] = ex["saida"]
            if ex["avanca_quando"]:
                item["pronta_quando"] = ex["avanca_quando"]
            item["rotulo_percurso"], item["selo"] = ex["rotulo_percurso"], ex["selo"]
            item["na_oficina"] = bool(ex["rotulo_percurso"])
            if ex["focos"] == "remover":
                focos = []
            elif ex["focos"] == "manter_algumas":
                focos = [f for f in focos if f["criterio"] in ex["focos_manter"]]

        if item["texto_intensidade"]:
            item["texto_intensidade"]["focos"] = [f["texto"] for f in focos]
            if focos:
                regras_aplicadas.append({"rotulo": "Focos", "itens": [
                    f"{f['texto']} — {S.descrever_valor(f['criterio'])}" for f in focos]})

        itens = sorted(tecnicas[cod].values(),
                       key=lambda t: (t["prioridade"], t["preparatoria"], (t["origens"] or ["C0"])[0]))
        item["tecnicas"] = itens
        if ativa and itens:
            linhas = []
            for t in itens:
                if not t["origens"]:
                    linhas.append(f"{t['nome']} — técnica de base da etapa")
                else:
                    extra = f" (vinda de {por_codigo[t['etapa_original']]['nome']}, etapa dispensada)" if t["preparatoria"] else ""
                    linhas.append(f"{t['nome']} — {'; '.join(t['motivos'])}{extra}")
            regras_aplicadas.append({"rotulo": "Técnicas", "itens": linhas})
        item["regras_aplicadas"] = regras_aplicadas
        percurso.append(item)

    # 6. Envolvimento dos atores
    partes_env, rastro_env = [], []
    for r in R["envolvimento"]:
        ok, atendidas = S.avaliar(r["modo"], r["condicoes"])
        if ok:
            partes_env.append(r["texto"])
            rastro_env.append("; ".join(S.explicar(c) for c in atendidas))
    envolvimento = " ".join(p.strip() for p in partes_env if p.strip())

    atores = []
    for p in contexto.get("publicos_afetados", []) or []:
        if p == "Outros":
            atores += [{"nome": o, "tipo": "Público afetado"} for o in _separar_itens(contexto.get("publicos_outros"))]
        else:
            atores.append({"nome": p, "tipo": "Público afetado"})
    atores += [{"nome": u, "tipo": "Unidade envolvida"} for u in _separar_itens(contexto.get("unidades_envolvidas"))]
    atores += [{"nome": i, "tipo": "Instituição externa"} for i in _separar_itens(contexto.get("instituicoes_externas"))]

    # 7. Pontos de atenção: condições especiais e riscos
    atencao, salvaguardas = [], []
    for cod in CODIGOS_T:
        cfg = R["condicoes_especiais"].get(cod, {})
        resp = condicoes.get(cod)
        if resp not in cfg.get("respostas", []):
            continue
        salvaguardas.append({"codigo": cod, "titulo": titulo_condicao(cod), "resposta": rules.RESPOSTAS_T[resp]})
        atencao.append({"codigo": cod, "titulo": titulo_condicao(cod), "acao": cfg["acao"], "etapa": cfg["etapa"],
                        "detalhe": R["textos_resposta"].get(resp, ""),
                        "motivo": f"Resposta do grupo: {rules.RESPOSTAS_T[resp]}."})
    riscos = []
    for r in R["riscos"]:
        ok, atendidas = S.avaliar(r["modo"], r["condicoes"])
        if ok:
            riscos.append((r["titulo"], r["texto"]))
            atencao.append({"titulo": r["titulo"], "acao": r["texto"], "etapa": "", "detalhe": "",
                            "motivo": "Regra de risco: " + "; ".join(S.explicar(c) for c in atendidas) + "."})
    div = R.get("risco_divergencia") or {}
    if div.get("ativo"):
        for cod in CODIGOS_C:
            if registro.get(cod, {}).get("status") == "alta":
                titulo = preencher(div["titulo"], criterio=titulo_criterio(cod).lower())
                riscos.append((titulo, div["texto"]))
                atencao.append({"titulo": titulo, "acao": div["texto"], "etapa": "", "detalhe": "",
                                "motivo": "Na consolidação, este critério teve respostas nos dois extremos."})

    # 8. Diagnóstico
    perfil = []
    for c in rules.CRITERIOS:
        cod, nivel = c["codigo"], S.niveis.get(c["codigo"])
        perfil.append({"codigo": cod, "titulo": c["titulo"], "bloco": c["bloco"],
                       "peso": 2 if R["criterios"][cod]["peso_dobrado"] else 1,
                       "nivel": nivel, "letra": rules.letra(nivel),
                       "rotulo": rotulo_nivel(R, cod, nivel) if nivel else "",
                       "peso_aplicado": S.pelo_peso(cod),
                       "texto": c["opcoes"][nivel - 1] if nivel else "",
                       "status": registro.get(cod, {}).get("status"),
                       "concordancia": registro.get(cod, {}).get("concordancia")})

    return {
        "ponto_entrada": por_codigo[entrada]["nome"],
        "ponto_entrada_codigo": entrada,
        "justificativa_entrada": texto_entrada,
        "rastro_entrada": rastro_entrada,
        "fases_ativas": [p["fase"] for p in percurso if p["ativa"]],
        "perfil": perfil,
        "percurso": percurso,
        "paralelo": S.paralelo,
        "alinhamento_na_oficina": any(p["na_oficina"] for p in percurso),
        "sem_sistema": not S.tem_sistema,
        "envolvimento": envolvimento,
        "rastro_envolvimento": rastro_env,
        "cocriacao_transversal": S.ef("C5") == 3,
        "atores": atores,
        "salvaguardas": salvaguardas,
        "riscos": riscos,
        "atencao": atencao,
        "definicoes_intensidade": R["intensidade"]["definicoes"],
    }


# ---------------------------------------------------------------------------
# Simulação (usada pelo editor para testar regras antes de salvar)
# ---------------------------------------------------------------------------
def simular(R, niveis, condicoes, tem_sistema=True):
    contexto = {"sistemas_envolvidos": "Sistema" if tem_sistema else ""}
    plano = gerar_plano(R, contexto, niveis, condicoes)
    plano["mapa"] = montar_mapa(R, niveis)
    return plano


MARCADORES = re.compile(r"\{(\w+)\}")


# ---------------------------------------------------------------------------
# Mapa do diagnóstico (plano cartesiano)
# ---------------------------------------------------------------------------
QUADRANTES = ["superior_esquerdo", "superior_direito", "inferior_esquerdo", "inferior_direito"]
NOME_QUADRANTE_POSICAO = {"superior_esquerdo": "superior esquerdo", "superior_direito": "superior direito",
                          "inferior_esquerdo": "inferior esquerdo", "inferior_direito": "inferior direito"}


def posicao_eixo(pesos, niveis):
    """Média ponderada dos níveis (1 a 3) convertida para 0 a 100. None se não houver dados."""
    soma = total = 0.0
    for cod, peso in (pesos or {}).items():
        try:
            peso = float(peso)
        except (TypeError, ValueError):
            continue
        nivel = niveis.get(cod)
        if peso > 0 and nivel in (1, 2, 3):
            soma += nivel * peso
            total += peso
    if not total:
        return None
    return round((soma / total - 1) / 2 * 100, 1)


def quadrante_de(x, y):
    """Os pontos sobre uma linha central contam como o lado mais alto do eixo."""
    vertical = "superior" if y >= 50 else "inferior"
    horizontal = "direito" if x >= 50 else "esquerdo"
    return f"{vertical}_{horizontal}"


def montar_mapa(R, niveis_grupo, participantes=None):
    """Posição da decisão do grupo e de cada participante no plano cartesiano.

    participantes: lista de (nome, {"C1": 1..3, ...}). Pontos na mesma posição são agrupados.
    """
    cfg = R.get("mapa") or {}
    if not cfg.get("ativo"):
        return None
    ex, ey = cfg["eixo_x"], cfg["eixo_y"]
    gx, gy = posicao_eixo(ex["pesos"], niveis_grupo), posicao_eixo(ey["pesos"], niveis_grupo)
    if gx is None or gy is None:
        return None
    q = quadrante_de(gx, gy)
    quad = cfg["quadrantes"][q]
    texto = preencher(cfg.get("texto", ""), quadrante=quad["nome"],
                      descricao=(quad["descricao"][:1].lower() + quad["descricao"][1:]) if quad["descricao"] else "",
                      x=round(gx), y=round(gy))

    pontos, por_quadrante = {}, {}
    if cfg.get("mostrar_participantes"):
        for nome, respostas in participantes or []:
            niv = {k: int(v) for k, v in respostas.items() if str(v) in ("1", "2", "3")}
            px, py = posicao_eixo(ex["pesos"], niv), posicao_eixo(ey["pesos"], niv)
            if px is None or py is None:
                continue
            pontos.setdefault((px, py), []).append(nome)
            por_quadrante.setdefault(quadrante_de(px, py), []).append(nome)
    lista = [{"x": x, "y": y, "nomes": nomes, "com_grupo": (x, y) == (gx, gy)}
             for (x, y), nomes in sorted(pontos.items(), key=lambda kv: (-kv[0][1], kv[0][0]))]

    leitura = ""
    if por_quadrante:
        if len(por_quadrante) == 1:
            leitura = "Todos os participantes ficaram no mesmo quadrante, o que indica uma visão comum sobre a iniciativa."
        else:
            partes = [f"{cfg['quadrantes'][k]['nome']} ({juntar(v)})" for k, v in
                      sorted(por_quadrante.items(), key=lambda kv: -len(kv[1]))]
            leitura = (f"As respostas individuais se distribuíram por {len(por_quadrante)} quadrantes: "
                       + "; ".join(partes) + ". Vale observar onde as visões se afastam da decisão do grupo.")

    return {"titulo": cfg.get("titulo") or "Mapa do diagnóstico",
            "eixo_x": ex["nome"], "eixo_y": ey["nome"],
            "rotulo_menor": cfg.get("rotulo_menor") or "menor", "rotulo_maior": cfg.get("rotulo_maior") or "maior",
            "quadrantes_linhas": {k: quebrar(v.get("descricao", ""), 40) for k, v in cfg["quadrantes"].items()},
            "grupo": {"x": gx, "y": gy}, "quadrante": q, "quadrante_nome": quad["nome"],
            "quadrantes": cfg["quadrantes"], "participantes": lista,
            "texto": texto, "leitura": leitura, "desenho": desenhar_mapa(cfg, gx, gy, lista)}


def quebrar(texto, largura):
    """Divide o texto em até duas linhas para caber no canto do quadrante."""
    import textwrap
    linhas = textwrap.wrap(str(texto or ""), largura)
    if len(linhas) > 2:
        linhas = [linhas[0], " ".join(linhas[1:])]
    return linhas


def desenhar_mapa(cfg, gx, gy, participantes):
    """Coordenadas do SVG: área do gráfico, pontos e rótulos posicionados sem sobreposição."""
    L, T, Wd, Hd = 96, 30, 600, 470          # área do gráfico dentro de um viewBox 0 0 740 600
    X = lambda v: L + v / 100 * Wd
    Y = lambda v: T + Hd - v / 100 * Hd
    ocupados = []

    def livre(x0, y0, x1, y1):
        return all(x1 < a or x0 > c or y1 < b or y0 > d for a, b, c, d in ocupados)

    def rotular(cx, cy, texto, largura_char, altura, raio):
        larg = len(texto) * largura_char
        tentativas = [(cx + raio + 6, cy + altura / 3, "start"), (cx - raio - 6, cy + altura / 3, "end"),
                      (cx + raio + 4, cy - raio - 4, "start"), (cx + raio + 4, cy + raio + altura, "start"),
                      (cx - raio - 4, cy - raio - 4, "end"), (cx - raio - 4, cy + raio + altura, "end")]
        for tx, ty, anc in tentativas:
            x0 = tx if anc == "start" else tx - larg
            caixa = (x0 - 2, ty - altura, x0 + larg + 2, ty + 3)
            if caixa[0] >= L + 2 and caixa[2] <= L + Wd - 2 and caixa[1] >= T + 2 and caixa[3] <= T + Hd - 2 and livre(*caixa):
                ocupados.append(caixa)
                return {"x": round(tx, 1), "y": round(ty, 1), "ancora": anc}
        tx, ty, anc = tentativas[0]
        ocupados.append((tx, ty - altura, tx + larg, ty + 3))
        return {"x": round(tx, 1), "y": round(ty, 1), "ancora": anc}

    # áreas dos textos dos quadrantes (cantos)
    for x0, y0, x1, y1 in ((L + 8, T + 8, L + 285, T + 74), (L + Wd - 285, T + 8, L + Wd - 8, T + 74),
                           (L + 8, T + Hd - 74, L + 285, T + Hd - 8), (L + Wd - 285, T + Hd - 74, L + Wd - 8, T + Hd - 8)):
        ocupados.append((x0, y0, x1, y1))
    # marcadores
    gpx, gpy = X(gx), Y(gy)
    anel = any(p["com_grupo"] for p in participantes)       # participante na mesma posição do grupo
    raio_grupo = 19 if anel else 14
    ocupados.append((gpx - raio_grupo, gpy - raio_grupo, gpx + raio_grupo, gpy + raio_grupo))
    pts = []
    for p in participantes:
        px, py = X(p["x"]), Y(p["y"])
        if not p["com_grupo"]:
            ocupados.append((px - 10, py - 10, px + 10, py + 10))
        pts.append([p, px, py])
    rot_grupo = rotular(gpx, gpy, "Decisão do grupo", 8.6, 15, raio_grupo)
    saida = []
    for p, px, py in pts:
        nome = ", ".join(p["nomes"])
        if p["com_grupo"]:
            nome += " (igual ao grupo)"
        saida.append({"cx": round(px, 1), "cy": round(py, 1), "nome": nome, "com_grupo": p["com_grupo"],
                      "rotulo": rotular(px, py, nome, 7.4, 13, raio_grupo if p["com_grupo"] else 11)})
    return {"L": L, "T": T, "W": Wd, "H": Hd, "meio_x": L + Wd / 2, "meio_y": T + Hd / 2,
            "grupo": {"cx": round(gpx, 1), "cy": round(gpy, 1), "rotulo": rot_grupo}, "participantes": saida}
