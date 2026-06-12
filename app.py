from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from conexao import conectar

app = Flask(__name__)
app.secret_key = "chave_secreta"


# --------------------------
# Helpers
# --------------------------
def get_usuario_session():
    return session.get("usuario")


def require_login():
    if not get_usuario_session():
        return redirect(url_for("login"))


def is_tipo(tipo):
    u = get_usuario_session()
    return u and u.get("tipo") == tipo


# =====================================================================
# 🔐 LOGIN
# =====================================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("usuario"):
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "").strip()

        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT id, nome, email, tipo 
                FROM usuarios 
                WHERE email = %s AND senha = %s
            """, (email, senha))
            usuario = cursor.fetchone()
        finally:
            cursor.close()
            conexao.close()

        if not usuario:
            flash("E-mail ou senha incorretos!", "erro")
            return redirect(url_for("login"))

        # Salva dados essenciais na sessão
        session["usuario"] = {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
            "tipo": usuario["tipo"]
        }
        return redirect(url_for("home"))

    return render_template("login.html")


# =====================================================================
# 🔑 HOME — REDIRECIONA PELO TIPO
# =====================================================================
@app.route("/home")
def home():
    usuario = session.get("usuario")

    if not usuario:
        return redirect(url_for("login"))

    tipo = usuario.get("tipo")
    if tipo == "admin":
        return redirect(url_for("admin_dashboard"))
    elif tipo == "professor":
        return redirect(url_for("professor_inicial"))

    # Se o tipo for inválido, limpa sessão e volta pro login
    session.pop("usuario", None)
    flash("Acesso não autorizado.", "erro")
    return redirect(url_for("login"))




# =====================================================================
# 🧾 REGISTRO DE USUÁRIO
# =====================================================================
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "").strip()
        tipo = request.form.get("tipo", "aluno")

        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM usuarios WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("E-mail já cadastrado!", "erro")
                return redirect(url_for("registrar"))

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, tipo)
                VALUES (%s, %s, %s, %s)
            """, (nome, email, senha, tipo))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

        flash("Cadastro realizado!", "sucesso")
        return redirect(url_for("login"))

    return render_template("registrar.html")


# =====================================================================
# 🧑‍💼 ADMIN — DASHBOARD
# =====================================================================
@app.route("/admin")
def admin_dashboard():
    if not session.get("usuario") or session["usuario"]["tipo"] != "admin":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM alunos")
        total_alunos = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM professores")
        total_professores = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM usuarios WHERE tipo='admin'")
        total_admins = cursor.fetchone()["total"]

        cursor.execute("SELECT AVG(nota) AS media FROM notas")
        media_geral = cursor.fetchone()["media"]
    finally:
        cursor.close()
        conexao.close()

    return render_template(
        "admin.html",
        view="dashboard",
        resumo={
            "total_alunos": total_alunos,
            "total_professores": total_professores,
            "total_admins": total_admins,
            "media_geral": media_geral if media_geral is not None else "—"
        }
    )


# =====================================================================
# CRUD — PROFESSORES
# =====================================================================
@app.route("/admin/professores")
def listar_professores():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        # Juntamos com usuarios para exibir nome/email do usuário do professor
        cursor.execute("""
            SELECT p.id, p.usuario_id, p.disciplina, u.nome AS nome, u.email AS email
            FROM professores p
            LEFT JOIN usuarios u ON p.usuario_id = u.id
        """)
        professores = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="professores", professores=professores)


@app.route("/admin/professores/add", methods=["GET", "POST"])
def add_professor():
    if request.method == "POST":
        # Aceita duas formas:
        # 1) usuário já existente (campo usuario_id ou email)
        # 2) criar usuário novo (nome, email)
        usuario_id = request.form.get("usuario_id")  # se o form já fornecer id
        nome = request.form.get("nome")
        email = request.form.get("email")
        disciplina = request.form.get("disciplina")

        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        try:
            # Se fornecer usuario_id e for válido, usamos ele
            if usuario_id:
                cursor.execute("SELECT id FROM usuarios WHERE id=%s", (usuario_id,))
                if not cursor.fetchone():
                    flash("Usuário informado não existe.", "erro")
                    return redirect(url_for("add_professor"))
                uid = int(usuario_id)
            else:
                # se fornecer email, tenta reutilizar usuário existente
                if email:
                    cursor.execute("SELECT id FROM usuarios WHERE email=%s", (email.strip().lower(),))
                    u = cursor.fetchone()
                    if u:
                        uid = u["id"]
                    else:
                        # criar novo usuário com tipo professor e senha padrao '123'
                        cursor.execute("INSERT INTO usuarios (nome, email, senha, tipo) VALUES (%s,%s,%s,%s)",
                                       (nome, email.strip().lower(), "123", "professor"))
                        conexao.commit()
                        uid = cursor.lastrowid
                else:
                    flash("Informe email ou usuario_id para o professor.", "erro")
                    return redirect(url_for("add_professor"))

            # Criar a linha em professores
            cursor.execute("INSERT INTO professores (usuario_id, disciplina) VALUES (%s, %s)", (uid, disciplina))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

        flash("Professor adicionado!", "sucesso")
        return redirect(url_for("listar_professores"))

    # GET -> exibir form (poderia precisar de lista de usuarios livres)
    return render_template("admin.html", view="professores_add")


