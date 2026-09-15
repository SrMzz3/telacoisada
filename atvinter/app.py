import sys
import re
import sqlite3
import requests

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QMessageBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QTabWidget,
    QAbstractItemView, QStatusBar
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from datetime import datetime


def so_num(txt):
    return re.sub(r'[^0-9]', '', txt or "")


def v_cpf(cpf):
    r = so_num(cpf)
    if len(r) != 11 or r == r[0] * 11:
        return False
    s = 0
    for i in range(10):
        s += int(r[i]) * (11 - i)
    d1 = (s * 10) % 11
    if d1 == 10:
        d1 = 0
    if d1 != int(r[10]):
        return False
    s = 0
    for i in range(11):
        s += int(r[i]) * (12 - i)
    d2 = (s * 10) % 11
    if d2 == 10:
        d2 = 0
    return d2 == int(r[11])


def v_cnpj(cnpj):
    r = so_num(cnpj)
    if len(r) != 14 or r == r[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(r[i]) * p1[i] for i in range(12))
    resto = s % 11
    d1 = 0 if resto < 2 else 11 - resto
    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(r[i]) * p2[i] for i in range(13))
    resto = s % 11
    d2 = 0 if resto < 2 else 11 - resto
    return r[-2:] == f"{d1}{d2}"


def v_email(e):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e or "") is not None


def v_cel(c):
    r = so_num(c)
    if len(r) < 10 or len(r) > 11:
        return False
    if len(r) == 11 and r[2] != '9':
        return False
    ddd = int(r[:2])
    return 11 <= ddd <= 99


def v_cep(c):
    return len(so_num(c)) == 8


def f_cpf(c):
    r = so_num(c)
    return f"{r[:3]}.{r[3:6]}.{r[6:9]}-{r[9:]}"


def f_cnpj(c):
    r = so_num(c)
    return f"{r[:2]}.{r[2:5]}.{r[5:8]}/{r[8:12]}-{r[12:]}"


def f_cel(c):
    r = so_num(c)
    if len(r) == 11:
        return f"({r[:2]}) {r[2:7]}-{r[7:]}"
    return f"({r[:2]}) {r[2:6]}-{r[6:]}"


def f_cep(c):
    r = so_num(c)
    return f"{r[:5]}-{r[5:]}"


def busca_cep_web(cep):
    c = so_num(cep)
    if len(c) != 8:
        return {"ok": False, "msg": "CEP deve ter 8 dígitos."}
    try:
        r = requests.get(f"https://viacep.com.br/ws/{c}/json/", timeout=8)
        if r.status_code != 200:
            return {"ok": False, "msg": f"Serviço retornou status {r.status_code}."}
        d = r.json()
        if "erro" in d:
            return {"ok": False, "msg": "CEP não encontrado na base dos Correios."}
        if not d.get("logradouro") and not d.get("localidade"):
            return {"ok": False, "msg": "Serviço não retornou dados de endereço."}
        return {"ok": True, "dados": d}
    except requests.exceptions.Timeout:
        return {"ok": False, "msg": "Tempo de conexão esgotado. Verifique sua internet."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "msg": "Não foi possível conectar ao serviço de CEP."}
    except Exception as e:
        return {"ok": False, "msg": f"Erro na consulta: {str(e)}"}


