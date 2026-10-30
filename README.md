
Aplicação web para controlar o **cadastro de colaboradores**, o **estoque de Equipamentos de Proteção Individual (EPIs)** e os **empréstimos/devoluções** desses equipamentos, com relatórios filtráveis.

O projeto não depende de nenhuma biblioteca Python externa: o back-end usa apenas a biblioteca padrão (`http.server`, `sqlite3`, `json`, `re`), o banco é um arquivo SQLite e o front-end é uma página HTML única com Bootstrap.

---

## Sumário

1. [Principais funcionalidades](#-principais-funcionalidades)
2. [Tecnologias utilizadas](#-tecnologias-utilizadas)
3. [Estrutura dos arquivos](#-estrutura-dos-arquivos)
4. [Como o sistema funciona](#-como-o-sistema-funciona)
5. [Banco de dados](#-banco-de-dados)
6. [Regras de negócio e validações](#-regras-de-negócio-e-validações)
7. [API REST](#-api-rest)
8. [Telas do sistema](#-telas-do-sistema)
9. [Passo a passo para usar](#-passo-a-passo-para-usar)
10. [Possíveis erros e soluções](#-possíveis-erros-e-soluções)
11. [Correções aplicadas e limitações restantes](#-correções-aplicadas-e-limitações-restantes)
12. [Melhorias futuras](#-melhorias-futuras)

---

## Principais funcionalidades

| Módulo | O que faz |
|---|---|
| **Colaboradores** | Cadastrar, listar, pesquisar por nome, editar e excluir colaboradores (nome, cargo, matrícula). |
| **Equipamentos (EPIs)** | Cadastrar, listar, editar e excluir EPIs (nome, tipo, quantidade em estoque, validade, situação). |
| **Empréstimos** | Registrar a entrega de um EPI a um colaborador, com data do empréstimo e data prevista de devolução. Bloqueia o empréstimo quando o estoque se esgota. |
| **Devoluções** | Atualizar o status do empréstimo para *Devolvido*, informando data efetiva e observação. |
| **Relatórios / Análise** | Histórico de empréstimos com filtro combinado (colaborador **E** equipamento **E** status). |

---

## Tecnologias utilizadas

- **Python 3** (a imagem Docker usa `python:3.11-slim`; localmente funciona do 3.8 em diante) – servidor HTTP e API.
- **SQLite 3** – banco de dados em arquivo (`controle_epi.db`), com chaves estrangeiras ativadas.
- **HTML + JavaScript puro** (sem framework) – interface e chamadas à API via `fetch`.
- **Bootstrap 5.3** (via CDN) + `style.css` – layout e estilo.
- **Docker / Docker Compose** – empacotamento e execução (opcional).

---

## Estrutura dos arquivos

```
projeto/
├── servidor.py          # Servidor HTTP + API REST + validações de negócio
├── banco.py             # Conexão e criação das tabelas SQLite
├── index.html           # Interface (4 telas) + toda a lógica JavaScript
├── style.css            # Estilos personalizados (fonte e animação de fade)
├── Dockerfile           # Receita da imagem Docker
├── docker-compose.yml   # Sobe o container e persiste o banco
└── dados/
    └── controle_epi.db  # Banco SQLite (pasta e arquivo criados automaticamente)
```

### Função de cada arquivo

**`banco.py`**
- `conectar()` – abre a conexão com `dados/controle_epi.db` (caminho calculado a partir da pasta do próprio arquivo, então funciona de qualquer diretório) e executa `PRAGMA foreign_keys = ON` (sem isso o SQLite ignora as chaves estrangeiras).
- `inicializar_banco()` – se existir um `controle_epi.db` antigo na raiz (versões anteriores) e ainda não houver banco em `dados/`, **copia-o automaticamente**; depois cria as tabelas `colaboradores`, `equipamentos` e `emprestimos` caso ainda não existam (`CREATE TABLE IF NOT EXISTS`). Pode ser executado várias vezes sem apagar dados.
- Se executado diretamente (`python banco.py`), apenas inicializa o banco.

**`servidor.py`**
- `validar_colaborador()` / `validar_equipamento()` – regras de validação e de duplicidade (usadas em cadastro e edição).
- `RequisicaoHandler` – classe que herda de `SimpleHTTPRequestHandler`. Ela serve os arquivos estáticos (`index.html`, `style.css`) **e** responde às rotas `/api/...`:
  - `do_GET` – consultas (com filtros).
  - `do_POST` – criação.
  - `do_PUT` – atualização.
  - `do_DELETE` – exclusão.
  - `do_OPTIONS` – resposta de *preflight* de CORS.
  - `_responder_json()` – envia JSON em UTF-8 com cabeçalhos CORS.
- Serve **apenas** `/`, `/index.html` e `/style.css` como arquivos estáticos (o banco e o código-fonte não ficam acessíveis).
- No bloco `__main__` inicializa o banco e sobe o servidor (com threads) na porta **8000**.

**`index.html`** – contém o menu lateral, as quatro telas e o JavaScript:

| Função JS | Papel |
|---|---|
| `mostrarTela(nome)` | Alterna entre as telas e recarrega os dados da tela aberta. |
| `exibirAlerta(msg, tipo)` | Mostra mensagens de sucesso/aviso/erro no topo. |
| `carregarColaboradores()` / `salvarColaborador()` / `editarColaborador()` | CRUD de colaboradores (a busca por nome é feita a cada tecla digitada). |
| `carregarEquipamentos()` / `salvarEquipamento()` / `editarEquipamento()` | CRUD de equipamentos. |
| `carregarOpcoesEmprestimo()` | Preenche os `<select>` de colaborador e equipamento. |
| `tratarMudancaStatus()` | Exibe os campos de devolução somente quando o status é *Devolvido*. |
| `salvarEmprestimo()` / `editarEmprestimo()` / `limparFormEmprestimo()` | Registro e atualização de empréstimos (valida data e estoque antes de enviar). |
| `carregarOpcoesFiltros()` / `carregarRelatorios()` | Tela de relatórios com filtros. |
| `excluirItem(endpoint, id, callback)` | Exclusão genérica com confirmação. |

**`style.css`** – define a fonte (Segoe UI) e a animação `fadeIn` aplicada às telas (`.secao-tela`).

**`Dockerfile`** – parte de `python:3.11-slim`, copia `banco.py`, `servidor.py`, `index.html` e `style.css` para `/app`, executa `python banco.py`, expõe a porta 8000 e inicia com `python servidor.py`.

**`docker-compose.yml`** – constrói a imagem, nomeia o container `sistema_controle_epi`, publica a porta `8000:8000`, mapeia a **pasta** `./dados` para `/app/dados` (persistência dos dados) e usa `restart: always`.

---

## Como o sistema funciona

```
┌────────────────────┐   fetch (JSON)    ┌─────────────────────────┐   sqlite3   ┌────────────────┐
│ Navegador          │ ────────────────► │ servidor.py             │ ──────────► │ controle_epi.db│
│ index.html + JS    │ ◄──────────────── │ http.server + API REST  │ ◄────────── │ (SQLite)       │
│ Bootstrap (CDN)    │   HTML/CSS/JSON   │ + validações de negócio │             │                │
└────────────────────┘                   └─────────────────────────┘             └────────────────┘
```

1. O usuário acessa `http://localhost:8000`. O servidor entrega o `index.html` (comportamento padrão do `SimpleHTTPRequestHandler`) e o `style.css`.
2. O JavaScript faz requisições para `/api/colaboradores`, `/api/equipamentos` e `/api/emprestimos` usando caminhos **relativos** (por isso a página precisa ser aberta pelo servidor, e não clicando no arquivo).
3. O servidor valida os dados, executa o SQL com parâmetros (`?`, protegendo contra SQL Injection) e devolve JSON.
4. Em caso de erro de validação, a API responde **HTTP 400** com `{"erro": "mensagem"}` e o front-end mostra a mensagem em um alerta vermelho.

### Fluxo de um empréstimo

1. O técnico escolhe colaborador, equipamento, data do empréstimo e data prevista de devolução.
2. O front-end verifica se a data prevista é **posterior ao momento atual** e se há estoque disponível.
3. O back-end repete a verificação de estoque (a regra fica protegida mesmo se alguém chamar a API diretamente).
4. O empréstimo é gravado com status `Emprestado`.
5. Na devolução, o técnico clica em **Editar Status** (tela de Relatórios), troca para `Devolvido` e informa a data efetiva e uma observação. O EPI volta a contar como disponível.

> **Estoque disponível = `quantidade` do equipamento − número de empréstimos com status `Emprestado` daquele equipamento.**

---

## Banco de dados

Arquivo: `dados/controle_epi.db` (SQLite).

**`colaboradores`**

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `nome` | TEXT NOT NULL | |
| `cargo` | TEXT NOT NULL | |
| `matricula` | TEXT NOT NULL | Guardada como texto (preserva zeros à esquerda). |

**`equipamentos`**

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `nome` | TEXT NOT NULL | |
| `tipo` | TEXT NOT NULL | Ex.: "Proteção Cabeça". |
| `quantidade` | INTEGER NOT NULL | Total em estoque. |
| `validade` | TEXT NOT NULL | Data no formato `AAAA-MM-DD`. |
| `situacao` | TEXT NOT NULL | `Disponível` ou `Indisponível`. |

**`emprestimos`**

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `colaborador_id` | INTEGER NOT NULL | FK → `colaboradores(id)` **ON DELETE RESTRICT** |
| `equipamento_id` | INTEGER NOT NULL | FK → `equipamentos(id)` **ON DELETE RESTRICT** |
| `data_emprestimo` | TEXT NOT NULL | Formato `AAAA-MM-DDTHH:MM`. |
| `data_prevista` | TEXT NOT NULL | Formato `AAAA-MM-DDTHH:MM`. |
| `data_devolucao` | TEXT | Preenchida na devolução. |
| `status` | TEXT NOT NULL | `Emprestado` ou `Devolvido`. |
| `observacao` | TEXT | Texto livre da devolução. |

Relacionamento: **um colaborador** e **um equipamento** podem ter **vários empréstimos** (1:N em cada lado).

> ℹ Um colaborador ou EPI **que já tem empréstimos registrados não pode ser excluído** (a API responde com uma mensagem explicando). Para removê-lo, exclua antes os empréstimos dele. Isso evita perder o histórico sem querer.

---

## Regras de negócio e validações

| Entidade | Regra | Onde é aplicada |
|---|---|---|
| Colaborador | Nome e cargo: **somente letras** (com acentos) e espaços. | Front-end (HTML `pattern` + JS) e back-end |
| Colaborador | Matrícula: **somente números**. | Front-end e back-end |
| Colaborador | **Nome único** (sem diferenciar maiúsculas/minúsculas, inclusive com acentos) e **matrícula única**. | Back-end |
| Equipamento | Nome e tipo: **somente letras** e espaços. | Front-end e back-end |
| Equipamento | A combinação **nome + tipo** não pode se repetir. | Back-end |
| Equipamento | Quantidade inteira ≥ 1; validade em `AAAA-MM-DD`; situação `Disponível`/`Indisponível`. | Front-end e back-end |
| Equipamento | A quantidade não pode ser reduzida abaixo do que está emprestado no momento. | Back-end |
| Empréstimo | Data prevista deve ser **posterior ao momento atual** ao registrar um empréstimo em aberto (usa o relógio do navegador). | Front-end |
| Empréstimo | Data prevista **posterior** à data do empréstimo; datas em formato válido. | Back-end |
| Empréstimo | Só é possível emprestar EPI **Disponível** e **dentro da validade**. | Back-end |
| Empréstimo | Ao marcar como *Devolvido*, a data efetiva é **obrigatória** e não pode ser anterior ao empréstimo. | Front-end e back-end |
| Empréstimo | **Reabrir** um empréstimo devolvido também respeita o estoque. | Back-end |
| Empréstimo | **Limite de estoque**: não permite emprestar se todas as unidades já estão emprestadas (registros históricos já *Devolvido* não consomem estoque). | Front-end e back-end |
| Empréstimo | Na edição, só `status`, `data_devolucao` e `observacao` podem mudar (os demais campos ficam bloqueados). | Front-end e back-end |

---

## API REST

URL base: `http://localhost:8000`. Corpo e respostas em JSON (UTF-8).

| Método | Rota | Parâmetros / Corpo | Descrição |
|---|---|---|---|
| GET | `/api/colaboradores` | `?nome=` (opcional, busca parcial) | Lista colaboradores. |
| POST | `/api/colaboradores` | `{nome, cargo, matricula}` | Cria colaborador. |
| PUT | `/api/colaboradores` | `{id, nome, cargo, matricula}` | Atualiza colaborador. |
| DELETE | `/api/colaboradores?id=1` | – | Exclui colaborador. |
| GET | `/api/equipamentos` | – | Lista equipamentos. |
| POST | `/api/equipamentos` | `{nome, tipo, quantidade, validade, situacao}` | Cria equipamento. |
| PUT | `/api/equipamentos` | `{id, nome, tipo, quantidade, validade, situacao}` | Atualiza equipamento. |
| DELETE | `/api/equipamentos?id=1` | – | Exclui equipamento. |
| GET | `/api/emprestimos` | `?colaborador_id=&equipamento_id=&status=` (todos opcionais, combinados com AND) | Lista empréstimos com nomes do colaborador e do equipamento. |
| POST | `/api/emprestimos` | `{colaborador_id, equipamento_id, data_emprestimo, data_prevista, status}` | Registra empréstimo (valida estoque). |
| PUT | `/api/emprestimos` | `{id, status, data_devolucao, observacao}` | Atualiza status/devolução. |
| DELETE | `/api/emprestimos?id=1` | – | Exclui empréstimo. |

**Códigos de resposta:** `200` (sucesso), `201` (criado), `400` (erro de validação, com `{"erro": "..."}`), `404` (rota ou registro não encontrado), `500` (erro interno inesperado). O CORS foi removido: a API só responde ao próprio site servido por `localhost:8000`.

**Exemplos com `curl`:**

```bash
# Criar colaborador
curl -X POST http://localhost:8000/api/colaboradores \
  -H "Content-Type: application/json" \
  -d '{"nome":"Maria Silva","cargo":"Soldadora","matricula":"1001"}'

# Listar empréstimos ainda em aberto
curl "http://localhost:8000/api/emprestimos?status=Emprestado"

# Excluir colaborador de id 3
curl -X DELETE "http://localhost:8000/api/colaboradores?id=3"
```

---

## Telas do sistema

O menu lateral dá acesso a quatro telas:

1. **Colaboradores** – formulário (nome, cargo, matrícula), campo de pesquisa por nome e tabela com botões *Editar* e *Excluir*.
2. **Equipamentos** – formulário (nome, tipo, quantidade, validade, situação) e tabela com *Editar* e *Excluir*.
3. **Empréstimos** – formulário para registrar a entrega de um EPI. Ao escolher o status *Devolvido* aparecem os campos de data efetiva e observação.
4. **Relatórios / Análise** – tabela com todos os empréstimos e três filtros combinados (colaborador, equipamento, status). É aqui que se clica em **Editar Status** para registrar uma devolução.

---

## Passo a passo para usar

### Pré-requisitos

- **Opção A (Docker):** Docker e Docker Compose instalados.
- **Opção B (sem Docker):** Python 3.8 ou superior.
- Conexão com a internet no navegador (o Bootstrap é carregado de um CDN).

### Opção A – Executando com Docker (recomendado)

**1. Coloque todos os arquivos na mesma pasta** (`Dockerfile`, `docker-compose.yml`, `servidor.py`, `banco.py`, `index.html`, `style.css`).

**2. Construa e suba o container:**

```bash
docker compose up --build -d
```

**3. Acesse no navegador:** <http://localhost:8000>

Não é preciso criar o banco antes: a pasta `dados/` aparece sozinha ao lado do `docker-compose.yml` e guarda o `controle_epi.db`.

Comandos úteis:

```bash
docker compose logs -f        # acompanhar os logs
docker compose ps             # ver se o container está rodando
docker compose down           # parar e remover o container (o banco continua em ./dados)
docker compose up --build -d  # recriar após alterar o código
```

> **Já usava a versão antiga com `controle_epi.db` na raiz?** Deixe o arquivo onde está e suba normalmente com o `servidor.py` local: ele copia o banco antigo para `dados/` na primeira execução. No Docker, copie manualmente: `mkdir dados && cp controle_epi.db dados/` antes do `docker compose up`.

### Opção B – Executando direto no computador

```bash
# 1. Entre na pasta do projeto
cd caminho/do/projeto

# 2. (Opcional) Criar o banco manualmente – o servidor já faz isso ao iniciar
python banco.py

# 3. Iniciar o servidor
python servidor.py
```

Saída esperada: `Servidor rodando em: http://localhost:8000`. Abra o endereço no navegador. Para encerrar, pressione `Ctrl + C`.

### Usando o sistema (ordem recomendada)

1. **Cadastre os colaboradores** na tela *Colaboradores* (ex.: Nome `João Pereira`, Cargo `Eletricista`, Matrícula `2045`) e clique em **Salvar**.
2. **Cadastre os EPIs** na tela *Equipamentos* (ex.: Nome `Capacete`, Tipo `Protecao Cabeca`, Quantidade `10`, Validade futura, Situação `Disponível`).
3. **Registre um empréstimo** na tela *Empréstimos*: escolha colaborador e equipamento, informe a data do empréstimo e uma **data prevista de devolução futura**, mantenha o status `Emprestado` e clique em **Registrar / Atualizar Empréstimo**. Você será levado automaticamente à tela de Relatórios.
4. **Registre a devolução** na tela *Relatórios / Análise*: clique em **Editar Status** na linha do empréstimo, mude para `Devolvido`, preencha a data efetiva (obrigatória) e a observação e confirme.
5. **Consulte o histórico** usando os filtros de colaborador, equipamento e status.
6. Para **editar** um colaborador ou EPI, clique em *Editar* (os dados sobem para o formulário), altere e clique em *Salvar*. Para **excluir**, clique em *Excluir* e confirme (colaboradores e EPIs com empréstimos registrados só podem ser excluídos depois de apagar esses empréstimos).

### Backup e reinício do zero

- **Backup:** copie a pasta `dados/` (de preferência com o sistema parado).
- **Zerar os dados:** pare o sistema, apague a pasta `dados/` e inicie novamente — o banco é recriado vazio.

---

## Possíveis erros e soluções

### Erros de instalação e execução

| Sintoma / mensagem | Causa provável | Solução |
|---|---|---|
| `failed to read dockerfile` / `open Dockerfile: no such file or directory` | O arquivo não se chama exatamente `Dockerfile` (no projeto original estava `dockefile`). | Na versão corrigida o nome já está certo; confira se o arquivo se chama `Dockerfile` (D maiúsculo, sem extensão). |
| `unable to open database file` / `sqlite3.OperationalError` | Sem permissão de escrita na pasta `dados/`, ou (versão antiga) o Docker criou uma **pasta** no lugar de `controle_epi.db`. | Garanta permissão de escrita na pasta do projeto. Se vier da versão antiga: `docker compose down`, apague a pasta `controle_epi.db` criada por engano e use os arquivos novos. |
| `OSError: [Errno 98] Address already in use` (ou `10048` no Windows) / `port is already allocated` | Outro programa ou container já usa a porta 8000. | Feche o outro processo, ou mude a porta: no compose use `"8080:8000"` e acesse `localhost:8080`; sem Docker altere `PORT` em `servidor.py`. (O reinício rápido do próprio servidor já não causa mais esse erro.) |
| `ModuleNotFoundError: No module named 'banco'` | `banco.py` não está na mesma pasta de `servidor.py`. | Mantenha os dois arquivos juntos. |
| Página abre sem estilo / menu "quebrado" | Sem internet: o Bootstrap é carregado de `cdn.jsdelivr.net`. | Conecte-se à internet ou baixe o Bootstrap e referencie os arquivos locais. |
| Listas vazias, nada carrega, erros `Failed to fetch` no console (F12) | `index.html` foi aberto com duplo clique (`file://`) ou o servidor não está rodando. | Abra sempre por `http://localhost:8000` com o servidor ativo. |
| Alterei o código e nada mudou no Docker | A imagem continua a antiga (os arquivos são copiados no *build*). | `docker compose up --build -d`. |
| `database is locked` | Outro programa (ex.: DB Browser for SQLite) está com o banco aberto escrevendo. | Feche o outro programa e tente novamente. |

### Mensagens exibidas pelo sistema

| Mensagem | Significado | Solução |
|---|---|---|
| "O nome do colaborador deve conter apenas letras." / "O cargo deve conter apenas letras." / "O nome do EPI deve conter apenas letras." | O texto tem número, hífen, apóstrofo, ponto, etc. (ex.: `João-Pedro`, `D'Ávila`, `Capacete 2`). | Use apenas letras e espaços. Essa restrição é uma regra do projeto; para mudá-la, veja a seção de limitações restantes. |
| "A matrícula deve conter apenas números." | Letras ou símbolos na matrícula. | Digite somente dígitos. |
| "Já existe um colaborador com esse nome / essa matrícula." | Duplicidade bloqueada pela regra de negócio. | Use outra matrícula ou edite o cadastro existente. Homônimos precisam ser diferenciados no nome (ex.: "Ana Souza Lima"). |
| "Já existe um equipamento cadastrado com este nome e tipo." | Mesmo nome + tipo já cadastrados. | Edite o existente e aumente a quantidade, ou use outro tipo. |
| "Estoque esgotado! O EPI '...' possui N unidade(s) e todas já estão emprestadas." | Todas as unidades estão com status `Emprestado`. | Registre a devolução de alguma unidade ou aumente a quantidade do EPI. |
| "A data prevista para devolução deve ser posterior à data e hora atuais!" | A data prevista está no passado. | Escolha uma data/hora futura. |
| "Campo obrigatório ausente: ..." | Chamada direta à API sem algum campo. | Envie todos os campos listados na seção [API REST](#-api-rest). |
| "O EPI '...' está marcado como Indisponível." / "...está com a validade vencida" | O EPI não pode ser entregue nessas condições. | Edite o EPI (situação/validade) ou escolha outro. |
| "Não é possível excluir: ... possui N empréstimo(s)" | O colaborador/EPI tem histórico. | Exclua antes os empréstimos ligados a ele, se realmente desejar. |
| "A quantidade não pode ser menor que N..." | Há N unidades emprestadas no momento. | Registre as devoluções antes de reduzir o estoque. |
| "Informe a data efetiva da devolução." | Status *Devolvido* sem data. | Preencha a data de devolução. |
| Selects de colaborador/equipamento vazios em *Empréstimos* | Ainda não há colaboradores ou equipamentos cadastrados. | Cadastre-os primeiro. |

## Resumo rápido

```bash
docker compose up --build -d       # subir o sistema
# abrir http://localhost:8000
docker compose down                # parar
```