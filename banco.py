import os
import shutil
import sqlite3

# Pasta do projeto (onde este arquivo está), independente de onde o script é executado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# O banco fica em uma PASTA ("dados"), que é a que o Docker mapeia como volume.
# Assim o arquivo de journal do SQLite também fica persistido no host.
PASTA_DADOS = os.path.join(BASE_DIR, "dados")
NOME_BANCO = os.path.join(PASTA_DADOS, "controle_epi.db")

# Caminho do banco antigo (versões anteriores guardavam o arquivo na raiz do projeto)
BANCO_LEGADO = os.path.join(BASE_DIR, "controle_epi.db")


def conectar():
    """Conecta ao banco SQLite e ativa a verificação de Chaves Estrangeiras (FK)."""
    os.makedirs(PASTA_DADOS, exist_ok=True)
    conn = sqlite3.connect(NOME_BANCO)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _migrar_banco_legado():
    """Se existir um banco na raiz (versão antiga) e ainda não houver um em dados/, copia-o."""
    os.makedirs(PASTA_DADOS, exist_ok=True)
    if (os.path.isfile(BANCO_LEGADO)
            and os.path.getsize(BANCO_LEGADO) > 0
            and not os.path.exists(NOME_BANCO)):
        shutil.copy2(BANCO_LEGADO, NOME_BANCO)
        print(f"Banco antigo copiado para {NOME_BANCO}")


def inicializar_banco():
    """Cria as tabelas relacionais do sistema caso não existam."""
    _migrar_banco_legado()
    conn = conectar()
    cursor = conn.cursor()

    # Tabela de Colaboradores
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS colaboradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cargo TEXT NOT NULL,
        matricula TEXT NOT NULL
    );
    """)

    # Tabela de Equipamentos (EPIs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        tipo TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        validade TEXT NOT NULL,
        situacao TEXT NOT NULL
    );
    """)

    # Tabela de Empréstimos
    # ON DELETE RESTRICT: não permite apagar colaborador/EPI que tenha histórico,
    # evitando perda silenciosa de registros (antes era CASCADE).
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emprestimos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colaborador_id INTEGER NOT NULL,
        equipamento_id INTEGER NOT NULL,
        data_emprestimo TEXT NOT NULL,
        data_prevista TEXT NOT NULL,
        data_devolucao TEXT,
        status TEXT NOT NULL,
        observacao TEXT,
        FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id) ON DELETE RESTRICT,
        FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id) ON DELETE RESTRICT
    );
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    inicializar_banco()
    print("Banco de dados inicializado com sucesso!")