class Banco:
    def __init__(self, caminho="cadastros.db"):
        self.caminho = caminho
        self.cria()

    def con(self):
        return sqlite3.connect(self.caminho)

    def cria(self):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pessoas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    documento TEXT NOT NULL,
                    tipo_doc TEXT NOT NULL,
                    email TEXT NOT NULL,
                    celular TEXT NOT NULL,
                    cep TEXT NOT NULL,
                    logradouro TEXT,
                    numero TEXT,
                    complemento TEXT,
                    bairro TEXT,
                    cidade TEXT,
                    estado TEXT
                )
            """)
            c.commit()

    def insere(self, d):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("""
                INSERT INTO pessoas
                (nome, documento, tipo_doc, email, celular, cep,
                 logradouro, numero, complemento, bairro, cidade, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d["nome"], d["documento"], d["tipo_doc"], d["email"],
                  d["celular"], d["cep"], d["logradouro"], d["numero"],
                  d["complemento"], d["bairro"], d["cidade"], d["estado"]))
            c.commit()
            return cur.lastrowid

    def lista(self):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM pessoas ORDER BY id DESC")
            return cur.fetchall()

    def busca(self, i):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("SELECT * FROM pessoas WHERE id = ?", (i,))
            return cur.fetchone()

    def atualiza(self, i, d):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("""
                UPDATE pessoas SET
                    nome=?, documento=?, tipo_doc=?, email=?, celular=?,
                    cep=?, logradouro=?, numero=?, complemento=?,
                    bairro=?, cidade=?, estado=?
                WHERE id=?
            """, (d["nome"], d["documento"], d["tipo_doc"], d["email"],
                  d["celular"], d["cep"], d["logradouro"], d["numero"],
                  d["complemento"], d["bairro"], d["cidade"], d["estado"], i))
            c.commit()

    def exclui(self, i):
        with self.con() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM pessoas WHERE id = ?", (i,))
            c.commit()

    def pesquisa(self, t):
        termo = f"%{t}%"
        with self.con() as c:
            cur = c.cursor()
            cur.execute("""
                SELECT * FROM pessoas
                WHERE nome LIKE ? OR documento LIKE ? OR email LIKE ?
                   OR cidade LIKE ? OR estado LIKE ? OR cep LIKE ?
                   OR bairro LIKE ? OR logradouro LIKE ?
                ORDER BY id DESC
            """, (termo, termo, termo, termo, termo, termo, termo, termo))
            return cur.fetchall()

    def doc_existe(self, doc, ignora_id=None):
        limpo = so_num(doc)
        with self.con() as c:
            cur = c.cursor()
            cur.execute("SELECT id, documento FROM pessoas")
            for i, d in cur.fetchall():
                if ignora_id and i == ignora_id:
                    continue
                if so_num(d) == limpo:
                    return True
            return False


def gerar_pdf_cadastro(d, caminho):
    doc = SimpleDocTemplate(caminho, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    est = getSampleStyleSheet()
    tit = ParagraphStyle('t', parent=est['Title'], fontSize=18,
                         textColor=colors.HexColor('#1a237e'), spaceAfter=20)
    sub = ParagraphStyle('s', parent=est['Heading2'], fontSize=13,
                         textColor=colors.HexColor('#283593'),
                         spaceBefore=15, spaceAfter=8)
    conteudo = []
    conteudo.append(Paragraph("Comprovante de Cadastro", tit))
    conteudo.append(Paragraph(
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
        est['Normal']))
    conteudo.append(Spacer(1, 0.5*cm))

    conteudo.append(Paragraph("Dados Pessoais", sub))
    t1 = Table([
        ["Nome completo:", d.get("nome", "")],
        [f"{d.get('tipo_doc', 'Documento')}:", d.get("documento", "")],
        ["E-mail:", d.get("email", "")],
        ["Celular:", d.get("celular", "")],
    ], colWidths=[4*cm, 12*cm])
    t1.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#e0e0e0')),
    ]))
    conteudo.append(t1)

    conteudo.append(Paragraph("Endereço", sub))
    t2 = Table([
        ["CEP:", d.get("cep", "")],
        ["Logradouro:", d.get("logradouro", "")],
        ["Número:", d.get("numero", "")],
        ["Complemento:", d.get("complemento", "") or "—"],
        ["Bairro:", d.get("bairro", "")],
        ["Cidade:", d.get("cidade", "")],
        ["Estado:", d.get("estado", "")],
    ], colWidths=[4*cm, 12*cm])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#e0e0e0')),
    ]))
    conteudo.append(t2)
    conteudo.append(Spacer(1, 1*cm))

    rod = ParagraphStyle('r', parent=est['Normal'], fontSize=8,
                         textColor=colors.grey, alignment=1)
    conteudo.append(Paragraph(
        "Documento gerado automaticamente pelo Sistema de Cadastro", rod))

    doc.build(conteudo)