@app.route("/admin/professores/edit/<int:id>", methods=["GET", "POST"])
def edit_professor(id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        disciplina = request.form.get("disciplina")
        nome = request.form.get("nome")
        email = request.form.get("email")
        turmas_escolhidas = request.form.getlist("turmas")  # Lista de IDs
        turmas_escolhidas = [int(t) for t in turmas_escolhidas]

        # 1️⃣ Atualiza disciplina do professor
        cursor.execute(
            "UPDATE professores SET disciplina=%s WHERE id=%s",
            (disciplina, id)
        )

        # 2️⃣ Atualiza nome/email do usuário do professor
        cursor.execute("SELECT usuario_id FROM professores WHERE id=%s", (id,))
        usuario_id = cursor.fetchone()["usuario_id"]
        cursor.execute(
            "UPDATE usuarios SET nome=%s, email=%s WHERE id=%s",
            (nome, email, usuario_id)
        )

        # 3️⃣ Busca turmas atuais do professor na tabela N:N
        cursor.execute("SELECT turma_id FROM professor_turma WHERE professor_id=%s", (id,))
        turmas_atual = {row["turma_id"] for row in cursor.fetchall()}

        # 4️⃣ Calcula turmas a remover e a adicionar
        remover = turmas_atual - set(turmas_escolhidas)
        adicionar = set(turmas_escolhidas) - turmas_atual

        # 5️⃣ Remove professor das turmas desmarcadas
        if remover:
            placeholders = ",".join(["%s"]*len(remover))
            cursor.execute(
                f"DELETE FROM professor_turma WHERE professor_id=%s AND turma_id IN ({placeholders})",
                [id] + list(remover)
            )

        # 6️⃣ Adiciona professor nas novas turmas
        if adicionar:
            for turma_id in adicionar:
                cursor.execute(
                    "INSERT INTO professor_turma (professor_id, turma_id) VALUES (%s, %s)",
                    (id, turma_id)
                )

        conn.commit()
        cursor.close()
        conn.close()
        flash("Professor atualizado!", "sucesso")
        return redirect(url_for("listar_professores"))

    # GET → busca dados do professor
    cursor.execute("""
        SELECT p.id, p.usuario_id, p.disciplina, u.nome, u.email
        FROM professores p
        JOIN usuarios u ON u.id = p.usuario_id
        WHERE p.id = %s
    """, (id,))
    item = cursor.fetchone()

    # Busca todas as turmas
    cursor.execute("SELECT id, nome FROM turmas")
    turmas = cursor.fetchall()

    # Busca turmas do professor na tabela N:N
    cursor.execute("SELECT turma_id FROM professor_turma WHERE professor_id=%s", (id,))
    turmas_do_prof = [row["turma_id"] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        view="professores_edit",
        item=item,
        turmas=turmas,
        turmas_do_prof=turmas_do_prof
    )





@app.route("/admin/professores/delete/<int:id>", methods=["POST"])
def delete_professor(id):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        # Ao deletar professor, deixamos usuário intacto (ou poderia deletar usuário também)
        cursor.execute("DELETE FROM professores WHERE id=%s", (id,))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()
    flash("Professor removido!", "sucesso")
    return redirect(url_for("listar_professores"))


# =====================================================================
# CRUD — ALUNOS
# =====================================================================
@app.route("/admin/alunos")
def listar_alunos():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.id, a.usuario_id, a.turma_id, a.serie, u.nome AS nome, u.email AS email, t.nome AS turma
            FROM alunos a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            LEFT JOIN turmas t ON a.turma_id = t.id
        """)
        alunos = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="alunos", alunos=alunos)


@app.route("/admin/alunos/add", methods=["GET", "POST"])
def add_aluno():
    if request.method == "POST":
        usuario_id = request.form.get("usuario_id")  # se você estiver selecionando um usuário existente
        nome = request.form.get("nome")              # se for criar um novo usuário
        email = request.form.get("email")
        turma_id = request.form.get("turma_id")      # turma selecionada no form

        if not turma_id:
            flash("Selecione uma turma.", "erro")
            return redirect(url_for("add_aluno"))

        conexao = conectar()
        cursor = conexao.cursor()

        # Se usuário não existe, cria
        if not usuario_id:
            cursor.execute(
                "INSERT INTO usuarios (nome, email,senha) VALUES (%s, %s, %s)",
                (nome, email, "123")
            )
            usuario_id = cursor.lastrowid

        # Cria o aluno com a turma selecionada
        cursor.execute(
            "INSERT INTO alunos (usuario_id, turma_id) VALUES (%s, %s)",
            (usuario_id, turma_id)
        )

        conexao.commit()
        cursor.close()
        conexao.close()

        flash("Aluno cadastrado com sucesso!", "sucesso")
        return redirect(url_for("add_aluno"))

    # GET → exibe o formulário
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    
    # Buscar usuários que ainda não são alunos (opcional)
    cursor.execute("""
        SELECT id, nome FROM usuarios 
        WHERE id NOT IN (SELECT usuario_id FROM alunos)
    """)
    usuarios = cursor.fetchall()

    # Buscar todas as turmas
    cursor.execute("SELECT id, nome FROM turmas")
    turmas = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template("admin.html", view="alunos_add", usuarios=usuarios, turmas=turmas)


@app.route("/aluno/editar/<int:id>", methods=["GET", "POST"])
def edit_aluno(id):
    conn = conectar()
    cursor = conn.cursor(dictionary=True)

    # Buscar dados do aluno junto com usuário
    cursor.execute("""
        SELECT
            alunos.id,
            alunos.serie,
            alunos.turma_id,
            usuarios.id AS usuario_id,
            usuarios.nome AS usuario_nome,
            usuarios.email AS usuario_email
        FROM alunos
        JOIN usuarios ON usuarios.id = alunos.usuario_id
        WHERE alunos.id = %s
    """, (id,))
    
    aluno = cursor.fetchone()

    if not aluno:
        flash("Aluno não encontrado!", "error")
        return redirect(url_for("listar_alunos"))

    # POST → atualizar
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        serie = request.form["serie"]
        turma_id = request.form["turma_id"] or None

        try:
            # Atualizar usuários
            cursor.execute("""
                UPDATE usuarios
                SET nome = %s, email = %s
                WHERE id = %s
            """, (nome, email, aluno["usuario_id"]))

            # Atualizar alunos
            cursor.execute("""
                UPDATE alunos
                SET serie = %s, turma_id = %s
                WHERE id = %s
            """, (serie, turma_id, id))

            conn.commit()
            flash("Aluno atualizado com sucesso!", "success")
            return redirect(url_for("listar_alunos"))

        except mysql.connector.Error as err:
            conn.rollback()

            if err.errno == 1062:
                flash("Este e-mail já está em uso!", "error")
            else:
                flash(f"Erro ao atualizar: {err}", "error")

            return redirect(url_for("edit_aluno", id=id))

    # GET → carregar turmas
    cursor.execute("SELECT * FROM turmas")
    turmas = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        view="alunos_edit",
        item=aluno,
        turmas=turmas
    )


@app.route("/admin/alunos/delete/<int:id>", methods=["POST"])
def delete_aluno(id):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        # Deleta apenas o registro de aluno. Usuário fica (pode ser deletado separadamente).
        cursor.execute("DELETE FROM alunos WHERE id=%s", (id,))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()
    flash("Aluno removido!", "sucesso")
    return redirect(url_for("listar_alunos"))


# =====================================================================
# CRUD — MATERIAIS
# =====================================================================
@app.route("/admin/materiais")
def listar_materiais():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT m.*, p.usuario_id AS professor_usuario_id, u.nome AS professor_nome
            FROM materiais m
            LEFT JOIN professores p ON m.professor_id = p.id
            LEFT JOIN usuarios u ON p.usuario_id = u.id
        """)
        materiais = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="materiais", materiais=materiais)


