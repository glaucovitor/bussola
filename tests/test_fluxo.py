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
    assert rules.ponto_entrada({"C1": 1, "C2": 1, "C3": 1, "C4": 1})[0] == rules.HO
    assert rules.ponto_entrada({"C1": 3, "C2": 1, "C3": 1, "C4": 1})[0] == rules.EX
    assert rules.ponto_entrada({"C1": 2, "C2": 1, "C3": 1, "C4": 1})[0] == rules.EX   # peso 2
    assert rules.ponto_entrada({"C1": 1, "C2": 1, "C3": 3, "C4": 1})[0] == rules.EX
    assert rules.ponto_entrada({"C1": 1, "C2": 1, "C3": 2, "C4": 3})[0] == rules.ID
    assert rules.ponto_entrada({"C1": 1, "C2": 1, "C3": 2, "C4": 2})[0] == rules.PR


def test_etapas_e_intensidade():
    import rules
    niveis = {"C1": 1, "C2": 1, "C3": 2, "C4": 2, "C5": 2, "C6": 1, "C7": 3, "C8": 2, "C9": 1, "C10": 3}
    p = rules.gerar_plano({"sistemas_envolvidos": "SEI"}, niveis, {"T8": "yes"})
    e = {x["fase"]: x for x in p["percurso"]}
    assert p["ponto_entrada"] == rules.PR
    assert not e[rules.EX]["ativa"] and not e[rules.ID]["ativa"]           # dispensadas
    assert all(e[x]["ativa"] for x in rules.ETAPAS_SEMPRE)                  # sempre presentes
    assert e[rules.AL]["intensidade"] == "Alta"                         # C5 = b com peso 2
    assert e[rules.HO]["intensidade"] == "Alta"                         # C10 = c, com sistema
    assert e[rules.AV]["intensidade"] == "Média"                             # C8 = b
    prep = [t["nome"] for t in e[rules.PR]["tecnicas"] if t["preparatoria"]]
    assert "Jornada completa atual (as-is)" in prep                         # veio da Exploração
    assert p["paralelo"]


def test_alinhamento_na_oficina():
    import rules
    simples = {"C1": 1, "C2": 1, "C3": 1, "C4": 2, "C5": 1, "C6": 1, "C7": 1, "C8": 1, "C9": 1, "C10": 1}
    p = rules.gerar_plano({"sistemas_envolvidos": "SEI"}, simples, {"T8": "no"})
    al = p["percurso"][0]
    assert p["alinhamento_na_oficina"] and al["na_oficina"] and al["intensidade"] == "Baixa"
    assert [t["nome"] for t in al["tecnicas"]] == ["Termo de abertura do projeto"]
    assert "oficina" in al["texto_intensidade"]["porque"]
    # Sem patrocinador definido (T8 diferente de Não), o alinhamento não é considerado feito
    p = rules.gerar_plano({"sistemas_envolvidos": "SEI"}, simples, {"T8": "unknown"})
    assert not p["percurso"][0]["na_oficina"]
    # C5 em nível médio (peso dobrado) também impede
    p = rules.gerar_plano({"sistemas_envolvidos": "SEI"}, {**simples, "C5": 2}, {"T8": "no"})
    assert not p["percurso"][0]["na_oficina"]


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