def gerar_pdf_tabela(registros, caminho, filtro=""):
    doc = SimpleDocTemplate(
        caminho,
        pagesize=landscape(A4),
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm)

    est = getSampleStyleSheet()
    tit = ParagraphStyle('t', parent=est['Title'], fontSize=16,
                         textColor=colors.HexColor('#1a237e'), spaceAfter=10)
    sub = ParagraphStyle('s', parent=est['Normal'], fontSize=10,
                         textColor=colors.HexColor('#555555'), spaceAfter=12)
    cel = ParagraphStyle('c', parent=est['Normal'], fontSize=8, leading=10)
    cab = ParagraphStyle('h', parent=est['Normal'], fontSize=9,
                         textColor=colors.white, leading=11)

    conteudo = []
    conteudo.append(Paragraph("Relatório de Cadastros", tit))

    info = f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}  |  " \
           f"Total de registros: {len(registros)}"
    if filtro:
        info += f"  |  Filtro aplicado: \"{filtro}\""
    conteudo.append(Paragraph(info, sub))

    if not registros:
        conteudo.append(Paragraph("Nenhum registro encontrado.", cel))
        doc.build(conteudo)
        return

    cabecalhos = ["ID", "Nome", "Documento", "E-mail", "Celular",
                  "CEP", "Logradouro", "Nº", "Bairro", "Cidade", "UF"]

    dados = [[Paragraph(f"<b>{h}</b>", cab) for h in cabecalhos]]

    for r in registros:
        linha = [
            Paragraph(str(r[0]), cel),
            Paragraph(r[1] or "", cel),
            Paragraph(f"{r[3]}: {r[2]}" if r[2] else "", cel),
            Paragraph(r[4] or "", cel),
            Paragraph(r[5] or "", cel),
            Paragraph(r[6] or "", cel),
            Paragraph(r[7] or "", cel),
            Paragraph(r[8] or "", cel),
            Paragraph(r[10] or "", cel),
            Paragraph(r[11] or "", cel),
            Paragraph(r[12] or "", cel),
        ]
        dados.append(linha)

    larguras = [1.1*cm, 3.8*cm, 3.4*cm, 4.5*cm, 2.6*cm, 2.0*cm,
                3.8*cm, 1.2*cm, 2.6*cm, 3.0*cm, 1.0*cm]

    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3f51b5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#c0c0c0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f5f5f5')]),
    ]))

    conteudo.append(tabela)
    conteudo.append(Spacer(1, 0.5*cm))

    rod = ParagraphStyle('r', parent=est['Normal'], fontSize=8,
                         textColor=colors.grey, alignment=1)
    conteudo.append(Paragraph(
        "Documento gerado automaticamente pelo Sistema de Cadastro", rod))

    doc.build(conteudo)