@app.route("/admin/materiais/add", methods=["GET", "POST"])
def add_material():
    if request.method == "POST":
        titulo = request.form.get("titulo")
        descricao = request.form.get("descricao")
        link = request.form.get("link")
        professor_id = request.form.get("professor_id")  # preferível

        conexao = conectar()
        cursor = conexao.cursor()
        try:
            # Se professor_id não vier, tente encontrar por email do professor no form (compatibilidade)
            if not professor_id:
                prof_email = request.form.get("professor_email")
                if prof_email:
                    cursor.execute("SELECT p.id FROM professores p JOIN usuarios u ON p.usuario_id = u.id WHERE u.email = %s", (prof_email.strip().lower(),))
                    r = cursor.fetchone()
                    if r:
                        professor_id = r[0]
            if not professor_id:
                flash("Professor precisa ser informado.", "erro")
                return redirect(url_for("add_material"))

            cursor.execute("""
                INSERT INTO materiais (titulo, descricao, link, professor_id)
                VALUES (%s, %s, %s, %s)
            """, (titulo, descricao, link, professor_id))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

        flash("Material cadastrado!", "sucesso")
        return redirect(url_for("listar_materiais"))

    return render_template("admin.html", view="materiais_add")


@app.route("/admin/materiais/edit/<int:id>", methods=["GET", "POST"])
def edit_material(id):
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        if request.method == "POST":
            titulo = request.form.get("titulo")
            descricao = request.form.get("descricao")
            link = request.form.get("link")
            professor_id = request.form.get("professor_id")

            cursor.execute("UPDATE materiais SET titulo=%s, descricao=%s, link=%s, professor_id=%s WHERE id=%s",
                           (titulo, descricao, link, professor_id, id))
            conexao.commit()
            flash("Material atualizado!", "sucesso")
            return redirect(url_for("listar_materiais"))

        cursor.execute("SELECT * FROM materiais WHERE id=%s", (id,))
        item = cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="materiais_edit", item=item)


@app.route("/admin/materiais/delete/<int:id>", methods=["POST"])
def delete_material(id):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM materiais WHERE id=%s", (id,))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()
    flash("Material removido!", "sucesso")
    return redirect(url_for("listar_materiais"))


