import datetime
import http.server
import json
import re
import socketserver
import sqlite3
import urllib.parse

import banco

PORT = 8000

# Somente estes caminhos são entregues como arquivos estáticos.
# Isso impede o download de controle_epi.db, servidor.py, banco.py etc.
ARQUIVOS_PUBLICOS = {"/", "/index.html", "/style.css"}

REGEX_LETRAS = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s]+$")
REGEX_NUMEROS = re.compile(r"^[0-9]+$")

STATUS_EMPRESTIMO = ("Emprestado", "Devolvido")
SITUACOES_EQUIPAMENTO = ("Disponível", "Indisponível")


# --- FUNÇÕES AUXILIARES ---
def _normalizar(texto):
    """Normaliza para comparação: sem espaços extras e sem diferenciar maiúsculas/minúsculas
    (casefold funciona também com letras acentuadas, ao contrário do LOWER() do SQLite)."""
    return " ".join(str(texto).split()).casefold()


def _parse_datetime(valor):
    """Converte 'AAAA-MM-DDTHH:MM' em datetime. Retorna None se for inválido."""
    try:
        return datetime.datetime.fromisoformat(str(valor))
    except (ValueError, TypeError):
        return None


def _contar_emprestados(cursor, equipamento_id, excluir_id=None):
    """Quantidade de unidades do EPI atualmente emprestadas."""
    sql = "SELECT COUNT(*) FROM emprestimos WHERE equipamento_id = ? AND status = 'Emprestado'"
    params = [equipamento_id]
    if excluir_id is not None:
        sql += " AND id != ?"
        params.append(excluir_id)
    cursor.execute(sql, params)
    return cursor.fetchone()[0]


# --- FUNÇÕES DE VALIDAÇÃO DE NEGÓCIO ---
def validar_colaborador(dados, cursor, item_id=None):
    nome = str(dados.get("nome", "")).strip()
    cargo = str(dados.get("cargo", "")).strip()
    matricula = str(dados.get("matricula", "")).strip()

    if not REGEX_LETRAS.match(nome):
        return "O nome do colaborador deve conter apenas letras."
    if not REGEX_LETRAS.match(cargo):
        return "O cargo deve conter apenas letras."
    if not REGEX_NUMEROS.match(matricula):
        return "A matrícula deve conter apenas números."

    cursor.execute("SELECT id, nome, matricula FROM colaboradores")
    outros = [l for l in cursor.fetchall() if item_id is None or l[0] != int(item_id)]

    if any(_normalizar(l[1]) == _normalizar(nome) for l in outros):
        return "Já existe um colaborador com esse nome."
    if any(l[2] == matricula for l in outros):
        return "Já existe um colaborador com essa matrícula."

    return None


def validar_equipamento(dados, cursor, item_id=None):
    nome = str(dados.get("nome", "")).strip()
    tipo = str(dados.get("tipo", "")).strip()
    quantidade = dados.get("quantidade")
    validade = dados.get("validade")
    situacao = dados.get("situacao")

    if not REGEX_LETRAS.match(nome):
        return "O nome do EPI deve conter apenas letras."
    if not REGEX_LETRAS.match(tipo):
        return "O tipo do EPI deve conter apenas letras."

    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade < 1:
        return "A quantidade deve ser um número inteiro maior ou igual a 1."

    try:
        datetime.date.fromisoformat(str(validade))
    except ValueError:
        return "Validade inválida. Use o formato AAAA-MM-DD."

    if situacao not in SITUACOES_EQUIPAMENTO:
        return "A situação deve ser 'Disponível' ou 'Indisponível'."

    cursor.execute("SELECT id, nome, tipo FROM equipamentos")
    outros = [l for l in cursor.fetchall() if item_id is None or l[0] != int(item_id)]
    if any(_normalizar(l[1]) == _normalizar(nome) and _normalizar(l[2]) == _normalizar(tipo) for l in outros):
        return "Já existe um equipamento cadastrado com este nome e tipo."

    # Não permite reduzir o estoque abaixo do que já está emprestado
    if item_id is not None:
        emprestados = _contar_emprestados(cursor, int(item_id))
        if quantidade < emprestados:
            return (f"A quantidade não pode ser menor que {emprestados}, "
                    f"pois há {emprestados} unidade(s) emprestada(s) no momento.")

    return None