class TelaCad(QWidget):
    def __init__(self, banco, janela, status):
        super().__init__()
        self.banco = banco
        self.janela = janela
        self.status = status
        self.id_edit = None
        self.monta()
        self.mascaras()

    def monta(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(15)

        self.lbl_modo = QLabel("Modo: Novo cadastro")
        self.lbl_modo.setStyleSheet(
            "background:#e8eaf6; color:#1a237e; padding:8px; "
            "border-radius:4px; font-weight:bold;")
        lay.addWidget(self.lbl_modo)

        g1 = QGroupBox("Dados Pessoais")
        f1 = QFormLayout(g1)
        f1.setSpacing(10)
        f1.setLabelAlignment(Qt.AlignRight)

        self.nome = QLineEdit()
        self.nome.setPlaceholderText("Digite o nome completo")
        self.nome.setMaxLength(100)

        self.tipo = QComboBox()
        self.tipo.addItems(["CPF", "CNPJ"])
        self.tipo.currentTextChanged.connect(self.troca)

        self.doc = QLineEdit()
        self.doc.setPlaceholderText("000.000.000-00")

        self.email = QLineEdit()
        self.email.setPlaceholderText("exemplo@email.com")

        self.cel = QLineEdit()
        self.cel.setPlaceholderText("(00) 00000-0000")

        linha = QHBoxLayout()
        linha.addWidget(self.tipo)
        linha.addWidget(self.doc, 1)
        w = QWidget()
        w.setLayout(linha)

        f1.addRow("Nome completo: *", self.nome)
        f1.addRow("CPF/CNPJ: *", w)
        f1.addRow("E-mail: *", self.email)
        f1.addRow("Celular: *", self.cel)

        g2 = QGroupBox("Endereço")
        grid = QGridLayout(g2)
        grid.setSpacing(10)

        self.cep = QLineEdit()
        self.cep.setPlaceholderText("00000-000")
        self.cep.setMaxLength(9)

        self.btn_cep = QPushButton("🔍 Buscar CEP")
        self.btn_cep.clicked.connect(self.consulta_cep)

        lc = QHBoxLayout()
        lc.addWidget(self.cep, 1)
        lc.addWidget(self.btn_cep)
        wc = QWidget()
        wc.setLayout(lc)

        self.log = QLineEdit()
        self.num = QLineEdit()
        self.num.setMaxLength(10)
        self.comp = QLineEdit()
        self.bairro = QLineEdit()
        self.cidade = QLineEdit()
        self.uf = QLineEdit()
        self.uf.setMaxLength(2)

        grid.addWidget(QLabel("CEP: *"), 0, 0)
        grid.addWidget(wc, 0, 1, 1, 3)
        grid.addWidget(QLabel("Logradouro: *"), 1, 0)
        grid.addWidget(self.log, 1, 1, 1, 3)
        grid.addWidget(QLabel("Número: *"), 2, 0)
        grid.addWidget(self.num, 2, 1)
        grid.addWidget(QLabel("Complemento:"), 2, 2)
        grid.addWidget(self.comp, 2, 3)
        grid.addWidget(QLabel("Bairro: *"), 3, 0)
        grid.addWidget(self.bairro, 3, 1, 1, 3)
        grid.addWidget(QLabel("Cidade: *"), 4, 0)
        grid.addWidget(self.cidade, 4, 1, 1, 2)
        grid.addWidget(QLabel("Estado: *"), 4, 3)
        grid.addWidget(self.uf, 4, 4)

        bt = QHBoxLayout()
        bt.setSpacing(10)
        self.btn_salvar = QPushButton("💾 Cadastrar")
        self.btn_salvar.clicked.connect(self.salva)

        self.btn_limpar = QPushButton("🧹 Limpar")
        self.btn_limpar.clicked.connect(self.limpa)

        self.btn_cancelar = QPushButton("❌ Cancelar edição")
        self.btn_cancelar.clicked.connect(self.limpa)
        self.btn_cancelar.setVisible(False)

        self.btn_pdf = QPushButton("📄 PDF deste cadastro")
        self.btn_pdf.clicked.connect(self.exporta)

        bt.addWidget(self.btn_salvar)
        bt.addWidget(self.btn_limpar)
        bt.addWidget(self.btn_cancelar)
        bt.addWidget(self.btn_pdf)
        bt.addStretch()

        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addLayout(bt)
        lay.addStretch()

    def mascaras(self):
        rx_cpf = QRegularExpression(r"\d{0,3}\.?\d{0,3}\.?\d{0,3}-?\d{0,2}")
        rx_cnpj = QRegularExpression(r"\d{0,2}\.?\d{0,3}\.?\d{0,3}/?\d{0,4}-?\d{0,2}")
        rx_cel = QRegularExpression(r"\(?\d{0,2}\)?\s?\d{0,5}-?\d{0,4}")
        rx_cep = QRegularExpression(r"\d{0,5}-?\d{0,3}")

        self.val_cpf = QRegularExpressionValidator(rx_cpf)
        self.val_cnpj = QRegularExpressionValidator(rx_cnpj)
        self.doc.setValidator(self.val_cpf)
        self.cel.setValidator(QRegularExpressionValidator(rx_cel))
        self.cep.setValidator(QRegularExpressionValidator(rx_cep))

    def troca(self, t):
        self.doc.clear()
        if t == "CPF":
            self.doc.setValidator(self.val_cpf)
            self.doc.setPlaceholderText("000.000.000-00")
            self.doc.setMaxLength(14)
        else:
            self.doc.setValidator(self.val_cnpj)
            self.doc.setPlaceholderText("00.000.000/0000-00")
            self.doc.setMaxLength(18)

    def consulta_cep(self):
        c = self.cep.text().strip()
        if not v_cep(c):
            QMessageBox.warning(self, "CEP inválido",
                "O CEP deve conter exatamente 8 dígitos.\nExemplo: 01001-000")
            return
        self.btn_cep.setEnabled(False)
        self.btn_cep.setText("Buscando...")
        self.status.showMessage("Consultando CEP...")
        QApplication.processEvents()

        r = busca_cep_web(c)

        self.btn_cep.setEnabled(True)
        self.btn_cep.setText("🔍 Buscar CEP")

        if not r["ok"]:
            self.status.showMessage("Falha na consulta do CEP", 5000)
            QMessageBox.warning(self, "Não foi possível buscar o CEP",
                f"{r['msg']}\n\nVocê pode preencher o endereço manualmente.")
            return
        d = r["dados"]
        self.log.setText(d.get("logradouro", ""))
        self.bairro.setText(d.get("bairro", ""))
        self.cidade.setText(d.get("localidade", ""))
        self.uf.setText(d.get("uf", ""))
        self.num.setFocus()
        self.status.showMessage("Endereço preenchido automaticamente!", 4000)

    def coleta(self):
        return {
            "nome": self.nome.text().strip(),
            "tipo_doc": self.tipo.currentText(),
            "documento": self.doc.text().strip(),
            "email": self.email.text().strip(),
            "celular": self.cel.text().strip(),
            "cep": self.cep.text().strip(),
            "logradouro": self.log.text().strip(),
            "numero": self.num.text().strip(),
            "complemento": self.comp.text().strip(),
            "bairro": self.bairro.text().strip(),
            "cidade": self.cidade.text().strip(),
            "estado": self.uf.text().strip().upper()
        }

    def valida(self, d):
        e = []
        if not d["nome"]:
            e.append("• Nome completo é obrigatório.")
        elif len(d["nome"]) < 3:
            e.append("• Nome deve ter pelo menos 3 caracteres.")

        if not d["documento"]:
            e.append(f"• {d['tipo_doc']} é obrigatório.")
        else:
            if d["tipo_doc"] == "CPF" and not v_cpf(d["documento"]):
                e.append("• CPF informado é inválido. Confira os dígitos.")
            if d["tipo_doc"] == "CNPJ" and not v_cnpj(d["documento"]):
                e.append("• CNPJ informado é inválido. Confira os dígitos.")

        if not d["email"]:
            e.append("• E-mail é obrigatório.")
        elif not v_email(d["email"]):
            e.append("• E-mail inválido. Use o formato nome@dominio.com")

        if not d["celular"]:
            e.append("• Celular é obrigatório.")
        elif not v_cel(d["celular"]):
            e.append("• Celular inválido. Use DDD + número (ex: (11) 91234-5678).")

        if not d["cep"]:
            e.append("• CEP é obrigatório.")
        elif not v_cep(d["cep"]):
            e.append("• CEP inválido. Deve conter 8 dígitos.")

        if not d["logradouro"]:
            e.append("• Logradouro é obrigatório.")
        if not d["numero"]:
            e.append("• Número é obrigatório.")
        if not d["bairro"]:
            e.append("• Bairro é obrigatório.")
        if not d["cidade"]:
            e.append("• Cidade é obrigatória.")
        if not d["estado"]:
            e.append("• Estado é obrigatório.")
        elif len(d["estado"]) != 2:
            e.append("• Estado deve ter 2 letras (ex: SP, RJ).")
        return e

    def salva(self):
        d = self.coleta()
        erros = self.valida(d)
        if erros:
            msg = "Corrija os seguintes problemas antes de continuar:\n\n" + "\n".join(erros)
            QMessageBox.warning(self, "Dados inválidos", msg)
            self.status.showMessage("Existem erros no formulário", 5000)
            return

        if self.banco.doc_existe(d["documento"], self.id_edit):
            QMessageBox.warning(self, "Documento duplicado",
                f"Já existe um cadastro com esse {d['tipo_doc']}.")
            return

        d["celular"] = f_cel(d["celular"])
        d["cep"] = f_cep(d["cep"])
        if d["tipo_doc"] == "CPF":
            d["documento"] = f_cpf(d["documento"])
        else:
            d["documento"] = f_cnpj(d["documento"])

        try:
            if self.id_edit:
                self.banco.atualiza(self.id_edit, d)
                QMessageBox.information(self, "Sucesso", "Cadastro atualizado com sucesso!")
                self.id_edit = None
            else:
                self.banco.insere(d)
                QMessageBox.information(self, "Sucesso", "Cadastro realizado com sucesso!")
            self.status.showMessage("Cadastro salvo!", 4000)
            self.limpa()
            self.janela.tabela.atualiza()
        except Exception as ex:
            QMessageBox.critical(self, "Erro ao salvar",
                f"Ocorreu um erro ao salvar no banco de dados:\n{str(ex)}")

    def limpa(self):
        for w in [self.nome, self.doc, self.email, self.cel, self.cep,
                  self.log, self.num, self.comp, self.bairro,
                  self.cidade, self.uf]:
            w.clear()
        self.tipo.setCurrentIndex(0)
        self.nome.setFocus()
        self.id_edit = None
        self.btn_salvar.setText("💾 Cadastrar")
        self.btn_cancelar.setVisible(False)
        self.lbl_modo.setText("Modo: Novo cadastro")
        self.status.showMessage("Formulário limpo", 3000)

    def carrega(self, i):
        r = self.banco.busca(i)
        if not r:
            return
        self.id_edit = i
        self.nome.setText(r[1])
        self.tipo.setCurrentText(r[3])
        self.doc.setText(r[2])
        self.email.setText(r[4])
        self.cel.setText(r[5])
        self.cep.setText(r[6])
        self.log.setText(r[7] or "")
        self.num.setText(r[8] or "")
        self.comp.setText(r[9] or "")
        self.bairro.setText(r[10] or "")
        self.cidade.setText(r[11] or "")
        self.uf.setText(r[12] or "")
        self.btn_salvar.setText("💾 Atualizar")
        self.btn_cancelar.setVisible(True)
        self.lbl_modo.setText(f"Modo: Editando registro #{i} — {r[1]}")
        self.status.showMessage(f"Editando registro #{i}", 4000)

    def exporta(self):
        d = self.coleta()
        erros = self.valida(d)
        if erros:
            QMessageBox.warning(self, "Dados incompletos",
                "Preencha corretamente o formulário antes de exportar o PDF.")
            return
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", f"cadastro_{d['nome'].split()[0]}.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        d["celular"] = f_cel(d["celular"])
        d["cep"] = f_cep(d["cep"])
        if d["tipo_doc"] == "CPF":
            d["documento"] = f_cpf(d["documento"])
        else:
            d["documento"] = f_cnpj(d["documento"])
        try:
            gerar_pdf_cadastro(d, caminho)
            QMessageBox.information(self, "PDF gerado",
                f"PDF exportado com sucesso em:\n{caminho}")
            self.status.showMessage("PDF exportado!", 4000)
        except Exception as ex:
            QMessageBox.critical(self, "Erro ao gerar PDF",
                f"Não foi possível gerar o PDF:\n{str(ex)}")


class TelaTabela(QWidget):
    def __init__(self, banco, tela_cad, status, janela):
        super().__init__()
        self.banco = banco
        self.tela_cad = tela_cad
        self.status = status
        self.janela = janela
        self.regs_atual = []
        self.monta()
        self.atualiza()

    def monta(self):
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()

        self.busca = QLineEdit()
        self.busca.setPlaceholderText(
            "🔎 Filtrar por nome, documento, e-mail, cidade, estado, CEP, bairro...")
        self.busca.textChanged.connect(self.pesquisa)
        self.busca.setClearButtonEnabled(True)

        btn_atualizar = QPushButton("🔄 Atualizar")
        btn_atualizar.clicked.connect(self.atualiza)

        btn_limpar_filtro = QPushButton("🧹 Limpar filtro")
        btn_limpar_filtro.clicked.connect(lambda: self.busca.clear())

        self.btn_pdf_tab = QPushButton("📄 Exportar tabela para PDF")
        self.btn_pdf_tab.clicked.connect(self.exporta_tabela)

        topo.addWidget(QLabel("Filtro:"))
        topo.addWidget(self.busca, 1)
        topo.addWidget(btn_limpar_filtro)
        topo.addWidget(btn_atualizar)
        topo.addWidget(self.btn_pdf_tab)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color:#555; padding:4px;")

        self.tab = QTableWidget()
        self.tab.setColumnCount(8)
        self.tab.setHorizontalHeaderLabels(
            ["ID", "Nome", "Documento", "E-mail", "Celular",
             "Cidade/UF", "CEP", "Ações"])
        self.tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tab.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.doubleClicked.connect(self.edita_duplo)

        lay.addLayout(topo)
        lay.addWidget(self.lbl_info)
        lay.addWidget(self.tab)

    def atualiza(self, regs=None):
        if regs is None:
            regs = self.banco.lista()
            self.busca.blockSignals(True)
            self.busca.clear()
            self.busca.blockSignals(False)
        self.regs_atual = regs
        self._preenche(regs)

    def _preenche(self, regs):
        self.tab.setRowCount(0)
        for i, r in enumerate(regs):
            self.tab.insertRow(i)
            self.tab.setItem(i, 0, QTableWidgetItem(str(r[0])))
            self.tab.setItem(i, 1, QTableWidgetItem(r[1]))
            self.tab.setItem(i, 2, QTableWidgetItem(f"{r[3]}: {r[2]}"))
            self.tab.setItem(i, 3, QTableWidgetItem(r[4]))
            self.tab.setItem(i, 4, QTableWidgetItem(r[5]))
            self.tab.setItem(i, 5, QTableWidgetItem(f"{r[11]}/{r[12]}"))
            self.tab.setItem(i, 6, QTableWidgetItem(r[6]))

            b1 = QPushButton("✏️")
            b1.setToolTip("Editar")
            b1.clicked.connect(lambda _=False, x=r[0]: self.edita(x))

            b2 = QPushButton("🗑️")
            b2.setToolTip("Excluir")
            b2.clicked.connect(lambda _=False, x=r[0]: self.exclui(x))

            b3 = QPushButton("📄")
            b3.setToolTip("Exportar PDF individual")
            b3.clicked.connect(lambda _=False, x=r[0]: self.gera_pdf_individual(x))

            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(b1)
            h.addWidget(b2)
            h.addWidget(b3)
            self.tab.setCellWidget(i, 7, w)

        t = self.busca.text().strip()
        if t:
            self.lbl_info.setText(
                f"Mostrando {len(regs)} registro(s) para o filtro: \"{t}\"")
        else:
            self.lbl_info.setText(f"Mostrando {len(regs)} registro(s) no total.")

    def edita_duplo(self, idx):
        i = int(self.tab.item(idx.row(), 0).text())
        self.edita(i)

    def pesquisa(self, t):
        if not t.strip():
            self.atualiza(self.banco.lista())
            self.regs_atual = self.banco.lista()
            self._preenche(self.regs_atual)
        else:
            r = self.banco.pesquisa(t.strip())
            self.regs_atual = r
            self._preenche(r)

    def edita(self, i):
        self.tela_cad.carrega(i)
        self.janela.abas.setCurrentIndex(0)

    def exclui(self, i):
        if self.tela_cad.id_edit == i:
            r = QMessageBox.question(self, "Registro em edição",
                "Esse registro está sendo editado agora. Excluir mesmo assim?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
            self.tela_cad.limpa()

        r = QMessageBox.question(self, "Confirmar exclusão",
            f"Tem certeza que deseja excluir o registro #{i}?",
            QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            self.banco.exclui(i)
            if self.busca.text().strip():
                self.pesquisa(self.busca.text())
            else:
                self.atualiza()
            self.status.showMessage(f"Registro #{i} excluído", 4000)

    def exporta_tabela(self):
        if not self.regs_atual:
            QMessageBox.information(self, "Nada para exportar",
                "Não há registros para exportar com o filtro atual.")
            return
        filtro = self.busca.text().strip()
        nome_sug = "cadastros.pdf" if not filtro else f"cadastros_filtro_{filtro}.pdf"
        nome_sug = re.sub(r'[^\w\-.]', '_', nome_sug)
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF da tabela", nome_sug, "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        try:
            gerar_pdf_tabela(self.regs_atual, caminho, filtro)
            QMessageBox.information(self, "PDF gerado",
                f"PDF da tabela exportado com sucesso em:\n{caminho}")
            self.status.showMessage("PDF da tabela exportado!", 4000)
        except Exception as ex:
            QMessageBox.critical(self, "Erro ao gerar PDF",
                f"Não foi possível gerar o PDF:\n{str(ex)}")

    def gera_pdf_individual(self, i):
        r = self.banco.busca(i)
        if not r:
            return
        d = {
            "nome": r[1], "documento": r[2], "tipo_doc": r[3],
            "email": r[4], "celular": r[5], "cep": r[6],
            "logradouro": r[7], "numero": r[8], "complemento": r[9],
            "bairro": r[10], "cidade": r[11], "estado": r[12]
        }
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", f"cadastro_{r[1].split()[0]}.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        try:
            gerar_pdf_cadastro(d, caminho)
            QMessageBox.information(self, "PDF gerado",
                f"PDF exportado com sucesso em:\n{caminho}")
        except Exception as ex:
            QMessageBox.critical(self, "Erro ao gerar PDF",
                f"Não foi possível gerar o PDF:\n{str(ex)}")


class Janela(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Cadastro - PySide6")
        self.resize(1100, 720)

        self.banco = Banco()
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.abas = QTabWidget()
        self.cadastro = TelaCad(self.banco, self, self.status)
        self.tabela = TelaTabela(self.banco, self.cadastro, self.status, self)

        self.abas.addTab(self.cadastro, "📝 Cadastro")
        self.abas.addTab(self.tabela, "📋 Registros / Filtro / PDF")
        self.setCentralWidget(self.abas)

        self.aplica_estilo()
        self.status.showMessage("Pronto", 3000)

    def aplica_estilo(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #c0c0c0;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1a237e;
            }
            QLineEdit, QComboBox {
                padding: 6px;
                border: 1px solid #bdbdbd;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3f51b5;
            }
            QPushButton {
                padding: 7px 14px;
                border-radius: 4px;
                background-color: #3f51b5;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #303f9f; }
            QPushButton:pressed { background-color: #1a237e; }
            QPushButton:disabled { background-color: #9fa8da; }
            QTableWidget {
                background-color: white;
                gridline-color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #3f51b5;
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTabWidget::pane { border: 1px solid #c0c0c0; }
            QTabBar::tab {
                padding: 8px 16px;
                background: #e8eaf6;
                color: #1a237e;
            }
            QTabBar::tab:selected {
                background: #3f51b5;
                color: white;
            }
        """)


def main():
    app = QApplication(sys.argv)
    janela = Janela()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()