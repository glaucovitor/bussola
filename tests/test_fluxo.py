"""Teste de ponta a ponta: oficina com 5 participantes, divergências, consolidação e plano.

Executar a partir da pasta do projeto:  python -m pytest tests -q
"""
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def app_ctx(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BUSSOLA_INSTANCE", tmp)
    for mod in ("app", "rules"):
        sys.modules.pop(mod, None)
    import app as modulo
    modulo.app.config.update(TESTING=True)
    return modulo


def csrf(html):
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_fluxo_completo(app_ctx):
    import rules
    app = app_ctx.app
    cond = app.test_client()

    # Sem login: o sistema abre direto no painel
    assert cond.get("/").headers["Location"].endswith("/oficinas")
    assert cond.get("/oficinas").status_code == 200
    assert cond.get("/entrar").status_code == 302

    # Nova oficina
    r = cond.get("/oficinas"); tk = csrf(r.text)
    r = cond.post("/oficinas/nova", data={"csrf_token": tk, "titulo": "Portal de outorgas"})
    oid = int(r.headers["Location"].rsplit("/", 1)[1])
    r = cond.get(f"/oficinas/{oid}"); assert r.status_code == 200
    codigo = re.search(r'class="code-big"[^>]*>([A-Z0-9]{6})<', r.text).group(1)
    assert cond.get(f"/oficinas/{oid}/qr.svg").status_code == 200

    # Contextualização em grupo (autosave via fetch)
    r = cond.post(f"/oficinas/{oid}/contexto", headers={"X-CSRF-Token": tk}, data={
        "nome_iniciativa": "Portal de outorgas", "unidade_demandante": "SOR", "data_aplicacao": "2026-10-26",
        "problema_resolver": "Pedidos incompletos geram retrabalho.",
        "publicos_afetados": ["Empresas", "Público interno", "Outros"], "publicos_outros": "Consultorias",
        "unidades_envolvidas": "SOR\nSTI", "instituicoes_externas": "MCom"})
    assert r.json["ok"]

    # Participantes
    perfis = {
        "Ana":    dict(C1=3, C2=2, C3=2, C4=3, C5=3, C6=1, C7=3, C8=2, C9=2, C10=3, T1="yes", T2="no", T3="yes", T4="no", T5="partial", T6="yes", T7="no", T8="no"),
        "Bruno":  dict(C1=1, C2=2, C3=2, C4=3, C5=3, C6=2, C7=3, C8=2, C9=2, C10=3, T1="yes", T2="no", T3="yes", T4="no", T5="no",      T6="yes", T7="no", T8="unknown"),
        "Carla":  dict(C1=2, C2=2, C3=2, C4=3, C5=3, C6=3, C7=3, C8=3, C9=2, C10=2, T1="no",  T2="no", T3="yes", T4="no", T5="partial", T6="yes", T7="yes", T8="no"),
        "Diego":  dict(C1=2, C2=2, C3=2, C4=3, C5=2, C6=1, C7=3, C8=2, C9=2, C10=3, T1="yes", T2="no", T3="yes", T4="no", T5="partial", T6="yes", T7="no", T8="no"),
        "Elisa":  dict(C1=2, C2=2, C3=2, C4=3, C5=3, C6=2, C7=3, C8=2, C9=2, C10=3, T1="yes", T2="no", T3="yes", T4="no", T5="partial", T6="yes", T7="no", T8="no"),
    }
    for nome, resp in perfis.items():
        c = app.test_client()
        r = c.get(f"/o/{codigo}"); t = csrf(r.text)
        r = c.post(f"/o/{codigo}", data={"csrf_token": t, "nome": nome, "unidade": "SOR"})
        r = c.get(f"/o/{codigo}"); assert "C10" in r.text
        dados = {k: str(v) for k, v in resp.items()}
        # envio incompleto é recusado
        r = c.post(f"/o/{codigo}/salvar", headers={"X-CSRF-Token": t}, data={"C1": dados["C1"], "acao": "enviar"})
        assert r.status_code == 400 and "C2" in r.json["faltando"]
        dados["com_C1"] = f"Comentário de {nome}"
        r = c.post(f"/o/{codigo}/salvar", headers={"X-CSRF-Token": t}, data={**dados, "acao": "enviar"})
        assert r.json["ok"] and r.json["enviado"]

    # Sem CSRF é recusado
    assert app.test_client().post(f"/o/{codigo}/salvar", data={"C1": "1"}).status_code in (302, 400)

    st = cond.get(f"/oficinas/{oid}/status.json").json
    assert st["enviados"] == 5

    # Análise
    r = cond.get(f"/oficinas/{oid}/consolidacao"); assert r.status_code == 200
    assert "Divergência alta" in r.text

    # Finalizar sem um valor definido é recusado; justificativas são opcionais
    form = {"csrf_token": tk, "acao": "finalizar"}
    an = rules.analisar_oficina([{k: v for k, v in p.items()} for p in perfis.values()])
    r = cond.post(f"/oficinas/{oid}/consolidacao", data=form, follow_redirects=True)
    assert "defina o valor" in r.text
    for cod, a in an.items():
        form[f"valor_{cod}"] = str(a["sugestao"])
    r = cond.post(f"/oficinas/{oid}/consolidacao", data=form, follow_redirects=True)
    assert "Ponto de entrada" in r.text

    # Plano
    r = cond.get(f"/oficinas/{oid}/plano")
    assert "Alinhamento e Escopo" in r.text and "Entrada" in r.text and "Saída" in r.text and "Técnicas sugeridas" in r.text
    assert "obrigatória" not in r.text
    assert not re.search(r"C\d+ = [abc]", r.text)        # sem letras de alternativas no texto
    j = cond.get(f"/oficinas/{oid}/plano.json").json
    assert j["plano"]["ponto_entrada"] == "Exploração do problema"   # C1 = b vale c (peso 2)
    etapas = {e["fase"]: e for e in j["plano"]["percurso"]}
    assert len(etapas) == 6 and etapas["Alinhamento e Escopo"]["ativa"]
    assert etapas["Handover e integração com desenvolvimento paralelo"]["intensidade"] == "Baixa"  # sem sistema
    assert any(s["codigo"] == "T1" for s in j["plano"]["salvaguardas"])
    assert cond.get(f"/oficinas/{oid}/respostas.csv").status_code == 200

    # Oficina encerrada: participante não altera mais
    c = app.test_client()
    r = c.get(f"/o/{codigo}")
    assert "encerr" in r.text


def test_regras_divergencia():
    import rules
    assert rules.analisar_criterio([2, 2, 2])["status"] == "consenso"
    assert rules.analisar_criterio([1, 3, 2])["status"] == "alta"
    assert rules.analisar_criterio([1, 2])["status"] == "moderada"
    assert rules.analisar_criterio([1, 1, 3, 3])["sugestao"] == 3          # empate → mais precavida
    assert rules.analisar_criterio([2, 2, 2, 1])["status"] == "consenso"  # 75% e amplitude 1
    assert rules.analisar_condicao(["yes", "no"])["status"] == "alta"
    assert rules.analisar_condicao(["yes", "no"])["sugestao"] == "yes"
    assert rules.analisar_condicao(["partial", "no", "no"])["status"] == "consenso"


def _R():
    import motor
    return motor.normalizar(motor.regras_padrao())


def _plano(niveis, condicoes, sistema="SEI", R=None):
    import motor
    return motor.gerar_plano(R or _R(), {"sistemas_envolvidos": sistema}, niveis, condicoes)


def test_ponto_de_entrada():
    base = {f"C{i}": 1 for i in range(1, 11)}
    casos = [({"C4": 1}, "HO"), ({"C1": 3}, "EX"), ({"C1": 2}, "EX"),      # C1 = b conta como c (peso)
             ({"C3": 3}, "EX"), ({"C3": 2, "C4": 3}, "ID"), ({"C3": 2, "C4": 2}, "PR")]
    for mudanca, esperado in casos:
        assert _plano({**base, **mudanca}, {})["ponto_entrada_codigo"] == esperado, mudanca


def test_etapas_e_intensidade():
    niveis = {"C1": 1, "C2": 1, "C3": 2, "C4": 2, "C5": 2, "C6": 1, "C7": 3, "C8": 2, "C9": 1, "C10": 3}
    p = _plano(niveis, {"T8": "yes"})
    e = {x["codigo"]: x for x in p["percurso"]}
    assert p["ponto_entrada_codigo"] == "PR"
    assert not e["EX"]["ativa"] and not e["ID"]["ativa"]           # dispensadas
    assert all(e[x]["ativa"] for x in ("AL", "HO", "AV"))          # sempre presentes
    assert e["AL"]["intensidade"] == "Alta"                        # C5 = b com peso dobrado
    assert e["HO"]["intensidade"] == "Alta"                        # C10 = c, com sistema
    assert e["AV"]["intensidade"] == "Média"                       # C8 = b
    prep = [t["nome"] for t in e["PR"]["tecnicas"] if t["preparatoria"]]
    assert "Jornada completa atual (as-is)" in prep                # veio da Exploração
    assert p["paralelo"] and e["HO"]["em_paralelo"]
    rotulos = [r["rotulo"] for r in e["HO"]["regras_aplicadas"]]
    assert {"Situação", "Intensidade", "Técnicas"} <= set(rotulos)


def test_alinhamento_na_oficina():
    simples = {"C1": 1, "C2": 1, "C3": 1, "C4": 2, "C5": 1, "C6": 1, "C7": 1, "C8": 1, "C9": 1, "C10": 1}
    p = _plano(simples, {"T8": "no"})
    al = p["percurso"][0]
    assert p["alinhamento_na_oficina"] and al["na_oficina"] and al["intensidade"] == "Baixa"
    assert [t["nome"] for t in al["tecnicas"]] == ["Termo de abertura do projeto"]
    assert "oficina" in al["texto_intensidade"]["porque"]
    assert any(r["rotulo"] == "Exceção" for r in al["regras_aplicadas"])
    assert not _plano(simples, {"T8": "unknown"})["percurso"][0]["na_oficina"]
    assert not _plano({**simples, "C5": 2}, {"T8": "no"})["percurso"][0]["na_oficina"]   # peso dobrado


def test_regras_editaveis_mudam_o_plano():
    """Alterar o conjunto de regras muda o plano: textos, técnicas, peso e ponto de entrada."""
    import motor
    niveis = {f"C{i}": 2 for i in range(1, 11)}
    R = _R()
    R["etapas"][1]["orientacao"]["Alta"] = "TEXTO PERSONALIZADO"
    R["tecnicas"].append({"nome": "Técnica nova", "etapa": "EX", "criterio": "C2", "niveis": [2, 3]})
    R["criterios"]["C1"]["frases"][1] = "frase editada"
    assert not motor.validar(R)
    p = _plano(niveis, {}, R=R)
    ex = p["percurso"][1]
    assert ex["texto_intensidade"]["orientacao"] == "TEXTO PERSONALIZADO"
    assert "Técnica nova" in [t["nome"] for t in ex["tecnicas"]]
    assert "frase editada" in p["justificativa_entrada"]
    # sem peso dobrado em C1, C1 = b deixa de levar à Exploração
    R["criterios"]["C1"]["peso_dobrado"] = False
    assert _plano(niveis, {}, R=R)["ponto_entrada_codigo"] == "PR"
    # nova regra de entrada no topo passa a valer primeiro
    R["ponto_entrada"]["regras"].insert(0, {"id": "x", "nome": "Teste", "etapa": "ID", "modo": "todas",
                                            "condicoes": [{"tipo": "criterio", "criterio": "C9", "niveis": [2]}],
                                            "texto": "Regra de teste.", "texto_peso": ""})
    p = _plano(niveis, {}, R=R)
    assert p["ponto_entrada_codigo"] == "ID" and p["rastro_entrada"]["regra"] == "Teste"


def test_validacao_de_regras():
    import motor
    R = _R()
    R["tecnicas"].append({"nome": "", "etapa": "XX", "criterio": "C99", "niveis": []})
    R["ponto_entrada"]["regras"][0]["condicoes"] = []
    erros = motor.validar(R)
    assert any("etapa inexistente" in e for e in erros)
    assert any("pelo menos uma condição" in e for e in erros)


def test_editor_de_regras_versoes(app_ctx):
    import motor
    c = app_ctx.app.test_client()
    tk = csrf(c.get("/regras").text)
    assert "Versão 1" in c.get("/regras").text
    assert c.get("/regras/editar").status_code == 200
    R = _R()
    R["etapas"][0]["orientacao"]["Baixa"] = "Orientação editada"
    # simular não salva
    r = c.post("/regras/simular", json={"regras": R, "perfil": {"C3": 1, "C5": 1, "C6": 1, "T8": "yes"}},
               headers={"X-CSRF-Token": tk})
    assert r.json["ok"] and r.json["plano"]["percurso"][0]["texto_intensidade"]["orientacao"] == "Orientação editada"
    # regras inválidas são recusadas
    ruim = _R(); ruim["focos"].append({"etapa": "ZZ", "criterio": "C1", "niveis": [2], "texto": "x"})
    r = c.post("/regras/salvar", json={"regras": ruim}, headers={"X-CSRF-Token": tk})
    assert r.status_code == 400 and r.json["erros"]
    # salvar cria a versão 2
    r = c.post("/regras/salvar", json={"regras": R, "nota": "teste"}, headers={"X-CSRF-Token": tk})
    assert r.json["versao"] == 2
    assert "Orientação editada" in c.get("/regras").text
    # exportar e restaurar
    assert c.get("/regras/exportar").json["etapas"][0]["orientacao"]["Baixa"] == "Orientação editada"
    c.post("/regras/versoes/1/restaurar", data={"csrf_token": tk})
    assert "Orientação editada" not in c.get("/regras").text and "Versão 3" in c.get("/regras").text


def test_login_opcional(monkeypatch):
    """Com BUSSOLA_EXIGIR_LOGIN=1, o painel volta a pedir usuário e senha."""
    monkeypatch.setenv("BUSSOLA_INSTANCE", tempfile.mkdtemp())
    monkeypatch.setenv("BUSSOLA_EXIGIR_LOGIN", "1")
    for mod in ("app", "rules"):
        sys.modules.pop(mod, None)
    import app as modulo
    c = modulo.app.test_client()
    assert c.get("/oficinas").status_code == 302
    tk = csrf(c.get("/entrar").text)
    r = c.post("/entrar", data={"csrf_token": tk, "usuario": "itrac", "senha": "errada"})
    assert "incorretos" in r.text
    c.post("/entrar", data={"csrf_token": tk, "usuario": "itrac", "senha": "123456"})
    assert c.get("/oficinas").status_code == 200


def test_participante_nao_ve_menu_do_condutor(app_ctx):
    c = app_ctx.app.test_client()
    r = c.get("/o")
    assert ">Oficinas</a>" not in r.text


def test_remover_iniciativa(app_ctx):
    c = app_ctx.app.test_client()
    tk = csrf(c.get("/oficinas").text)
    r = c.post("/oficinas/nova", data={"csrf_token": tk, "titulo": "Iniciativa de teste"})
    oid = int(r.headers["Location"].rsplit("/", 1)[1])
    codigo = re.search(r'class="code-big"[^>]*>([A-Z0-9]{6})<', c.get(f"/oficinas/{oid}").text).group(1)
    # um participante com respostas
    p = app_ctx.app.test_client(); pt = csrf(p.get(f"/o/{codigo}").text)
    p.post(f"/o/{codigo}", data={"csrf_token": pt, "nome": "Ana"})
    assert "Remover" in c.get("/oficinas").text
    # código errado não remove
    c.post(f"/oficinas/{oid}/excluir", data={"csrf_token": tk, "confirmacao": "XXXXXX"})
    assert c.get(f"/oficinas/{oid}").status_code == 200
    # remoção apaga a oficina e os participantes
    r = c.post(f"/oficinas/{oid}/excluir", data={"csrf_token": tk, "confirmacao": codigo}, follow_redirects=True)
    assert "removida" in r.text and "Iniciativa de teste</b>" not in r.text
    assert c.get(f"/oficinas/{oid}").status_code == 404
    import sqlite3
    con = sqlite3.connect(app_ctx.app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM participantes").fetchone()[0] == 0


def test_plano_finalizado_preserva_versao_das_regras(app_ctx):
    c = app_ctx.app.test_client()
    tk = csrf(c.get("/oficinas").text)
    oid = int(c.post("/oficinas/nova", data={"csrf_token": tk, "titulo": "Versões"}).headers["Location"].rsplit("/", 1)[1])
    codigo = re.search(r'class="code-big"[^>]*>([A-Z0-9]{6})<', c.get(f"/oficinas/{oid}").text).group(1)
    resp = {**{f"C{i}": "2" for i in range(1, 11)}, **{f"T{i}": "no" for i in range(1, 9)}}
    p = app_ctx.app.test_client(); pt = csrf(p.get(f"/o/{codigo}").text)
    p.post(f"/o/{codigo}", data={"csrf_token": pt, "nome": "Ana"})
    p.post(f"/o/{codigo}/salvar", headers={"X-CSRF-Token": pt}, data={**resp, "acao": "enviar"})
    c.post(f"/oficinas/{oid}/consolidacao", data={"csrf_token": tk, "acao": "finalizar",
                                                  **{f"valor_{k}": v for k, v in resp.items()}})
    antes = c.get(f"/oficinas/{oid}/plano").text
    R = _R(); R["etapas"][1]["orientacao"]["Alta"] = "NOVA ORIENTAÇÃO"
    c.post("/regras/salvar", json={"regras": R}, headers={"X-CSRF-Token": tk})
    depois = c.get(f"/oficinas/{oid}/plano").text
    assert "NOVA ORIENTAÇÃO" not in depois and "versão mais recente" in depois
    c.post(f"/oficinas/{oid}/plano/atualizar-regras", data={"csrf_token": tk})
    assert "NOVA ORIENTAÇÃO" in c.get(f"/oficinas/{oid}/plano").text
    assert "regras da versão 1" in antes


def test_mapa_do_diagnostico():
    import motor
    R = _R()
    grupo = dict(C1=2, C2=2, C3=2, C4=3, C5=3, C6=1, C7=3, C8=2, C9=2, C10=3)
    parts = [("Ana", {**grupo, "C1": 3}), ("Bruno", {**grupo, "C1": 1, "C6": 2}), ("Eva", grupo), ("Fábio", grupo)]
    m = motor.montar_mapa(R, grupo, parts)
    assert (m["grupo"]["x"], m["grupo"]["y"]) == (60.0, 71.4) and m["quadrante_nome"] == "Transformação"
    assert "difícil" not in str(m) and m["rotulo_menor"] == "menor"
    iguais = [p for p in m["participantes"] if p["com_grupo"]]
    assert iguais and iguais[0]["nomes"] == ["Eva", "Fábio"]                 # pontos coincidentes agrupados
    assert "2 quadrantes" in m["leitura"]
    simples = {f"C{i}": 1 for i in range(1, 11)}
    assert motor.montar_mapa(R, simples)["quadrante_nome"] == "Execução direta"
    # editar pesos e nomes muda o mapa; desativar remove
    R["mapa"]["eixo_x"]["pesos"] = {c: 0 for c in R["mapa"]["eixo_x"]["pesos"]} | {"C4": 1}
    R["mapa"]["quadrantes"]["superior_direito"]["nome"] = "Grande transformação"
    m = motor.montar_mapa(R, grupo)
    assert m["grupo"]["x"] == 100.0 and m["quadrante_nome"] == "Grande transformação"
    R["mapa"]["eixo_y"]["pesos"] = {c: 0 for c in R["mapa"]["eixo_y"]["pesos"]}
    assert any("eixo vertical" in e for e in motor.validar(R))
    R["mapa"]["ativo"] = False
    assert motor.montar_mapa(R, grupo) is None and not any("eixo" in e for e in motor.validar(R))


def test_regras_antigas_sem_mapa_recebem_o_padrao():
    import motor
    R = motor.regras_padrao(); del R["mapa"]
    R = motor.normalizar(R)
    assert R["mapa"]["ativo"] and not motor.validar(R)


def test_migracao_textos_do_mapa(monkeypatch):
    """Uma versão ativa com os textos antigos do mapa recebe uma nova versão com os textos suavizados."""
    import json, sqlite3
    pasta = tempfile.mkdtemp()
    monkeypatch.setenv("BUSSOLA_INSTANCE", pasta)
    for mod in ("app", "rules", "motor"):
        sys.modules.pop(mod, None)
    import app as modulo
    con = sqlite3.connect(modulo.app.config["DATABASE"])
    R = json.loads(con.execute("SELECT conteudo FROM regras_versoes").fetchone()[0])
    R["mapa"]["eixo_y"]["nome"] = "Complexidade de implantação"
    R["mapa"]["quadrantes"]["superior_direito"] = {"nome": "Transformação", "descricao": "Muito a descobrir e difícil de implantar"}
    con.execute("INSERT INTO regras_versoes (conteudo, nota, criado_em) VALUES (?,?,?)", (json.dumps(R), "antiga", "2026-10-30"))
    con.commit(); con.close()
    modulo.init_db()
    con = sqlite3.connect(modulo.app.config["DATABASE"])
    ultima = con.execute("SELECT conteudo, nota FROM regras_versoes ORDER BY id DESC LIMIT 1").fetchone()
    assert ultima[1] == "Textos do mapa do diagnóstico suavizados" and "difícil" not in ultima[0]
    modulo.init_db()   # rodar de novo não cria outra versão
    assert con.execute("SELECT COUNT(*) FROM regras_versoes").fetchone()[0] == 3
