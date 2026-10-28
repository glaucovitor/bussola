"""Bússola — oficinas de diagnóstico de Design de Serviços.

Fluxo:
  1. O condutor cria a oficina e projeta o link/QR code.
  2. Identificação e contextualização são preenchidas em grupo, pelo condutor.
  3. Cada participante responde C1–C10 e T1–T8 individualmente.
  4. O condutor consolida as divergências e o sistema gera o plano metodológico.
"""
import csv
import io
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)

import motor
import rules

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.environ.get("BUSSOLA_INSTANCE", os.path.join(BASE_DIR, "instance"))
os.makedirs(INSTANCE_DIR, exist_ok=True)


def _secret_key():
    if os.environ.get("BUSSOLA_SECRET_KEY"):
        return os.environ["BUSSOLA_SECRET_KEY"]
    caminho = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(caminho):
        with open(caminho, "w") as f:
            f.write(secrets.token_hex(32))
    with open(caminho) as f:
        return f.read().strip()


app = Flask(__name__, instance_path=INSTANCE_DIR)
app.config.update(
    SECRET_KEY=_secret_key(),
    DATABASE=os.environ.get("BUSSOLA_DB", os.path.join(INSTANCE_DIR, "bussola.sqlite3")),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("BUSSOLA_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

CODIGOS_C = [c["codigo"] for c in rules.CRITERIOS]
CODIGOS_T = [t["codigo"] for t in rules.CONDICOES]
TODOS_CODIGOS = CODIGOS_C + CODIGOS_T
LIMITE_COMENTARIO = 1000
LIMITE_CAMPO = 4000

SCHEMA = """
CREATE TABLE IF NOT EXISTS oficinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    titulo TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberta',
    contexto_json TEXT NOT NULL DEFAULT '{}',
    contexto_atualizado_em TEXT,
    consolidacao_json TEXT NOT NULL DEFAULT '{}',
    consolidacao_atualizada_em TEXT,
    finalizada_em TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS participantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oficina_id INTEGER NOT NULL REFERENCES oficinas(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    papel TEXT,
    unidade TEXT,
    respostas_json TEXT NOT NULL DEFAULT '{}',
    comentarios_json TEXT NOT NULL DEFAULT '{}',
    enviado_em TEXT,
    atualizado_em TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_participantes_oficina ON participantes(oficina_id);
CREATE TABLE IF NOT EXISTS regras_versoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conteudo TEXT NOT NULL,
    nota TEXT,
    criado_em TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


@app.teardown_appcontext
def fechar_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    # Migração: versão das regras usada em cada plano finalizado
    colunas = [r[1] for r in con.execute("PRAGMA table_info(oficinas)")]
    if "regras_versao_id" not in colunas:
        con.execute("ALTER TABLE oficinas ADD COLUMN regras_versao_id INTEGER")
    # Primeira versão das regras = regras padrão
    if not con.execute("SELECT 1 FROM regras_versoes LIMIT 1").fetchone():
        con.execute("INSERT INTO regras_versoes (conteudo, nota, criado_em) VALUES (?,?,?)",
                    (json.dumps(motor.regras_padrao(), ensure_ascii=False), "Regras padrão do sistema",
                     datetime.now().isoformat(timespec="seconds")))
    # Planos finalizados antes do versionamento ficam presos à primeira versão
    primeira = con.execute("SELECT MIN(id) FROM regras_versoes").fetchone()[0]
    con.execute("UPDATE oficinas SET regras_versao_id = ? WHERE finalizada_em IS NOT NULL AND regras_versao_id IS NULL",
                (primeira,))
    con.commit()
    con.close()


init_db()


# ---------------------------------------------------------------------------
# Regras do plano (versionadas)
# ---------------------------------------------------------------------------
def versao_regras(versao_id=None):
    """Retorna (linha da versão, regras normalizadas). Sem id, retorna a versão ativa (a mais recente)."""
    db = get_db()
    if versao_id:
        row = db.execute("SELECT * FROM regras_versoes WHERE id = ?", (versao_id,)).fetchone()
        if row:
            return row, motor.normalizar(json.loads(row["conteudo"]))
    row = db.execute("SELECT * FROM regras_versoes ORDER BY id DESC LIMIT 1").fetchone()
    return row, motor.normalizar(json.loads(row["conteudo"]))


def salvar_versao(R, nota):
    db = get_db()
    cur = db.execute("INSERT INTO regras_versoes (conteudo, nota, criado_em) VALUES (?,?,?)",
                     (json.dumps(R, ensure_ascii=False), (nota or "").strip()[:300], agora()))
    db.commit()
    return cur.lastrowid


def agora():
    return datetime.now().isoformat(timespec="seconds")


def carregar(texto):
    try:
        return json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Segurança: CSRF, cabeçalhos, autenticação
# ---------------------------------------------------------------------------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def verificar_csrf():
    session.permanent = True
    if request.method == "POST":
        enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
            if request.is_json or request.headers.get("X-CSRF-Token") is not None:
                return jsonify(ok=False, erro="Sessão expirada. Recarregue a página."), 400
            flash("Sua sessão expirou. Tente novamente.", "erro")
            return redirect(request.url)


@app.after_request
def cabecalhos(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# Login opcional. Por padrão o sistema abre direto no painel do condutor.
# Para exigir login, defina BUSSOLA_EXIGIR_LOGIN=1 (usuário e senha abaixo).
EXIGIR_LOGIN = os.environ.get("BUSSOLA_EXIGIR_LOGIN") == "1"
ADMIN_USUARIO = os.environ.get("BUSSOLA_ADMIN_USUARIO", "itrac")
ADMIN_SENHA = os.environ.get("BUSSOLA_ADMIN_SENHA", "123456")


def eh_condutor():
    return not EXIGIR_LOGIN or session.get("admin") is True


app.jinja_env.globals["eh_condutor"] = eh_condutor
app.jinja_env.globals["exigir_login"] = EXIGIR_LOGIN


def somente_condutor(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not eh_condutor():
            if request.headers.get("X-CSRF-Token") is not None:
                return jsonify(ok=False, erro="Sessão de administrador expirada. Entre novamente."), 403
            return redirect(url_for("login", proximo=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.route("/entrar", methods=["GET", "POST"])
def login():
    if not EXIGIR_LOGIN:
        return redirect(url_for("painel"))
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        if (secrets.compare_digest(usuario, ADMIN_USUARIO)
                and secrets.compare_digest(senha, ADMIN_SENHA)):
            session["admin"] = True
            proximo = request.args.get("proximo", "")
            if not proximo.startswith("/") or proximo.startswith("//"):
                proximo = url_for("painel")
            return redirect(proximo)
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("login.html")


@app.route("/sair", methods=["POST"])
def logout():
    session.pop("admin", None)
    return redirect(url_for("login") if EXIGIR_LOGIN else url_for("entrar_por_codigo"))


def oficina_do_condutor(oficina_id):
    of = get_db().execute("SELECT * FROM oficinas WHERE id = ?", (oficina_id,)).fetchone()
    if not of:
        abort(404)
    return of


def gerar_codigo():
    alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    db = get_db()
    while True:
        codigo = "".join(secrets.choice(alfabeto) for _ in range(6))
        if not db.execute("SELECT 1 FROM oficinas WHERE codigo = ?", (codigo,)).fetchone():
            return codigo


def ip_da_rede():
    """IP da máquina na rede local, para montar o link do QR code."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def url_publica(endpoint, **kwargs):
    caminho = url_for(endpoint, **kwargs)
    base = os.environ.get("BUSSOLA_URL_PUBLICA")
    if base:
        return base.rstrip("/") + caminho
    # Se o condutor abriu por localhost, troca pelo IP da rede para o QR funcionar nos celulares.
    host = request.host
    nome, _, porta = host.partition(":")
    if nome in ("localhost", "127.0.0.1", "[::1]"):
        ip = ip_da_rede()
        if ip:
            host = ip + (":" + porta if porta else "")
    return f"{request.scheme}://{host}{caminho}"


# ---------------------------------------------------------------------------
# Área do condutor
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    return redirect(url_for("painel") if eh_condutor() else url_for("login"))


@app.route("/oficinas")
@somente_condutor
def painel():
    oficinas = get_db().execute("""
        SELECT o.*, COUNT(p.id) AS total,
               SUM(CASE WHEN p.enviado_em IS NOT NULL THEN 1 ELSE 0 END) AS enviados
        FROM oficinas o LEFT JOIN participantes p ON p.oficina_id = o.id
        GROUP BY o.id ORDER BY o.criado_em DESC
    """).fetchall()
    return render_template("painel.html", oficinas=oficinas)


@app.route("/oficinas/nova", methods=["POST"])
@somente_condutor
def nova_oficina():
    titulo = request.form.get("titulo", "").strip()[:180]
    if not titulo:
        flash("Dê um nome à oficina.", "erro")
        return redirect(url_for("painel"))
    db = get_db()
    contexto = {"nome_iniciativa": titulo, "data_aplicacao": datetime.now().date().isoformat()}
    cur = db.execute("""INSERT INTO oficinas (codigo, titulo, contexto_json, criado_em)
                        VALUES (?,?,?,?)""",
                     (gerar_codigo(), titulo, json.dumps(contexto, ensure_ascii=False), agora()))
    db.commit()
    return redirect(url_for("oficina", oficina_id=cur.lastrowid))


def participantes_da(oficina_id):
    return get_db().execute(
        "SELECT * FROM participantes WHERE oficina_id = ? ORDER BY criado_em", (oficina_id,)).fetchall()


def progresso(p):
    resp = carregar(p["respostas_json"])
    return sum(1 for k in TODOS_CODIGOS if resp.get(k))


@app.route("/oficinas/<int:oficina_id>")
@somente_condutor
def oficina(oficina_id):
    of = oficina_do_condutor(oficina_id)
    link = url_publica("participar", codigo=of["codigo"])
    return render_template("oficina.html", of=of, link=link, contexto=carregar(of["contexto_json"]),
                           total_itens=len(TODOS_CODIGOS))


@app.route("/oficinas/<int:oficina_id>/qr.svg")
@somente_condutor
def qr(oficina_id):
    of = oficina_do_condutor(oficina_id)
    try:
        import segno
    except ImportError:
        abort(404)
    buf = io.BytesIO()
    segno.make(url_publica("participar", codigo=of["codigo"]), error="m").save(
        buf, kind="svg", scale=8, border=2, dark="#000", light="#fff")
    return Response(buf.getvalue(), mimetype="image/svg+xml")


@app.route("/oficinas/<int:oficina_id>/status.json")
@somente_condutor
def status_json(oficina_id):
    of = oficina_do_condutor(oficina_id)
    lista = []
    for p in participantes_da(oficina_id):
        lista.append({"id": p["id"], "nome": p["nome"], "papel": p["papel"] or "",
                      "unidade": p["unidade"] or "", "progresso": progresso(p),
                      "enviado": bool(p["enviado_em"]), "atualizado_em": p["atualizado_em"]})
    pendente = False
    if of["consolidacao_atualizada_em"]:
        pendente = any(p["atualizado_em"] and p["enviado_em"] and p["atualizado_em"] > of["consolidacao_atualizada_em"]
                       for p in participantes_da(oficina_id))
    return jsonify(status=of["status"], participantes=lista, total_itens=len(TODOS_CODIGOS),
                   enviados=sum(1 for p in lista if p["enviado"]),
                   respostas_apos_consolidacao=pendente)


@app.route("/oficinas/<int:oficina_id>/estado", methods=["POST"])
@somente_condutor
def mudar_estado(oficina_id):
    oficina_do_condutor(oficina_id)
    novo = request.form.get("status")
    if novo in ("aberta", "encerrada"):
        db = get_db()
        db.execute("UPDATE oficinas SET status = ? WHERE id = ?", (novo, oficina_id))
        db.commit()
        flash("Respostas reabertas para os participantes." if novo == "aberta"
              else "Respostas encerradas. Os participantes não podem mais alterar.", "ok")
    return redirect(request.form.get("voltar") or url_for("oficina", oficina_id=oficina_id))


@app.route("/oficinas/<int:oficina_id>/participantes/<int:pid>/excluir", methods=["POST"])
@somente_condutor
def excluir_participante(oficina_id, pid):
    oficina_do_condutor(oficina_id)
    db = get_db()
    db.execute("DELETE FROM participantes WHERE id = ? AND oficina_id = ?", (pid, oficina_id))
    db.commit()
    if request.headers.get("X-CSRF-Token"):
        return jsonify(ok=True)
    flash("Participante removido.", "ok")
    return redirect(url_for("oficina", oficina_id=oficina_id))


@app.route("/oficinas/<int:oficina_id>/excluir", methods=["POST"])
@somente_condutor
def excluir_oficina(oficina_id):
    of = oficina_do_condutor(oficina_id)
    # O código vai num campo oculto: protege contra envio acidental do formulário errado.
    if request.form.get("confirmacao", "").strip().upper() != of["codigo"]:
        flash("Não foi possível confirmar a remoção. Tente novamente.", "erro")
        return redirect(url_for("painel"))
    db = get_db()
    db.execute("DELETE FROM oficinas WHERE id = ?", (oficina_id,))
    db.commit()
    flash(f"Iniciativa “{of['titulo']}” removida.", "ok")
    return redirect(url_for("painel"))


# --- Identificação e contextualização (em grupo) ---------------------------
def ler_contexto_do_form(form):
    ctx = {}
    for chave, *_ in rules.CAMPOS_IDENTIFICACAO:
        ctx[chave] = form.get(chave, "").strip()[:LIMITE_CAMPO]
    for chave, *_ in rules.CAMPOS_CONTEXTO:
        ctx[chave] = form.get(chave, "").strip()[:LIMITE_CAMPO]
    for chave, _ in rules.CAMPOS_ENVOLVIDOS:
        ctx[chave] = form.get(chave, "").strip()[:LIMITE_CAMPO]
    ctx["publicos_afetados"] = [p for p in form.getlist("publicos_afetados") if p in rules.PUBLICOS]
    ctx["publicos_outros"] = form.get("publicos_outros", "").strip()[:LIMITE_CAMPO]
    return ctx


@app.route("/oficinas/<int:oficina_id>/contexto", methods=["GET", "POST"])
@somente_condutor
def contexto(oficina_id):
    of = oficina_do_condutor(oficina_id)
    if request.method == "POST":
        ctx = ler_contexto_do_form(request.form)
        db = get_db()
        titulo = ctx.get("nome_iniciativa") or of["titulo"]
        db.execute("UPDATE oficinas SET contexto_json = ?, contexto_atualizado_em = ?, titulo = ? WHERE id = ?",
                   (json.dumps(ctx, ensure_ascii=False), agora(), titulo[:180], oficina_id))
        db.commit()
        if request.headers.get("X-CSRF-Token"):
            return jsonify(ok=True, salvo_em=agora())
        flash("Identificação e contextualização salvas.", "ok")
        return redirect(url_for("oficina", oficina_id=oficina_id))
    return render_template("contexto.html", of=of, ctx=carregar(of["contexto_json"]), rules=rules)


# --- Consolidação ------------------------------------------------------------
def respostas_enviadas(oficina_id):
    return [p for p in participantes_da(oficina_id) if p["enviado_em"]]


@app.route("/oficinas/<int:oficina_id>/consolidacao", methods=["GET", "POST"])
@somente_condutor
def consolidacao(oficina_id):
    of = oficina_do_condutor(oficina_id)
    enviados = respostas_enviadas(oficina_id)
    respostas = [carregar(p["respostas_json"]) for p in enviados]
    _, R = versao_regras()
    analise = rules.analisar_oficina(respostas, float(R["consenso"]["limiar"]))
    decisoes = carregar(of["consolidacao_json"])

    if request.method == "POST":
        acao = request.form.get("acao", "salvar")
        novas, faltando = {}, []
        for cod in TODOS_CODIGOS:
            valor = request.form.get(f"valor_{cod}", "")
            just = request.form.get(f"just_{cod}", "").strip()[:LIMITE_CAMPO]
            if cod in CODIGOS_C:
                valor = int(valor) if valor in ("1", "2", "3") else None
            else:
                valor = valor if valor in rules.RESPOSTAS_T else None
            a = analise[cod]
            novas[cod] = {"valor": valor, "justificativa": just, "sugestao": a["sugestao"],
                          "status": a["status"], "concordancia": a["concordancia"], "n": a["n"]}
            if valor is None:
                faltando.append(cod)
        db = get_db()
        db.execute("UPDATE oficinas SET consolidacao_json = ?, consolidacao_atualizada_em = ? WHERE id = ?",
                   (json.dumps(novas, ensure_ascii=False), agora(), oficina_id))
        if acao == "finalizar":
            if faltando:
                db.execute("UPDATE oficinas SET finalizada_em = NULL WHERE id = ?", (oficina_id,))
                db.commit()
                flash("Para finalizar, defina o valor de " + ", ".join(faltando) + ".", "erro")
                return redirect(url_for("consolidacao", oficina_id=oficina_id))
            versao_atual, _ = versao_regras()
            db.execute("UPDATE oficinas SET finalizada_em = ?, status = 'encerrada', regras_versao_id = ? WHERE id = ?",
                       (agora(), versao_atual["id"], oficina_id))
            db.commit()
            flash("Consolidação finalizada. O plano metodológico está pronto.", "ok")
            return redirect(url_for("plano", oficina_id=oficina_id))
        db.execute("UPDATE oficinas SET finalizada_em = NULL WHERE id = ?", (oficina_id,))
        db.commit()
        flash("Decisões salvas.", "ok")
        return redirect(url_for("consolidacao", oficina_id=oficina_id))

    # Respostas e comentários individuais para exibição
    individuais = []
    for p in enviados:
        individuais.append({"nome": p["nome"], "papel": p["papel"], "unidade": p["unidade"],
                            "respostas": carregar(p["respostas_json"]),
                            "comentarios": carregar(p["comentarios_json"])})
    contagem = {s: sum(1 for c in TODOS_CODIGOS if analise[c]["status"] == s)
                for s in ("consenso", "moderada", "alta")}
    return render_template("consolidacao.html", of=of, rules=rules, R=R, analise=analise,
                           decisoes=decisoes, individuais=individuais, contagem=contagem,
                           total_participantes=len(participantes_da(oficina_id)))


# --- Plano metodológico ------------------------------------------------------
def montar_plano(of):
    """Plano finalizado usa a versão das regras gravada na finalização; os demais, a versão ativa."""
    versao, R = versao_regras(of["regras_versao_id"] if of["finalizada_em"] else None)
    decisoes = carregar(of["consolidacao_json"])
    enviados = respostas_enviadas(of["id"])
    analise = rules.analisar_oficina([carregar(p["respostas_json"]) for p in enviados],
                                     float(R["consenso"]["limiar"]))
    niveis, condicoes, registro, faltando = {}, {}, {}, []
    for cod in TODOS_CODIGOS:
        d = decisoes.get(cod, {})
        valor = d.get("valor") if d.get("valor") is not None else analise[cod]["sugestao"]
        if valor is None:
            faltando.append(cod)
            continue
        (niveis if cod in CODIGOS_C else condicoes)[cod] = valor
        registro[cod] = {"status": d.get("status", analise[cod]["status"]),
                         "concordancia": d.get("concordancia", analise[cod]["concordancia"]),
                         "sugestao": d.get("sugestao", analise[cod]["sugestao"]),
                         "justificativa": d.get("justificativa", ""),
                         "valor": valor}
    if faltando:
        return None, faltando, registro, enviados, versao, R
    ctx = carregar(of["contexto_json"])
    return motor.gerar_plano(R, ctx, niveis, condicoes, registro), [], registro, enviados, versao, R


@app.route("/oficinas/<int:oficina_id>/plano")
@somente_condutor
def plano(oficina_id):
    of = oficina_do_condutor(oficina_id)
    p, faltando, registro, enviados, versao, R = montar_plano(of)
    ativa, _ = versao_regras()
    return render_template("plano.html", of=of, plano=p, faltando=faltando, registro=registro,
                           ctx=carregar(of["contexto_json"]), rules=rules, R=R, enviados=enviados,
                           gerado_em=agora(), versao=versao, versao_ativa=ativa)


@app.route("/oficinas/<int:oficina_id>/plano/atualizar-regras", methods=["POST"])
@somente_condutor
def atualizar_regras_do_plano(oficina_id):
    oficina_do_condutor(oficina_id)
    ativa, _ = versao_regras()
    db = get_db()
    db.execute("UPDATE oficinas SET regras_versao_id = ? WHERE id = ?", (ativa["id"], oficina_id))
    db.commit()
    flash(f"Plano atualizado para as regras da versão {ativa['id']}.", "ok")
    return redirect(url_for("plano", oficina_id=oficina_id))


@app.route("/oficinas/<int:oficina_id>/plano.json")
@somente_condutor
def plano_json(oficina_id):
    of = oficina_do_condutor(oficina_id)
    p, faltando, registro, enviados, versao, _ = montar_plano(of)
    dados = {
        "oficina": {"codigo": of["codigo"], "titulo": of["titulo"], "finalizada_em": of["finalizada_em"]},
        "regras_versao": versao["id"],
        "contexto": carregar(of["contexto_json"]),
        "consolidacao": registro,
        "participantes": [{"nome": e["nome"], "papel": e["papel"], "unidade": e["unidade"],
                           "respostas": carregar(e["respostas_json"]),
                           "comentarios": carregar(e["comentarios_json"]),
                           "enviado_em": e["enviado_em"]} for e in enviados],
        "plano": p,
        "pendencias": faltando,
        "gerado_em": agora(),
    }
    nome = f"plano_{of['codigo']}.json"
    return Response(json.dumps(dados, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})


@app.route("/oficinas/<int:oficina_id>/respostas.csv")
@somente_condutor
def respostas_csv(oficina_id):
    of = oficina_do_condutor(oficina_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["participante", "papel", "unidade", "enviado_em"] + TODOS_CODIGOS
               + [f"comentario_{c}" for c in TODOS_CODIGOS])
    for p in participantes_da(oficina_id):
        r, c = carregar(p["respostas_json"]), carregar(p["comentarios_json"])
        valores = []
        for cod in TODOS_CODIGOS:
            v = r.get(cod, "")
            valores.append(rules.letra(int(v)) if cod in CODIGOS_C and v else rules.RESPOSTAS_T.get(v, v))
        w.writerow([p["nome"], p["papel"] or "", p["unidade"] or "", p["enviado_em"] or ""]
                   + valores + [c.get(cod, "") for cod in TODOS_CODIGOS])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=respostas_{of['codigo']}.csv"})


# ---------------------------------------------------------------------------
# Regras do plano: leitura, edição, versões e simulação
# ---------------------------------------------------------------------------
def _uso_versoes():
    return {r["regras_versao_id"]: r["n"] for r in get_db().execute(
        "SELECT regras_versao_id, COUNT(*) AS n FROM oficinas WHERE regras_versao_id IS NOT NULL GROUP BY regras_versao_id")}


@app.route("/regras")
@somente_condutor
def regras_ver():
    versao_id = request.args.get("versao", type=int)
    versao, R = versao_regras(versao_id)
    ativa, _ = versao_regras()
    versoes = get_db().execute("SELECT id, nota, criado_em FROM regras_versoes ORDER BY id DESC").fetchall()
    return render_template("regras.html", R=R, versao=versao, ativa=ativa, versoes=versoes,
                           uso=_uso_versoes(), rules=rules, motor=motor)


@app.route("/regras/editar")
@somente_condutor
def regras_editar():
    versao, R = versao_regras()
    meta = {
        "criterios": [{"codigo": c["codigo"], "titulo": c["titulo"], "opcoes": c["opcoes"]} for c in rules.CRITERIOS],
        "condicoes": [{"codigo": t["codigo"], "titulo": t["titulo"]} for t in rules.CONDICOES],
        "respostas": rules.RESPOSTAS_T,
        "contextos": motor.CONTEXTOS,
    }
    return render_template("regras_editar.html", R=R, versao=versao, meta=meta)


def _ler_regras_json():
    dados = request.get_json(silent=True) or {}
    R = dados.get("regras")
    if not isinstance(R, dict):
        return None, None, ["Conteúdo das regras ausente."]
    try:
        R = motor.normalizar(R)
    except (TypeError, KeyError, AttributeError, ValueError):
        return None, None, ["O conjunto de regras está mal formado."]
    return R, dados, motor.validar(R)


@app.route("/regras/salvar", methods=["POST"])
@somente_condutor
def regras_salvar():
    R, dados, erros = _ler_regras_json()
    if erros:
        return jsonify(ok=False, erros=erros), 400
    vid = salvar_versao(R, dados.get("nota") or "Edição pelo editor de regras")
    return jsonify(ok=True, versao=vid)


@app.route("/regras/simular", methods=["POST"])
@somente_condutor
def regras_simular():
    R, dados, erros = _ler_regras_json()
    if erros:
        return jsonify(ok=False, erros=erros), 400
    perfil = dados.get("perfil") or {}
    niveis = {c: int(perfil.get(c, 1)) for c in CODIGOS_C if str(perfil.get(c, 1)) in ("1", "2", "3")}
    condicoes = {t: perfil.get(t, "no") for t in CODIGOS_T if perfil.get(t, "no") in rules.RESPOSTAS_T}
    plano = motor.simular(R, niveis, condicoes, bool(perfil.get("tem_sistema", True)))
    return jsonify(ok=True, plano=plano)


@app.route("/regras/exportar")
@somente_condutor
def regras_exportar():
    versao, R = versao_regras(request.args.get("versao", type=int))
    return Response(json.dumps(R, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=regras_bussola_v{versao['id']}.json"})


@app.route("/regras/importar", methods=["POST"])
@somente_condutor
def regras_importar():
    arquivo = request.files.get("arquivo")
    try:
        R = motor.normalizar(json.loads(arquivo.read().decode("utf-8")))
    except (AttributeError, ValueError, TypeError, KeyError):
        flash("Não foi possível ler o arquivo. Envie um JSON exportado pelo sistema.", "erro")
        return redirect(url_for("regras_ver"))
    erros = motor.validar(R)
    if erros:
        flash("O arquivo tem problemas e não foi importado: " + " ".join(erros[:5]), "erro")
        return redirect(url_for("regras_ver"))
    vid = salvar_versao(R, f"Importada de {arquivo.filename}")
    flash(f"Regras importadas como versão {vid}, que passa a ser a ativa.", "ok")
    return redirect(url_for("regras_ver"))


@app.route("/regras/versoes/<int:versao_id>/restaurar", methods=["POST"])
@somente_condutor
def regras_restaurar(versao_id):
    versao, R = versao_regras(versao_id)
    if versao["id"] != versao_id:
        abort(404)
    vid = salvar_versao(R, f"Restauração da versão {versao_id}")
    flash(f"A versão {versao_id} foi restaurada como versão {vid}, que passa a ser a ativa.", "ok")
    return redirect(url_for("regras_ver"))


@app.route("/regras/padrao", methods=["POST"])
@somente_condutor
def regras_restaurar_padrao():
    vid = salvar_versao(motor.regras_padrao(), "Restauração das regras padrão do sistema")
    flash(f"As regras padrão foram restauradas como versão {vid}.", "ok")
    return redirect(url_for("regras_ver"))


# ---------------------------------------------------------------------------
# Área dos participantes
# ---------------------------------------------------------------------------
def oficina_por_codigo(codigo):
    of = get_db().execute("SELECT * FROM oficinas WHERE codigo = ?", (codigo.upper(),)).fetchone()
    if not of:
        abort(404)
    return of


def participante_atual(of):
    token = session.get(f"p_{of['codigo']}")
    if not token:
        return None
    return get_db().execute("SELECT * FROM participantes WHERE token = ? AND oficina_id = ?",
                            (token, of["id"])).fetchone()


@app.route("/o", methods=["GET", "POST"])
def entrar_por_codigo():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        if get_db().execute("SELECT 1 FROM oficinas WHERE codigo = ?", (codigo,)).fetchone():
            return redirect(url_for("participar", codigo=codigo))
        flash("Código não encontrado. Confira com o condutor.", "erro")
    return render_template("codigo.html")


@app.route("/o/<codigo>", methods=["GET", "POST"])
def participar(codigo):
    of = oficina_por_codigo(codigo)
    p = participante_atual(of)
    if request.method == "POST" and not p:
        if of["status"] != "aberta":
            flash("As respostas desta oficina estão encerradas.", "erro")
            return redirect(url_for("participar", codigo=of["codigo"]))
        nome = request.form.get("nome", "").strip()[:120]
        if not nome:
            flash("Informe seu nome.", "erro")
            return redirect(url_for("participar", codigo=of["codigo"]))
        token = secrets.token_urlsafe(24)
        db = get_db()
        db.execute("""INSERT INTO participantes (oficina_id, token, nome, papel, unidade, criado_em, atualizado_em)
                      VALUES (?,?,?,?,?,?,?)""",
                   (of["id"], token, nome, request.form.get("papel", "").strip()[:120],
                    request.form.get("unidade", "").strip()[:120], agora(), agora()))
        db.commit()
        session[f"p_{of['codigo']}"] = token
        return redirect(url_for("participar", codigo=of["codigo"]))
    if not p:
        return render_template("entrar.html", of=of)
    return render_template("questionario.html", of=of, p=p, rules=rules,
                           respostas=carregar(p["respostas_json"]),
                           comentarios=carregar(p["comentarios_json"]),
                           ctx=carregar(of["contexto_json"]), total_itens=len(TODOS_CODIGOS))


def limpar_respostas(dados):
    respostas, comentarios = {}, {}
    for cod in CODIGOS_C:
        v = str(dados.get(cod, ""))
        if v in ("1", "2", "3"):
            respostas[cod] = int(v)
    for cod in CODIGOS_T:
        v = dados.get(cod, "")
        if v in rules.RESPOSTAS_T:
            respostas[cod] = v
    for cod in TODOS_CODIGOS:
        texto = str(dados.get(f"com_{cod}", "") or "").strip()[:LIMITE_COMENTARIO]
        if texto:
            comentarios[cod] = texto
    return respostas, comentarios


@app.route("/o/<codigo>/salvar", methods=["POST"])
def salvar_participante(codigo):
    of = oficina_por_codigo(codigo)
    p = participante_atual(of)
    if not p:
        return jsonify(ok=False, erro="Participante não identificado. Recarregue a página."), 403
    if of["status"] != "aberta":
        return jsonify(ok=False, erro="As respostas desta oficina foram encerradas pelo condutor."), 409
    respostas, comentarios = limpar_respostas(request.form)
    enviar = request.form.get("acao") == "enviar"
    faltando = [c for c in TODOS_CODIGOS if c not in respostas]
    db = get_db()
    if enviar and faltando:
        return jsonify(ok=False, erro="Responda todos os itens antes de enviar.", faltando=faltando), 400
    # Um envio anterior deixa de valer se o participante apagar alguma resposta.
    db.execute("""UPDATE participantes SET respostas_json = ?, comentarios_json = ?, atualizado_em = ?,
                  enviado_em = CASE WHEN ? THEN ? WHEN ? THEN NULL ELSE enviado_em END WHERE id = ?""",
               (json.dumps(respostas), json.dumps(comentarios, ensure_ascii=False), agora(),
                1 if enviar else 0, agora(), 1 if faltando else 0, p["id"]))
    db.commit()
    enviado = enviar or (bool(p["enviado_em"]) and not faltando)
    return jsonify(ok=True, enviado=enviado, salvo_em=agora(), respondidos=len(respostas))


@app.route("/o/<codigo>/sair", methods=["POST"])
def sair_participante(codigo):
    of = oficina_por_codigo(codigo)
    session.pop(f"p_{of['codigo']}", None)
    return redirect(url_for("participar", codigo=of["codigo"]))


@app.errorhandler(404)
def nao_encontrado(_e):
    return render_template("erro.html", titulo="Página não encontrada",
                           mensagem="Confira o link ou o código da oficina."), 404


@app.errorhandler(413)
def grande_demais(_e):
    return jsonify(ok=False, erro="Conteúdo grande demais."), 413


@app.template_filter("datahora")
def datahora(valor):
    if not valor:
        return "–"
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


@app.template_filter("titulo_criterio")
def titulo_criterio(cod):
    c = rules.CRITERIOS_POR_CODIGO.get(cod)
    return c["titulo"].lower() if c else cod


@app.template_filter("data_br")
def data_br(valor):
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return valor or "–"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