# =====================================================================
# CRUD — NOTAS
# =====================================================================
@app.route("/admin/notas")
def listar_notas():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT n.id, n.nota, n.aluno_id, n.materia_id, n.professor_id,
                   u.nome AS aluno_nome, m.nome AS materia_nome, up.nome AS professor_nome
            FROM notas n
            LEFT JOIN alunos a ON n.aluno_id = a.id
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            LEFT JOIN materias m ON n.materia_id = m.id
            LEFT JOIN professores p ON n.professor_id = p.id
            LEFT JOIN usuarios up ON p.usuario_id = up.id
        """)
        notas = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="notas", notas=notas)


@app.route("/admin/notas/add", methods=["GET", "POST"])
def add_nota():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        # lista alunos e materias para o select no template
        cursor.execute("SELECT a.id, u.nome FROM alunos a JOIN usuarios u ON a.usuario_id = u.id")
        alunos = cursor.fetchall()
        cursor.execute("SELECT * FROM materias")
        materias = cursor.fetchall()
        cursor.execute("""
            SELECT p.id, u.nome FROM professores p JOIN usuarios u ON p.usuario_id = u.id
        """)
        professores = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()

    if request.method == "POST":
        # Aceitamos tanto os campos normalizados quanto os antigos:
        aluno_id = request.form.get("aluno_id") or request.form.get("aluno")  # aluno pode vir como nome/id
        materia_id = request.form.get("materia_id") or request.form.get("disciplina")
        professor_id = request.form.get("professor_id")
        nota = request.form.get("nota")

        # validações básicas
        if not aluno_id or not materia_id or nota is None:
            flash("Aluno, matéria e nota são obrigatórios.", "erro")
            return redirect(url_for("add_nota"))

        # Se forem nomes (strings) tente mapear para ids
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        try:
            # resolve aluno_id se for nome
            if not str(aluno_id).isdigit():
                cursor.execute("SELECT a.id FROM alunos a JOIN usuarios u ON a.usuario_id = u.id WHERE u.nome = %s", (aluno_id,))
                row = cursor.fetchone()
                if not row:
                    flash("Aluno não encontrado.", "erro")
                    return redirect(url_for("add_nota"))
                aluno_id = row["id"]
            # resolve materia_id se for nome
            if not str(materia_id).isdigit():
                cursor.execute("SELECT id FROM materias WHERE nome = %s", (materia_id,))
                row = cursor.fetchone()
                if not row:
                    flash("Matéria não encontrada.", "erro")
                    return redirect(url_for("add_nota"))
                materia_id = row["id"]

            # se professor_id vier por email ou nome, tente resolver
            if professor_id and not str(professor_id).isdigit():
                cursor.execute("SELECT p.id FROM professores p JOIN usuarios u ON p.usuario_id = u.id WHERE u.email = %s OR u.nome = %s",
                               (professor_id, professor_id))
                r = cursor.fetchone()
                if r:
                    professor_id = r["id"]
                else:
                    professor_id = None

            # checar se existe nota já
            cursor.execute("SELECT id FROM notas WHERE aluno_id = %s AND materia_id = %s", (aluno_id, materia_id))
            existe = cursor.fetchone()
            if existe:
                cursor.execute("UPDATE notas SET nota=%s, professor_id=%s WHERE id=%s", (nota, professor_id, existe["id"]))
            else:
                cursor.execute("INSERT INTO notas (aluno_id, materia_id, professor_id, nota) VALUES (%s,%s,%s,%s)",
                               (aluno_id, materia_id, professor_id, nota))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

        flash("Nota registrada!", "sucesso")
        return redirect(url_for("listar_notas"))

    return render_template("admin.html", view="notas_add", alunos=alunos, materias=materias, professores=professores)


@app.route("/admin/notas/edit/<int:id>", methods=["GET", "POST"])
def edit_nota(id):
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        # pegar listas auxiliares
        cursor.execute("SELECT a.id, u.nome FROM alunos a JOIN usuarios u ON a.usuario_id = u.id")
        alunos = cursor.fetchall()
        cursor.execute("SELECT * FROM materias")
        materias = cursor.fetchall()
        cursor.execute("SELECT p.id, u.nome FROM professores p JOIN usuarios u ON p.usuario_id = u.id")
        professores = cursor.fetchall()

        if request.method == "POST":
            aluno_id = request.form.get("aluno_id")
            materia_id = request.form.get("materia_id")
            professor_id = request.form.get("professor_id")
            nota = request.form.get("nota")

            cursor.execute("UPDATE notas SET aluno_id=%s, materia_id=%s, professor_id=%s, nota=%s WHERE id=%s",
                           (aluno_id, materia_id, professor_id, nota, id))
            conexao.commit()
            flash("Nota atualizada!", "sucesso")
            return redirect(url_for("listar_notas"))

        cursor.execute("SELECT * FROM notas WHERE id=%s", (id,))
        item = cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()

    return render_template("admin.html", view="notas_edit", item=item, alunos=alunos, materias=materias, professores=professores)


@app.route("/admin/notas/delete/<int:id>", methods=["POST"])
def delete_nota(id):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM notas WHERE id=%s", (id,))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()
    flash("Nota removida!", "sucesso")
    return redirect(url_for("listar_notas"))


# =====================================================================
# CRUD — ADMINISTRADORES (usuarios tipo admin)
# =====================================================================
@app.route("/admin/admins")
def listar_admins():
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM usuarios WHERE tipo='admin'")
        admins = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="admins", admins=admins)


@app.route("/admin/admins/add", methods=["GET", "POST"])
def add_admin():
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")

        conexao = conectar()
        cursor = conexao.cursor()
        try:
            cursor.execute("INSERT INTO usuarios (nome, email, senha, tipo) VALUES (%s, %s, %s, %s)",
                           (nome, email.strip().lower(), "123", "admin"))
            conexao.commit()
        finally:
            cursor.close()
            conexao.close()

        flash("Administrador criado!", "sucesso")
        return redirect(url_for("listar_admins"))

    return render_template("admin.html", view="admins_add")


@app.route("/admin/admins/edit/<int:id>", methods=["GET", "POST"])
def edit_admin(id):
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        if request.method == "POST":
            nome = request.form.get("nome")
            email = request.form.get("email")
            cursor.execute("UPDATE usuarios SET nome=%s, email=%s WHERE id=%s", (nome, email.strip().lower(), id))
            conexao.commit()
            flash("Administrador atualizado!", "sucesso")
            return redirect(url_for("listar_admins"))

        cursor.execute("SELECT * FROM usuarios WHERE id=%s", (id,))
        item = cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()
    return render_template("admin.html", view="admins_edit", item=item)


@app.route("/admin/admins/delete/<int:id>", methods=["POST"])
def delete_admin(id):
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("DELETE FROM usuarios WHERE id=%s", (id,))
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()
    flash("Administrador removido!", "sucesso")
    return redirect(url_for("listar_admins"))


# =====================================================================
# PERFIL DO ADMIN
# =====================================================================
@app.route("/admin/perfil", methods=["GET", "POST"])
def perfil():
    usuario = session.get("usuario")
    if not usuario or usuario["tipo"] != "admin":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        if request.method == "POST":
            nome = request.form.get("nome")
            email = request.form.get("email")
            senha = request.form.get("senha", None)

            if senha:
                cursor.execute("UPDATE usuarios SET nome=%s, email=%s, senha=%s WHERE id=%s",
                               (nome, email.strip().lower(), senha, usuario["id"]))
            else:
                cursor.execute("UPDATE usuarios SET nome=%s, email=%s WHERE id=%s",
                               (nome, email.strip().lower(), usuario["id"]))
            conexao.commit()

            # Atualiza session
            session["usuario"]["nome"] = nome
            session["usuario"]["email"] = email.strip().lower()
            flash("Perfil atualizado!", "sucesso")
            return redirect(url_for("perfil"))

        cursor.execute("SELECT * FROM usuarios WHERE id=%s", (usuario["id"],))
        admin = cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()

    return render_template("admin.html", view="perfil", admin=admin)


# -------------------------------------------------------
# 👨‍🏫 PROFESSOR - DASHBOARD & PÁGINA COMPLETA
# -------------------------------------------------------
@app.route("/professor")
def professor_home():
    if not session.get("usuario"):
        return redirect(url_for("login"))
    usuario = session["usuario"]
    if usuario["tipo"] != "professor":
        flash("Acesso negado!", "erro")
        return redirect(url_for("login"))
    return render_template("professor.html")


@app.route("/professor_inicial")
def professor_inicial(view="dashboard"):
    if not session.get("usuario"):
        return redirect(url_for("login"))

    usuario = session["usuario"]
    if usuario["tipo"] != "professor":
        flash("Acesso negado!", "erro")
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    try:
        # Buscar ID interno do professor
        cursor.execute("SELECT id FROM professores WHERE usuario_id = %s", (usuario["id"],))
        prof = cursor.fetchone()
        if not prof:
            flash("Professor não encontrado.", "erro")
            return redirect(url_for("professor_home"))
        professor_id = prof["id"]

        # Buscar alunos das turmas que o professor leciona (JOIN na tabela N:N)
        cursor.execute("""
            SELECT 
                a.id AS aluno_id,
                u.nome AS aluno,
                t.nome AS turma,
                IFNULL(AVG(n.nota), 0) AS media
            FROM alunos a
            JOIN usuarios u ON a.usuario_id = u.id
            JOIN turmas t ON a.turma_id = t.id
            JOIN professor_turma pt ON pt.turma_id = t.id
            LEFT JOIN notas n ON a.id = n.aluno_id AND n.professor_id = %s
            WHERE pt.professor_id = %s
            GROUP BY a.id, u.nome, t.nome
        """, (professor_id, professor_id))
        alunos = cursor.fetchall()

        # Buscar notas completas do professor
        cursor.execute("""
            SELECT 
                n.id AS nota_id,
                a.id AS aluno_id,
                u.nome AS aluno,
                m.nome AS materia,
                n.nota,
                t.nome AS turma
            FROM notas n
            JOIN alunos a ON n.aluno_id = a.id
            JOIN usuarios u ON a.usuario_id = u.id
            JOIN materias m ON n.materia_id = m.id
            JOIN turmas t ON a.turma_id = t.id
            JOIN professor_turma pt ON pt.turma_id = t.id
            WHERE n.professor_id = %s AND pt.professor_id = %s
            ORDER BY u.nome, m.nome
        """, (professor_id, professor_id))
        notas = cursor.fetchall()

        # Buscar matérias
        cursor.execute("SELECT * FROM materias")
        materias = cursor.fetchall()

        # Buscar materiais do professor
        cursor.execute("SELECT * FROM materiais WHERE professor_id = %s", (professor_id,))
        materiais = cursor.fetchall()

    finally:
        cursor.close()
        conexao.close()

    resumo = {
        "total_turmas": len(alunos) if alunos else 0,  # agora total de turmas = quantidade de alunos únicos pode ser ajustado
        "total_alunos": len(alunos) if alunos else 0,
        "total_materiais": len(materiais) if materiais else 0,
        "total_notas": len(notas) if notas else 0
    }

    return render_template(
        "professor.html",
        professor=professor_id,
        usuario=usuario,
        alunos=alunos,
        materias=materias,
        view=view,
        resumo=resumo,
        materiais=materiais
    )



# -------------------------------------------------------
# ✏️ LANÇAR / EDITAR NOTAS (professor)
# -------------------------------------------------------

# Abrir formulário de lançamento de notas
@app.route("/professor/notas/add", methods=["GET"])
def prof_add_nota():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    # Buscar o professor logado
    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (session["usuario"]["id"],))
    prof = cursor.fetchone()
    if not prof:
        flash("Professor não encontrado.", "erro")
        return redirect(url_for("professor_dashboard"))
    professor_id = prof["id"]

    # Buscar turmas desse professor (N:N)
    cursor.execute("""
        SELECT t.id, t.nome
        FROM turmas t
        JOIN professor_turma pt ON pt.turma_id = t.id
        WHERE pt.professor_id = %s
    """, (professor_id,))
    turmas = cursor.fetchall()

    # Buscar todas as matérias
    cursor.execute("SELECT id, nome FROM materias")
    materias = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template("professor.html", view="notas_add", turmas=turmas, materias=materias)


@app.route("/professor/nota", methods=["POST"])
def registrar_nota_professor():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    usuario = session["usuario"]
    aluno_id = request.form.get("aluno_id")
    materia_id = request.form.get("materia_id")
    nota = request.form.get("nota")

    if not aluno_id or not materia_id or nota is None:
        flash("Aluno, matéria e nota são obrigatórios.", "erro")
        return redirect(url_for("prof_add_nota"))

    conexao = conectar()
    cursor = conexao.cursor()

    # Buscar professor
    cursor.execute("SELECT id FROM professores WHERE usuario_id = %s", (usuario["id"],))
    professor = cursor.fetchone()
    if not professor:
        flash("Professor não encontrado.", "erro")
        return redirect(url_for("prof_add_nota"))
    professor_id = professor[0]

    # Verificar se o aluno pertence a alguma turma do professor
    cursor.execute("""
        SELECT 1
        FROM alunos a
        JOIN turmas t ON t.id = a.turma_id
        JOIN professor_turma pt ON pt.turma_id = t.id
        WHERE a.id = %s AND pt.professor_id = %s
    """, (aluno_id, professor_id))
    pertence = cursor.fetchone()
    if not pertence:
        flash("Aluno não pertence a nenhuma turma sua.", "erro")
        return redirect(url_for("prof_add_nota"))

    # Verificar se nota já existe
    cursor.execute("SELECT id FROM notas WHERE aluno_id=%s AND materia_id=%s", (aluno_id, materia_id))
    existe = cursor.fetchone()

    if existe:
        cursor.execute(
            "UPDATE notas SET nota=%s, professor_id=%s WHERE aluno_id=%s AND materia_id=%s",
            (nota, professor_id, aluno_id, materia_id)
        )
        flash("Nota atualizada com sucesso!", "sucesso")
    else:
        cursor.execute(
            "INSERT INTO notas (aluno_id, materia_id, professor_id, nota) VALUES (%s, %s, %s, %s)",
            (aluno_id, materia_id, professor_id, nota)
        )
        flash("Nota lançada com sucesso!", "sucesso")

    conexao.commit()
    cursor.close()
    conexao.close()

    return redirect(url_for("prof_notas"))



# Editar nota
@app.route("/professor/notas/edit/<int:id>", methods=["GET", "POST"])
def prof_edit_nota(id):
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    # achar professor
    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (session["usuario"]["id"],))
    prof = cursor.fetchone()

    if not prof:
        flash("Professor não encontrado.", "erro")
        return redirect(url_for("prof_notas"))

    professor_id = prof["id"]

    if request.method == "GET":
        cursor.execute("""
            SELECT 
                n.id,
                n.nota,
                u.nome AS aluno,
                m.nome AS disciplina
            FROM notas n
            JOIN alunos a ON n.aluno_id = a.id
            JOIN usuarios u ON a.usuario_id = u.id
            JOIN materias m ON n.materia_id = m.id
            WHERE n.id=%s AND n.professor_id=%s
        """, (id, professor_id))

        nota = cursor.fetchone()

        if not nota:
            cursor.close()
            conexao.close()
            flash("Nota não encontrada.", "erro")
            return redirect(url_for("prof_notas"))

        cursor.close()
        conexao.close()

        return render_template("professor.html", view="notas_edit", nota=nota)

    # POST → atualizar a nota
    nova_nota = request.form.get("nota")

    cursor.execute("""
        UPDATE notas SET nota=%s 
        WHERE id=%s AND professor_id=%s
    """, (nova_nota, id, professor_id))

    conexao.commit()
    cursor.close()
    conexao.close()

    flash("Nota atualizada com sucesso!", "sucesso")
    return redirect(url_for("prof_notas"))

@app.route("/professor/alunos_por_turma")
def alunos_por_turma():
    turma_id = request.args.get("turma_id")

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            a.id AS id,
            u.nome AS nome
        FROM alunos a
        JOIN usuarios u ON a.usuario_id = u.id
        WHERE a.turma_id = %s
    """, (turma_id,))

    alunos = cursor.fetchall()

    cursor.close()
    conexao.close()

    return jsonify(alunos)