def validar_novo_emprestimo(dados, cursor):
    cursor.execute("SELECT 1 FROM colaboradores WHERE id = ?", (dados.get("colaborador_id"),))
    if not cursor.fetchone():
        return "Colaborador não encontrado."

    cursor.execute("SELECT nome, quantidade, validade, situacao FROM equipamentos WHERE id = ?",
                   (dados.get("equipamento_id"),))
    eq = cursor.fetchone()
    if not eq:
        return "Equipamento não encontrado."
    nome_epi, qtd_total, validade, situacao = eq

    if dados.get("status") not in STATUS_EMPRESTIMO:
        return "Status inválido. Use 'Emprestado' ou 'Devolvido'."

    data_emp = _parse_datetime(dados.get("data_emprestimo"))
    data_prev = _parse_datetime(dados.get("data_prevista"))
    if not data_emp or not data_prev:
        return "Datas inválidas. Use o formato AAAA-MM-DDTHH:MM."
    if data_prev <= data_emp:
        return "A data prevista de devolução deve ser posterior à data do empréstimo."

    if dados["status"] == "Devolvido":
        data_dev = _parse_datetime(dados.get("data_devolucao"))
        if not data_dev:
            return "Informe a data efetiva da devolução."
        if data_dev < data_emp:
            return "A data da devolução não pode ser anterior à data do empréstimo."
        return None  # registro histórico: não consome estoque

    # A partir daqui o EPI sairá do estoque (status Emprestado)
    if situacao != "Disponível":
        return f"O EPI '{nome_epi}' está marcado como Indisponível."
    if str(validade) < datetime.date.today().isoformat():
        return f"O EPI '{nome_epi}' está com a validade vencida ({validade})."
    if _contar_emprestados(cursor, dados["equipamento_id"]) >= qtd_total:
        return (f"Estoque esgotado! O EPI '{nome_epi}' possui {qtd_total} unidade(s) "
                f"e todas já estão emprestadas.")

    return None


def validar_atualizacao_emprestimo(dados, cursor):
    """Retorna (erro, status_http). Valida a mudança de status/devolução."""
    if dados.get("status") not in STATUS_EMPRESTIMO:
        return "Status inválido. Use 'Emprestado' ou 'Devolvido'.", 400

    cursor.execute("SELECT equipamento_id, data_emprestimo FROM emprestimos WHERE id = ?", (dados["id"],))
    atual = cursor.fetchone()
    if not atual:
        return "Empréstimo não encontrado.", 404
    equipamento_id, data_emprestimo = atual

    if dados["status"] == "Emprestado":
        # Reabrir um empréstimo volta a consumir estoque
        cursor.execute("SELECT nome, quantidade FROM equipamentos WHERE id = ?", (equipamento_id,))
        nome_epi, qtd_total = cursor.fetchone()
        if _contar_emprestados(cursor, equipamento_id, excluir_id=dados["id"]) >= qtd_total:
            return (f"Estoque esgotado! O EPI '{nome_epi}' possui {qtd_total} unidade(s) "
                    f"e todas já estão emprestadas."), 400
    else:
        data_dev = _parse_datetime(dados.get("data_devolucao"))
        if not data_dev:
            return "Informe a data efetiva da devolução.", 400
        data_emp = _parse_datetime(data_emprestimo)
        if data_emp and data_dev < data_emp:
            return "A data da devolução não pode ser anterior à data do empréstimo.", 400

    return None, 200


class RequisicaoHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        # Serve os arquivos sempre a partir da pasta do projeto, não importa de onde o script foi chamado
        super().__init__(*args, directory=banco.BASE_DIR, **kwargs)

    # A interface é servida pelo mesmo servidor (mesma origem), então não é necessário CORS.
    # Removê-lo impede que outros sites chamem a API a partir do navegador do usuário.
    def _responder_json(self, dados, status=200):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _ler_json(self):
        """Lê o corpo da requisição. Em caso de JSON inválido já responde 400 e retorna None."""
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not isinstance(dados, dict):
                raise ValueError("O corpo deve ser um objeto JSON.")
            return dados
        except (ValueError, UnicodeDecodeError):
            self._responder_json({"erro": "JSON inválido na requisição."}, status=400)
            return None

    def _caminho(self):
        return urllib.parse.urlparse(self.path).path

    # --- ARQUIVOS ESTÁTICOS (somente os permitidos) ---
    def do_HEAD(self):
        if self._caminho() not in ARQUIVOS_PUBLICOS:
            return self.send_error(404, "Não encontrado")
        return super().do_HEAD()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/colaboradores":
            conn = banco.conectar()
            try:
                cursor = conn.cursor()
                nome_filtro = query.get("nome", [""])[0]
                if nome_filtro:
                    cursor.execute("SELECT id, nome, cargo, matricula FROM colaboradores WHERE nome LIKE ?",
                                   (f"%{nome_filtro}%",))
                else:
                    cursor.execute("SELECT id, nome, cargo, matricula FROM colaboradores")
                linhas = cursor.fetchall()
            finally:
                conn.close()
            return self._responder_json([{"id": l[0], "nome": l[1], "cargo": l[2], "matricula": l[3]}
                                         for l in linhas])

        elif path == "/api/equipamentos":
            conn = banco.conectar()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id, nome, tipo, quantidade, validade, situacao FROM equipamentos")
                linhas = cursor.fetchall()
            finally:
                conn.close()
            return self._responder_json([{"id": l[0], "nome": l[1], "tipo": l[2], "quantidade": l[3],
                                          "validade": l[4], "situacao": l[5]} for l in linhas])

        elif path == "/api/emprestimos":
            colaborador_id = query.get("colaborador_id", [""])[0]
            equipamento_id = query.get("equipamento_id", [""])[0]
            status = query.get("status", [""])[0]

            sql = """
                SELECT e.id, c.nome, eq.nome, e.data_emprestimo, e.data_prevista,
                       e.data_devolucao, e.status, e.observacao, e.colaborador_id, e.equipamento_id
                FROM emprestimos e
                JOIN colaboradores c ON e.colaborador_id = c.id
                JOIN equipamentos eq ON e.equipamento_id = eq.id
                WHERE 1=1
            """
            params = []
            if colaborador_id:
                sql += " AND e.colaborador_id = ?"
                params.append(colaborador_id)
            if equipamento_id:
                sql += " AND e.equipamento_id = ?"
                params.append(equipamento_id)
            if status:
                sql += " AND e.status = ?"
                params.append(status)

            conn = banco.conectar()
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                linhas = cursor.fetchall()
            finally:
                conn.close()
            return self._responder_json([{
                "id": l[0], "colaborador_nome": l[1], "equipamento_nome": l[2],
                "data_emprestimo": l[3], "data_prevista": l[4], "data_devolucao": l[5],
                "status": l[6], "observacao": l[7], "colaborador_id": l[8], "equipamento_id": l[9]
            } for l in linhas])

        if path.startswith("/api/"):
            return self._responder_json({"erro": "Rota não encontrada."}, status=404)

        # Arquivos estáticos: apenas a lista permitida
        if path not in ARQUIVOS_PUBLICOS:
            return self.send_error(404, "Não encontrado")
        return super().do_GET()

    def do_POST(self):
        path = self._caminho()
        dados = self._ler_json()
        if dados is None:
            return

        conn = banco.conectar()
        try:
            cursor = conn.cursor()

            if path == "/api/colaboradores":
                erro = validar_colaborador(dados, cursor)
                if erro:
                    return self._responder_json({"erro": erro}, status=400)
                cursor.execute("INSERT INTO colaboradores (nome, cargo, matricula) VALUES (?, ?, ?)",
                               (dados["nome"].strip(), dados["cargo"].strip(), str(dados["matricula"]).strip()))

            elif path == "/api/equipamentos":
                erro = validar_equipamento(dados, cursor)
                if erro:
                    return self._responder_json({"erro": erro}, status=400)
                cursor.execute("INSERT INTO equipamentos (nome, tipo, quantidade, validade, situacao) VALUES (?, ?, ?, ?, ?)",
                               (dados["nome"].strip(), dados["tipo"].strip(), dados["quantidade"],
                                dados["validade"], dados["situacao"]))

            elif path == "/api/emprestimos":
                erro = validar_novo_emprestimo(dados, cursor)
                if erro:
                    return self._responder_json({"erro": erro}, status=400)
                devolvido = dados["status"] == "Devolvido"
                cursor.execute("""
                    INSERT INTO emprestimos (colaborador_id, equipamento_id, data_emprestimo,
                                             data_prevista, data_devolucao, status, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (dados["colaborador_id"], dados["equipamento_id"], dados["data_emprestimo"],
                      dados["data_prevista"],
                      dados.get("data_devolucao") if devolvido else None,
                      dados["status"],
                      (dados.get("observacao") or None) if devolvido else None))

            else:
                return self._responder_json({"erro": "Rota não encontrada."}, status=404)

            conn.commit()
            return self._responder_json({"mensagem": "Cadastrado com sucesso!"}, status=201)
        except KeyError as e:
            return self._responder_json({"erro": f"Campo obrigatório ausente: {e.args[0]}"}, status=400)
        except sqlite3.IntegrityError as e:
            return self._responder_json({"erro": f"Violação de integridade no banco: {e}"}, status=400)
        except Exception as e:
            return self._responder_json({"erro": f"Erro interno: {e}"}, status=500)
        finally:
            conn.close()

    def do_PUT(self):
        path = self._caminho()
        dados = self._ler_json()
        if dados is None:
            return

        conn = banco.conectar()
        try:
            cursor = conn.cursor()

            if path == "/api/colaboradores":
                cursor.execute("SELECT 1 FROM colaboradores WHERE id = ?", (dados["id"],))
                if not cursor.fetchone():
                    return self._responder_json({"erro": "Colaborador não encontrado."}, status=404)
                erro = validar_colaborador(dados, cursor, item_id=dados["id"])
                if erro:
                    return self._responder_json({"erro": erro}, status=400)
                cursor.execute("UPDATE colaboradores SET nome=?, cargo=?, matricula=? WHERE id=?",
                               (dados["nome"].strip(), dados["cargo"].strip(),
                                str(dados["matricula"]).strip(), dados["id"]))

            elif path == "/api/equipamentos":
                cursor.execute("SELECT 1 FROM equipamentos WHERE id = ?", (dados["id"],))
                if not cursor.fetchone():
                    return self._responder_json({"erro": "Equipamento não encontrado."}, status=404)
                erro = validar_equipamento(dados, cursor, item_id=dados["id"])
                if erro:
                    return self._responder_json({"erro": erro}, status=400)
                cursor.execute("UPDATE equipamentos SET nome=?, tipo=?, quantidade=?, validade=?, situacao=? WHERE id=?",
                               (dados["nome"].strip(), dados["tipo"].strip(), dados["quantidade"],
                                dados["validade"], dados["situacao"], dados["id"]))

            elif path == "/api/emprestimos":
                erro, status_http = validar_atualizacao_emprestimo(dados, cursor)
                if erro:
                    return self._responder_json({"erro": erro}, status=status_http)
                devolvido = dados["status"] == "Devolvido"
                cursor.execute("UPDATE emprestimos SET status=?, data_devolucao=?, observacao=? WHERE id=?",
                               (dados["status"],
                                dados.get("data_devolucao") if devolvido else None,
                                dados.get("observacao") or None,
                                dados["id"]))

            else:
                return self._responder_json({"erro": "Rota não encontrada."}, status=404)

            conn.commit()
            return self._responder_json({"mensagem": "Atualizado com sucesso!"})
        except KeyError as e:
            return self._responder_json({"erro": f"Campo obrigatório ausente: {e.args[0]}"}, status=400)
        except sqlite3.IntegrityError as e:
            return self._responder_json({"erro": f"Violação de integridade no banco: {e}"}, status=400)
        except Exception as e:
            return self._responder_json({"erro": f"Erro interno: {e}"}, status=500)
        finally:
            conn.close()

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_url.query)

        try:
            item_id = int(query.get("id", [""])[0])
        except ValueError:
            return self._responder_json({"erro": "ID ausente ou inválido."}, status=400)

        path = parsed_url.path
        conn = banco.conectar()
        try:
            cursor = conn.cursor()

            if path == "/api/colaboradores":
                cursor.execute("SELECT COUNT(*) FROM emprestimos WHERE colaborador_id = ?", (item_id,))
                total = cursor.fetchone()[0]
                if total:
                    return self._responder_json({
                        "erro": f"Não é possível excluir: o colaborador possui {total} empréstimo(s) "
                                f"registrado(s). Exclua os empréstimos antes, se realmente desejar."
                    }, status=400)
                cursor.execute("DELETE FROM colaboradores WHERE id=?", (item_id,))

            elif path == "/api/equipamentos":
                cursor.execute("SELECT COUNT(*) FROM emprestimos WHERE equipamento_id = ?", (item_id,))
                total = cursor.fetchone()[0]
                if total:
                    return self._responder_json({
                        "erro": f"Não é possível excluir: o EPI possui {total} empréstimo(s) "
                                f"registrado(s). Exclua os empréstimos antes, se realmente desejar."
                    }, status=400)
                cursor.execute("DELETE FROM equipamentos WHERE id=?", (item_id,))

            elif path == "/api/emprestimos":
                cursor.execute("DELETE FROM emprestimos WHERE id=?", (item_id,))

            else:
                return self._responder_json({"erro": "Rota não encontrada."}, status=404)

            if cursor.rowcount == 0:
                return self._responder_json({"erro": "Registro não encontrado."}, status=404)

            conn.commit()
            return self._responder_json({"mensagem": "Excluído com sucesso!"})
        except sqlite3.IntegrityError as e:
            return self._responder_json({"erro": f"Violação de integridade no banco: {e}"}, status=400)
        except Exception as e:
            return self._responder_json({"erro": f"Erro interno: {e}"}, status=500)
        finally:
            conn.close()


class ServidorThreaded(socketserver.ThreadingTCPServer):
    allow_reuse_address = True   # evita "Address already in use" ao reiniciar rápido
    daemon_threads = True        # atende várias requisições ao mesmo tempo


if __name__ == "__main__":
    banco.inicializar_banco()
    with ServidorThreaded(("", PORT), RequisicaoHandler) as httpd:
        print(f"Servidor rodando em: http://localhost:{PORT}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")
