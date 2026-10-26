# Bússola — oficinas de diagnóstico de Design de Serviços

Sistema web para aplicar o Formulário de Diagnóstico de Serviços em oficinas com vários participantes e gerar o plano metodológico automaticamente.

## Como a oficina funciona

1. **Condutor cria a oficina** e projeta o QR code ou o código de 6 letras.
2. **Identificação e contextualização** são preenchidas em grupo, pelo condutor, com a tela projetada. O salvamento é automático.
3. **Cada participante responde C1–C10 e T1–T8 individualmente** pelo celular ou notebook. As respostas são salvas a cada clique; se a rede cair, o sistema tenta de novo sozinho. O participante pode deixar um comentário em cada item.
4. **O condutor acompanha em tempo real** quem entrou, o progresso de cada um e quem já enviou. Quando todos terminarem, encerra as respostas.
5. **Consolidação**: o sistema mostra o mapa de respostas de todos os participantes, classifica cada item em *consenso*, *divergência moderada* ou *divergência alta* e sugere uma alternativa. O condutor conduz a discussão (pode filtrar só os divergentes e ocultar os nomes ao projetar) e registra a decisão do grupo, com uma justificativa opcional.
6. **Plano metodológico** é gerado a partir da consolidação, nas seis etapas de Design de Serviços (Alinhamento e Escopo, Exploração do problema, Ideação, Prototipação, Handover e integração com desenvolvimento paralelo, Avaliação e Melhoria Contínua): ponto de entrada, intensidade de cada etapa, entrada e saída de cada etapa, técnicas sugeridas, intensidade de cada etapa (alta, média ou baixa) com texto justificando, pontos de atenção (T1–T8 e riscos), registro das divergências e quadro de aprovação. Pode ser impresso ou salvo em PDF pelo navegador e exportado em JSON.

### Regras de divergência

| Situação | Critérios (a/b/c) | Condições (Sim/Não/Parcial/Não sei) |
| --- | --- | --- |
| Consenso | Todos iguais, ou ≥ 2/3 na mesma alternativa sem a e c ao mesmo tempo | Todos iguais, ou ≥ 2/3 na mesma resposta sem “Não” junto de “Sim”/“Não sei” |
| Divergência alta | Há respostas a **e** c | Há “Não” junto de “Sim” ou “Não sei” |
| Divergência moderada | Demais casos | Demais casos |

A **sugestão** é a alternativa mais votada; em empate, prevalece a mais precavida (nível mais alto ou resposta de maior risco).

Todas as regras, textos e técnicas ficam em `rules.py`. Para mudar o limiar de consenso, trocar técnicas ou ajustar o ponto de entrada, altere apenas esse arquivo.

## Instalação

Requer Python 3.10 ou superior.

```bash
cd bussola
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

## Executar na oficina (rede local)

Os participantes precisam estar na mesma rede do computador do condutor (ou o sistema precisa estar num servidor acessível a todos).

```bash
waitress-serve --host 0.0.0.0 --port 5000 --threads 16 app:app
```

Abra `http://localhost:5000` no computador do condutor.

Se o condutor abrir o sistema por `localhost`, o QR code usa automaticamente o IP da máquina na rede local, para funcionar nos celulares. Se o sistema estiver atrás de um proxy ou domínio, defina o endereço público:

```bash
export BUSSOLA_URL_PUBLICA=https://bussola.unb.br
```

Participantes também podem acessar `<endereço>/o` e digitar o código.

## Acesso

O sistema não exige login: ao abrir o endereço, o condutor cai direto na lista de oficinas. Participantes entram pelo QR code ou pelo código da oficina, e as telas deles não mostram o menu do condutor.

Atenção: sem login, qualquer pessoa na mesma rede que digitar o endereço do sistema consegue abrir o painel. Para exigir login, inicie o servidor com `BUSSOLA_EXIGIR_LOGIN=1`. O login padrão é **itrac** / **123456**, e pode ser trocado com `BUSSOLA_ADMIN_USUARIO` e `BUSSOLA_ADMIN_SENHA`.

## Variáveis de ambiente

| Variável | Uso |
| --- | --- |
| `BUSSOLA_EXIGIR_LOGIN=1` | Passa a exigir login no painel do condutor |
| `BUSSOLA_ADMIN_USUARIO` / `BUSSOLA_ADMIN_SENHA` | Login usado quando ele é exigido (padrão: itrac / 123456) |
| `BUSSOLA_URL_PUBLICA` | Endereço usado no QR code e no link (quando atrás de proxy/domínio) |
| `BUSSOLA_SECRET_KEY` | Chave de sessão; se ausente, é gerada em `instance/secret_key` |
| `BUSSOLA_INSTANCE` | Pasta do banco e da chave (padrão: `instance/`) |
| `BUSSOLA_HTTPS=1` | Marca o cookie de sessão como seguro (use quando servir em HTTPS) |

## Dados e backup

Tudo fica em `instance/bussola.sqlite3` (SQLite em modo WAL, adequado para dezenas de participantes simultâneos). Para backup, copie a pasta `instance/` com o servidor parado.

Exportações disponíveis por oficina:
- **Respostas (CSV)**: uma linha por participante, com respostas e comentários; abre direto no Excel.
- **Dados do plano (JSON)**: contexto, respostas individuais, consolidação com justificativas e plano gerado.

## Segurança

- Login opcional (`BUSSOLA_EXIGIR_LOGIN=1`); proteção CSRF em todos os formulários, cookies `HttpOnly` e `SameSite=Lax`.
- Participantes são identificados por um token aleatório guardado na sessão do navegador; podem retomar e alterar as respostas enquanto a oficina estiver aberta.
- Ao encerrar as respostas, nenhuma alteração dos participantes é aceita.

## Testes

```bash
pip install pytest
python -m pytest tests -q
```

O teste de ponta a ponta simula uma oficina com cinco participantes, divergências, consolidação e geração do plano.

## Estrutura

```
app.py          rotas, banco de dados, segurança
rules.py        conteúdo do formulário, análise de divergência e geração do plano
templates/      telas (condutor, participante, consolidação, plano)
static/         estilos
tests/          testes automatizados
```