# Excluir nota
@app.route("/professor/notas/delete/<int:id>", methods=["POST"])
def prof_delete_nota(id):
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM notas WHERE id=%s", (id,))
    conexao.commit()
    cursor.close()
    conexao.close()
    flash("Nota removida com sucesso!", "sucesso")
    return redirect(url_for("prof_notas"))


# -------------------------------------------------------
# 📚 MATERIAL DIDÁTICO (professor)
# -------------------------------------------------------
@app.route("/professor/materiais/add", methods=["GET", "POST"])
def prof_add_material():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    usuario = session["usuario"]
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (usuario["id"],))
    prof = cursor.fetchone()
    professor_id = prof["id"]

    if request.method == "POST":
        titulo = request.form.get("titulo")
        descricao = request.form.get("descricao")
        link = request.form.get("link")

        cursor.execute(
            "INSERT INTO materiais (titulo, descricao, link, professor_id) VALUES (%s, %s, %s, %s)",
            (titulo, descricao, link, professor_id)
        )
        conexao.commit()
        cursor.close()
        conexao.close()
        flash("Material adicionado com sucesso!", "sucesso")
        return redirect(url_for("prof_materiais"))

    cursor.close()
    conexao.close()
    return render_template("professor.html", view="materiais_add")

# Editar material
@app.route("/professor/materiais/edit/<int:id>", methods=["GET", "POST"])
def prof_edit_material(id):
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (session["usuario"]["id"],))
    prof = cursor.fetchone()
    professor_id = prof["id"]

    if request.method == "GET":
        cursor.execute("SELECT * FROM materiais WHERE id=%s AND professor_id=%s", (id, professor_id))
        material = cursor.fetchone()
        cursor.close()
        conexao.close()
        return render_template("professor.html", view="materiais_edit", material=material)

    # POST → atualizar
    titulo = request.form.get("titulo")
    descricao = request.form.get("descricao")
    link = request.form.get("link")

    cursor.execute(
        "UPDATE materiais SET titulo=%s, descricao=%s, link=%s WHERE id=%s AND professor_id=%s",
        (titulo, descricao, link, id, professor_id)
    )
    conexao.commit()
    cursor.close()
    conexao.close()
    flash("Material atualizado com sucesso!", "sucesso")
    return redirect(url_for("prof_materiais"))

# Excluir material
@app.route("/professor/materiais/delete/<int:id>", methods=["POST"])
def prof_delete_material(id):
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (session["usuario"]["id"],))
    prof = cursor.fetchone()

    cursor.execute("DELETE FROM materiais WHERE id=%s AND professor_id=%s", (id, prof["id"]))
    conexao.commit()

    cursor.close()
    conexao.close()
    flash("Material excluído com sucesso!", "sucesso")
    return redirect(url_for("prof_materiais"))

# -------------------------------------------------------
# Lançar nota (rota alternativa)
# -------------------------------------------------------
@app.route("/lancar_nota", methods=["POST"])
def lancar_nota():
    if not session.get("usuario"):
        return redirect(url_for("login"))

    aluno_id = request.form.get("aluno_id")
    professor_id = request.form.get("professor_id")
    materia_id = request.form.get("materia_id")  # agora esperável
    nota = request.form.get("nota")

    if not aluno_id or not materia_id or nota is None:
        flash("Aluno, matéria e nota são obrigatórios.", "erro")
        return redirect(url_for("professor_inicial"))

    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO notas (aluno_id, professor_id, materia_id, nota) VALUES (%s,%s,%s,%s)",
                       (aluno_id, professor_id, materia_id, nota))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    flash("Nota lançada com sucesso!", "sucesso")
    return redirect(url_for("professor_inicial"))


# -------------------------------------------------------
# 🧑‍🏫 EDITAR PERFIL (professor)
# -------------------------------------------------------
@app.route("/professor/editar_perfil", methods=["POST"])
def editar_perfil_professor():
    if not session.get("usuario"):
        return redirect(url_for("login"))

    usuario = session["usuario"]
    nome = request.form.get("nome")
    email = request.form.get("email")
    senha = request.form.get("senha")

    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE usuarios
            SET nome = %s, email = %s, senha = %s
            WHERE id = %s
        """, (nome, email.strip().lower(), senha, usuario["id"]))
        conexao.commit()
        # Atualiza sessão
        usuario["nome"] = nome
        usuario["email"] = email.strip().lower()
        session["usuario"] = usuario
    finally:
        cursor.close()
        conexao.close()

    flash("Perfil atualizado!", "sucesso")
    return redirect(url_for("professor_home"))


# Rota-facade para views do professor
@app.route("/professor/dashboard")
def professor_dashboard():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    usuario = session["usuario"]

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Identifica o professor autenticado
        cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (usuario["id"],))
        prof = cursor.fetchone()
        if not prof:
            flash("Professor não encontrado!", "erro")
            return redirect(url_for("login"))
        professor_id = prof["id"]

        # Total de turmas (usando tabela N:N)
        cursor.execute("""
            SELECT COUNT(DISTINCT t.id) AS total
            FROM turmas t
            JOIN professor_turma pt ON pt.turma_id = t.id
            WHERE pt.professor_id = %s
        """, (professor_id,))
        total_turmas = cursor.fetchone()["total"]

        # Total de alunos nas turmas do professor
        cursor.execute("""
            SELECT COUNT(DISTINCT a.id) AS total
            FROM alunos a
            JOIN turmas t ON t.id = a.turma_id
            JOIN professor_turma pt ON pt.turma_id = t.id
            WHERE pt.professor_id = %s
        """, (professor_id,))
        total_alunos = cursor.fetchone()["total"]

        # Total de materiais
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM materiais
            WHERE professor_id = %s
        """, (professor_id,))
        total_materiais = cursor.fetchone()["total"]

        # Média geral das notas
        cursor.execute("""
            SELECT AVG(nota) AS media
            FROM notas
            WHERE professor_id = %s
        """, (professor_id,))
        media_geral = cursor.fetchone()["media"] or 0

    finally:
        cursor.close()
        conexao.close()

    resumo = {
        "total_alunos": total_alunos,
        "total_turmas": total_turmas,
        "total_materiais": total_materiais,
        "media_geral": float(media_geral)
    }

    return render_template("professor.html", view="dashboard", resumo=resumo, usuario=usuario)




@app.route("/professor/turmas")
def professor_turmas():
    return professor_inicial(view="turmas")

@app.route("/prof/alunos")
def professor_alunos():
    usuario = get_usuario_session()
    if not usuario:
        return redirect(url_for("login"))

    conn = conectar()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ Pegar o ID do professor correspondente ao usuário logado
        cursor.execute("SELECT id FROM professores WHERE usuario_id = %s", (usuario["id"],))
        prof = cursor.fetchone()
        if not prof:
            flash("Professor não encontrado!", "erro")
            return redirect(url_for("login"))

        prof_id = prof["id"]

        # 2️⃣ Buscar turmas do professor usando tabela N:N
        cursor.execute("""
            SELECT t.id, t.nome
            FROM turmas t
            JOIN professor_turma pt ON pt.turma_id = t.id
            WHERE pt.professor_id = %s
        """, (prof_id,))
        turmas = cursor.fetchall()

        # 3️⃣ Pegar turma selecionada
        turma_id = request.args.get("turma_id")
        alunos = []

        if turma_id:
            cursor.execute("""
                SELECT a.id AS aluno_id,
                       u.nome AS aluno,
                       IFNULL(AVG(n.nota), 0) AS media
                FROM alunos a
                JOIN usuarios u ON u.id = a.usuario_id
                LEFT JOIN notas n ON n.aluno_id = a.id AND n.professor_id = %s
                WHERE a.turma_id = %s
                GROUP BY a.id, u.nome
            """, (prof_id, turma_id))
            alunos = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "professor.html",
        view="alunos",
        turmas=turmas,
        turma_selecionada=int(turma_id) if turma_id else None,
        alunos=alunos
    )




@app.route("/professor/notas")
def prof_notas():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    usuario = session["usuario"]

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    # Descobre o ID do professor
    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (usuario["id"],))
    professor = cursor.fetchone()
    professor_id = professor["id"]

    # BUSCA COMPLETA -> garante que aparece o nome do aluno
    cursor.execute("""
        SELECT 
            n.id,
            n.nota,
            u.nome AS aluno,
            m.nome AS materia_nome
        FROM notas n
        JOIN alunos a ON n.aluno_id = a.id
        JOIN usuarios u ON a.usuario_id = u.id
        JOIN materias m ON n.materia_id = m.id
        WHERE n.professor_id = %s
    """, (professor_id,))

    notas = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template("professor.html", view="notas", notas=notas)


@app.route("/professor/materiais")
def prof_materiais():
    if not session.get("usuario") or session["usuario"]["tipo"] != "professor":
        return redirect(url_for("login"))

    usuario = session["usuario"]
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    cursor.execute("SELECT id FROM professores WHERE usuario_id=%s", (usuario["id"],))
    prof = cursor.fetchone()
    professor_id = prof["id"]

    cursor.execute("SELECT * FROM materiais WHERE professor_id=%s", (professor_id,))
    materiais = cursor.fetchall()

    cursor.close()
    conexao.close()
    return render_template("professor.html", view="materiais", materiais=materiais)



@app.route("/professor/perfil", methods=["GET", "POST"])
def prof_perfil():
    if request.method == "POST":
        return editar_perfil_professor()
    return professor_inicial(view="perfil")

# =====================================================================
# LOGOUT
# =====================================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)