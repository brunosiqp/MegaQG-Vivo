"""
As oito correções do QG XML (v4) aplicadas a um XML de DPS/NFSe já carregado em memória.

Cada função recebe a raiz do XML e devolve (quantidade de alterações, mensagens). Nenhuma
grava arquivo nem acessa a rede: o código do município vem de um "resolvedor" passado por
quem chama (ver cep.py). As tags são procuradas pelo nome local, então tudo funciona em XML
com ou sem xmlns, e as tags criadas herdam o namespace do elemento onde entram.

Diferenças em relação ao script original (QG XML v4), todas no sentido do que ele se propunha:
  - cLocEmi e cLocPrestacao agora funcionam em XML com xmlns (antes não achavam as tags);
  - PIS/COFINS é recalculado com arredondamento fiscal (meio centavo para cima), em decimal;
  - CST vazio é preenchido na própria tag (antes era criada uma segunda tag CST);
  - padronizar o CST para dois dígitos conta como alteração (o arquivo é salvo).
"""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import xml.etree.ElementTree as ET

# id, nome mostrado na tela, o que faz
CORRECOES = [
    ("encoding", "Caracteres corrompidos", "Tags de texto iniciadas por \"x\" com sinais de conversão errada"),
    ("numero", "Número do endereço", "Cria <nro>01</nro> em tomador e destinatário quando a tag não existe"),
    ("cmun", "Código do município (cMun)", "Preenche pelo CEP quando está ausente ou vazio, em tomador e destinatário"),
    ("clocemi", "Local de emissão (cLocEmi)", "Usa o cMun do emitente quando está ausente, vazio ou \"0\""),
    ("clocprestacao", "Local da prestação (cLocPrestacao)",
     "Usa o cMun do emitente quando está ausente, vazio ou \"0\". Presume serviço prestado no município do emitente"),
    ("piscofins", "PIS/COFINS", "CST ausente, CST 00/08/09 com valores, alíquotas ×100 e valores recalculados"),
    ("iss", "Alíquota do ISS (pAliq)", "Divide por 100 quando é maior que 10"),
    ("competencia", "Data de competência (dCompet)", "Iguala à data de <dhEmi> quando é diferente ou está vazia"),
]
IDS_CORRECOES = [c[0] for c in CORRECOES]

CST_PADRAO = "01"  # CST usado quando o grupo tem base, alíquotas ou valores mas não tem CST
CAMPOS_PISCOFINS = ("vBCPisCofins", "pAliqPis", "pAliqCofins", "vPis", "vCofins")
CSTS_SEM_BASE = {"00", "08", "09"}  # rejeição E0682: não admitem base, alíquotas nem valores
CENTAVO = Decimal("0.01")


class ErroCorrecaoCep(Exception):
    """A DPS não pode ser corrigida por falta de CEP ou porque o CEP não foi resolvido."""


# ------------------------------------------------------------------ auxiliares de XML
def nome_local(tag) -> str:
    """Nome da tag sem o namespace: {http://...}CEP -> CEP."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def obter_namespace(tag) -> str:
    return tag.split("}", 1)[0][1:] if tag.startswith("{") and "}" in tag else ""


def criar_elemento(nome, referencia):
    """Nova tag no mesmo namespace do elemento de referência."""
    namespace = obter_namespace(referencia.tag)
    return ET.Element(f"{{{namespace}}}{nome}" if namespace else nome)


def filho(elemento, nome):
    """Filho direto com esse nome local (ou None)."""
    if elemento is None:
        return None
    return next((f for f in elemento if nome_local(f.tag) == nome), None)


def descendente(elemento, nome):
    """Primeiro elemento com esse nome local em toda a estrutura (ou None)."""
    return next((e for e in elemento.iter() if nome_local(e.tag) == nome), None)


def _texto(elemento) -> str:
    return (elemento.text or "").strip() if elemento is not None else ""


# ------------------------------------------------------- 1. caracteres corrompidos
# Sinais de UTF-8 lido como Windows-1252/Latin-1 ("mojibake")
PADROES_ENCODING_SUSPEITO = (
    "Ã", "Â", "â€", "â€™", "â€œ", "â€\x9d", "â€“", "â€”", "ðŸ", "�",
)

# Sequências conhecidas, corrigidas antes da tentativa genérica. Escritas com \u onde o
# caractere é invisível ou ambíguo (ƒ = ƒ, ‚ = ‚, hífen suave = ­).
CORRECOES_ENCODING_CONHECIDAS = {
    "Ã‚": "Â",
    "Ã\u0082": "Â",
    "ÃƒÂ‚": "Â",
    "ÃƒÂ\u0082": "Â",
    "ÃƒÂ£": "ã",
    "ÃƒÂ§": "ç",
    "ÃƒÂ©": "é",
    "ÃƒÂª": "ê",
    "ÃƒÂº": "ú",
    "ÃƒÂ¡": "á",
    "ÃƒÂ³": "ó",
    "ÃƒÂ­": "í",
    "UNIÃƒO": "UNIÃO",
    # Alguns XMLs trazem a letra Ã (A com til) em maiúsculo nessa forma incompleta de
    # dupla codificação, sem o caractere Â intermediário.
    "NÃƒO": "NÃO",
    "nÃƒo": "não",
    "ÃƒO": "ÃO",
    "Ãƒo": "ão",
}


def pontuar_texto_corrompido(texto) -> int:
    """Quanto maior a pontuação, maior a chance de o texto estar com UTF-8 interpretado
    como Windows-1252/Latin-1."""
    if not texto:
        return 0
    pontos = sum(texto.count(padrao) for padrao in PADROES_ENCODING_SUSPEITO)
    # Caracteres de controle da faixa C1 também costumam indicar a conversão errada
    return pontos + sum(1 for caractere in texto if 0x80 <= ord(caractere) <= 0x9F)


def corrigir_texto_corrompido(texto):
    """Desfaz uma ou mais camadas de conversão errada: "nÃƒÂ£o" -> "não".
    Só aceita o resultado se o texto melhorar. Devolve (texto, alterou)."""
    if not texto or pontuar_texto_corrompido(texto) == 0:
        return texto, False
    original = atual = texto
    for errado, correto in CORRECOES_ENCODING_CONHECIDAS.items():
        atual = atual.replace(errado, correto)
    for _ in range(4):  # até 4 camadas
        melhor_texto, melhor_pontuacao = atual, pontuar_texto_corrompido(atual)
        for codificacao_errada in ("cp1252", "latin-1"):
            try:
                candidato = atual.encode(codificacao_errada).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            pontuacao = pontuar_texto_corrompido(candidato)
            if pontuacao < melhor_pontuacao:
                melhor_texto, melhor_pontuacao = candidato, pontuacao
        if melhor_texto == atual:
            break
        atual = melhor_texto
        if melhor_pontuacao == 0:
            break
    return atual, atual != original


def corrigir_encoding(raiz):
    """Só o texto das tags cujo nome começa com "x" (xNome, xLgr, xCpl, xDescServ...)."""
    quantidade, mensagens = 0, []
    for elemento in raiz.iter():
        nome_tag = nome_local(elemento.tag)
        if not nome_tag.lower().startswith("x") or not elemento.text:
            continue
        original = elemento.text
        corrigido, alterado = corrigir_texto_corrompido(original)
        if alterado:
            elemento.text = corrigido
            quantidade += 1
            if quantidade <= 10:
                mensagens.append(f"Encoding corrigido: <{nome_tag}> '{original.strip()}' -> '{corrigido.strip()}'")
    if quantidade:
        mensagens.insert(0, f"Encoding: {quantidade} campo(s) com caracteres corrompidos foram corrigidos.")
    return quantidade, mensagens


# ------------------------------------------------------- 2. número do endereço
def blocos_de_endereco(raiz):
    """(tomadores, destinatários) do documento."""
    tomadores = [e for e in raiz.iter() if nome_local(e.tag) == "toma"]
    destinatarios = [e for e in raiz.iter() if nome_local(e.tag) == "dest"]
    return tomadores, destinatarios


def preencher_numero_ausente(raiz):
    """Inclui <nro>01</nro> nos endereços de toma e dest que não têm a tag. Um <nro> que já
    exista não é alterado, mesmo vazio."""
    alteracoes, mensagens = 0, []
    tomadores, destinatarios = blocos_de_endereco(raiz)
    for bloco in tomadores + destinatarios:
        endereco = filho(bloco, "end")
        if endereco is None or filho(endereco, "nro") is not None:
            continue
        numero = criar_elemento("nro", endereco)
        numero.text = "01"
        logradouro = filho(endereco, "xLgr")
        if logradouro is not None:
            endereco.insert(list(endereco).index(logradouro) + 1, numero)
        else:
            # Mantém a sequência do leiaute sem xLgr: antes de complemento ou bairro, se houver
            proxima = next((f for f in endereco if nome_local(f.tag) in {"xCpl", "xBairro"}), None)
            if proxima is None:
                endereco.append(numero)
            else:
                endereco.insert(list(endereco).index(proxima), numero)
        alteracoes += 1
        mensagens.append(f"<{nome_local(bloco.tag)}>: tag <nro> ausente; incluído '01'.")
    return alteracoes, mensagens


# ------------------------------------------------------- 3. cMun de tomador e destinatário
def limpar_cep(cep) -> str:
    return re.sub(r"\D", "", cep or "")


def _end_nac(bloco):
    return filho(filho(bloco, "end"), "endNac")


def _cep_do_bloco(bloco):
    cep = _texto(filho(_end_nac(bloco), "CEP"))
    return limpar_cep(cep) or None


def _preencher_cmun(end_nac, cmun):
    """Preenche <cMun> só quando não existe ou está vazio; inexistente, é criado antes de <CEP>."""
    tag_cep = filho(end_nac, "CEP")
    if tag_cep is None:
        return False, "Tag <CEP> não encontrada dentro de <endNac>."
    tag_cmun = filho(end_nac, "cMun")
    if tag_cmun is not None:
        if _texto(tag_cmun):
            return False, f"Tag <cMun> já preenchida com {_texto(tag_cmun)}; nenhuma alteração realizada."
        tag_cmun.text = cmun
        return True, "Tag <cMun> estava vazia e foi preenchida."
    nova = criar_elemento("cMun", end_nac)
    nova.text = cmun
    end_nac.insert(list(end_nac).index(tag_cep), nova)
    return True, "Tag <cMun> adicionada."


def _processar_bloco(bloco, resolvedor, cache_ceps, cmun_referencia=None):
    """<toma> ou <dest>: cMun preenchido não gera consulta nem alteração; ausente ou vazio é
    obtido pelo CEP. Devolve (alterou, cMun, mensagem)."""
    nome_bloco = nome_local(bloco.tag)
    end_nac = _end_nac(bloco)
    if end_nac is None:
        return False, None, f"<{nome_bloco}> não possui a estrutura <end>/<endNac>."
    cmun_atual = _texto(filho(end_nac, "cMun"))
    if cmun_atual:
        return False, cmun_atual, (f"<{nome_bloco}>: cMun já preenchido com {cmun_atual}. "
                                   "Nenhuma consulta ou alteração realizada.")
    cep = limpar_cep(_texto(filho(end_nac, "CEP")))
    if not cep:
        raise ErroCorrecaoCep(f"<{nome_bloco}> possui cMun ausente/vazio, mas não possui CEP dentro de <endNac>.")
    if cmun_referencia:
        cmun = cmun_referencia
    elif cep in cache_ceps:
        cmun = cache_ceps[cep]
    else:
        try:
            cmun = resolvedor.cmun_por_cep(cep)
        except Exception as erro:
            # CEP sem resolução vai para pendentes: não se usa endereço alternativo, para não
            # preencher a DPS com dado incerto.
            raise ErroCorrecaoCep(f"CEP {cep} não pôde ser resolvido e foi marcado para correção manual: "
                                  f"{erro}") from erro
        cache_ceps[cep] = cmun
    alterado, mensagem = _preencher_cmun(end_nac, cmun)
    return alterado, cmun, f"<{nome_bloco}>: CEP {cep} -> cMun {cmun}. {mensagem}"


def corrigir_cmun(raiz, resolvedor, cache_ceps):
    """cMun de tomadores e destinatários. O destinatário reaproveita o cMun do tomador quando
    os CEPs são iguais ou quando ele não tem CEP; com CEP diferente, consulta o próprio."""
    alteracoes, mensagens = 0, []
    tomadores, destinatarios = blocos_de_endereco(raiz)
    cmuns_toma = []
    for bloco in tomadores:
        try:
            alterado, cmun, mensagem = _processar_bloco(bloco, resolvedor, cache_ceps)
        except ErroCorrecaoCep:
            raise
        except Exception as erro:
            raise RuntimeError(f"<toma>: erro ao processar: {erro}") from erro
        mensagens.append(mensagem)
        alteracoes += alterado
        if cmun:
            cmuns_toma.append(cmun)

    for indice, bloco in enumerate(destinatarios):
        try:
            # Reaproveita o cMun do tomador correspondente (ou do único tomador do XML)
            referencia = cmuns_toma[indice] if indice < len(cmuns_toma) else (
                cmuns_toma[0] if len(cmuns_toma) == 1 else None)
            cep_dest = _cep_do_bloco(bloco)
            if cep_dest:
                toma = tomadores[indice] if indice < len(tomadores) else (
                    tomadores[0] if len(tomadores) == 1 else None)
                cep_toma = _cep_do_bloco(toma) if toma is not None else None
                if cep_toma and cep_dest != cep_toma:
                    referencia = None  # CEP próprio e diferente: vale o do destinatário
            alterado, _cmun, mensagem = _processar_bloco(bloco, resolvedor, cache_ceps, referencia)
        except ErroCorrecaoCep:
            raise
        except Exception as erro:
            raise RuntimeError(f"<dest>: erro ao processar: {erro}") from erro
        mensagens.append(mensagem)
        alteracoes += alterado
    return alteracoes, mensagens


# ------------------------------------------------------- 4 e 5. cLocEmi e cLocPrestacao
def cmun_do_emitente(raiz, resolvedor):
    """cMun do prestador: o que estiver em prest/end/endNac/cMun; sem ele, pelo CNPJ
    (CNPJ -> CEP -> cMun). None se não der para determinar."""
    prest = descendente(raiz, "prest")
    if prest is None:
        return None
    cmun = _texto(filho(_end_nac(prest), "cMun"))
    if cmun and cmun != "0":
        return cmun
    cnpj = _texto(filho(prest, "CNPJ"))
    if cnpj and resolvedor is not None:
        return resolvedor.cmun_por_cnpj(cnpj)
    return None


def _precisa_preencher(elemento) -> bool:
    return _texto(elemento) in ("", "0")


def corrigir_clocemi(raiz, resolvedor):
    """<cLocEmi> ausente, vazio ou "0" recebe o cMun do emitente; criado, entra após <tpEmit>."""
    inf_dps = descendente(raiz, "infDPS")
    if inf_dps is None:
        return 0, []
    cloc = filho(inf_dps, "cLocEmi")
    if not _precisa_preencher(cloc):
        return 0, []
    cmun = cmun_do_emitente(raiz, resolvedor)
    if not cmun:
        return 0, ["cLocEmi ausente ou zerado, mas o cMun do emitente não pôde ser determinado; não alterado."]
    if cloc is not None:
        cloc.text = cmun
        return 1, [f"cLocEmi corrigido ({cmun}), pelo cMun do emitente."]
    cloc = criar_elemento("cLocEmi", inf_dps)
    cloc.text = cmun
    filhos = list(inf_dps)
    tp_emit = filho(inf_dps, "tpEmit")
    if tp_emit is not None:
        inf_dps.insert(filhos.index(tp_emit) + 1, cloc)
    else:
        seguinte = next((f for f in filhos if nome_local(f.tag) in {"subst", "prest"}), None)
        if seguinte is None:
            inf_dps.append(cloc)
        else:
            inf_dps.insert(filhos.index(seguinte), cloc)
    return 1, [f"cLocEmi criado ({cmun}), pelo cMun do emitente."]


def corrigir_clocprestacao(raiz, resolvedor):
    """<serv>/<locPrest>/<cLocPrestacao> ausente, vazio ou "0" recebe o cMun do emitente
    (presume serviço prestado no município do emitente). <locPrest> é criado antes de <cServ>."""
    serv = descendente(raiz, "serv")
    if serv is None:
        return 0, []
    loc_prest = filho(serv, "locPrest")
    cloc = filho(loc_prest, "cLocPrestacao")
    if not _precisa_preencher(cloc):
        return 0, []
    cmun = cmun_do_emitente(raiz, resolvedor)
    if not cmun:
        return 0, ["cLocPrestacao ausente ou zerado, mas o cMun do emitente não pôde ser determinado; "
                   "não alterado."]
    criado = cloc is None
    if loc_prest is None:
        loc_prest = criar_elemento("locPrest", serv)
        c_serv = filho(serv, "cServ")
        serv.insert(list(serv).index(c_serv) if c_serv is not None else 0, loc_prest)
    if cloc is None:
        cloc = criar_elemento("cLocPrestacao", loc_prest)
        loc_prest.append(cloc)
    cloc.text = cmun
    return 1, [f"cLocPrestacao {'criado' if criado else 'corrigido'} ({cmun}), pelo cMun do emitente."]


# ------------------------------------------------------- 6. PIS/COFINS e 7. ISS
def _decimal(elemento, nome):
    try:
        return Decimal((elemento.text or "").strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"valor inválido em <{nome}>: '{elemento.text}'") from None


def _duas_casas(valor) -> str:
    """Duas casas com arredondamento fiscal (meio centavo para cima)."""
    return str(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))


def _dividir_aliquota(elemento, nome, limite):
    """Alíquota maior que o limite foi multiplicada por 100 por engano: divide por 100."""
    if elemento is None or not _texto(elemento):
        return None
    valor = _decimal(elemento, nome)
    if valor <= limite:
        return None
    elemento.text = _duas_casas(valor / 100)
    return f"{nome}: {_duas_casas(valor)} -> {elemento.text}"


def corrigir_piscofins(raiz, cst_padrao=CST_PADRAO):
    """Regulariza cada grupo <piscofins>: CST ausente, CST sem base com valores, alíquotas
    multiplicadas por 100 e valores divergentes do cálculo."""
    alteracoes, mensagens = 0, []
    for grupo in [e for e in raiz.iter() if nome_local(e.tag) == "piscofins"]:
        tags = {nome_local(f.tag): f for f in grupo}
        tag_cst = tags.get("CST")
        if not _texto(tag_cst):
            if not any(campo in tags for campo in CAMPOS_PISCOFINS):
                raise RuntimeError("PIS/COFINS sem CST e sem dados para determinar a tributação.")
            if tag_cst is None:
                tag_cst = criar_elemento("CST", grupo)
                grupo.insert(0, tag_cst)
            tag_cst.text = cst_padrao
            mensagens.append(f"PIS/COFINS: CST ausente; incluído CST {cst_padrao} porque há base, "
                             "alíquotas ou valores de contribuição.")
            alteracoes += 1

        cst = _texto(tag_cst).zfill(2)
        if tag_cst.text != cst:
            mensagens.append(f"PIS/COFINS: CST '{_texto(tag_cst)}' padronizado para '{cst}'.")
            tag_cst.text = cst
            alteracoes += 1

        if cst in CSTS_SEM_BASE:
            removidos = [campo for campo in CAMPOS_PISCOFINS if campo in tags]
            for campo in removidos:
                grupo.remove(tags[campo])
            if removidos:
                mensagens.append(f"PIS/COFINS: CST {cst} não permite base, alíquotas ou valores; removidos "
                                 + ", ".join(removidos) + ".")
                alteracoes += len(removidos)
            continue

        for nome, limite in (("pAliqPis", 10), ("pAliqCofins", 20)):
            mensagem = _dividir_aliquota(tags.get(nome), nome, limite)
            if mensagem:
                mensagens.append(mensagem)
                alteracoes += 1

        if all(campo in tags for campo in CAMPOS_PISCOFINS):
            base = _decimal(tags["vBCPisCofins"], "vBCPisCofins")
            for nome_valor, nome_aliquota in (("vPis", "pAliqPis"), ("vCofins", "pAliqCofins")):
                calculado = (base * _decimal(tags[nome_aliquota], nome_aliquota) / 100).quantize(
                    CENTAVO, rounding=ROUND_HALF_UP)
                tag_valor = tags[nome_valor]
                atual = _decimal(tag_valor, nome_valor) if _texto(tag_valor) else None
                if atual != calculado:
                    mensagens.append(f"{nome_valor}: {_texto(tag_valor) or '(vazio)'} -> {calculado}")
                    tag_valor.text = str(calculado)
                    alteracoes += 1
    return alteracoes, mensagens


def corrigir_aliquota_iss(raiz):
    """<pAliq> maior que 10 é dividido por 100 (500 vira 5.00)."""
    alteracoes, mensagens = 0, []
    for elemento in raiz.iter():
        if nome_local(elemento.tag) == "pAliq":
            mensagem = _dividir_aliquota(elemento, "pAliq", 10)
            if mensagem:
                mensagens.append(mensagem)
                alteracoes += 1
    return alteracoes, mensagens


# ------------------------------------------------------- 8. data de competência
def corrigir_competencia(raiz):
    """<dCompet> passa a ser a data de <dhEmi> (a parte antes do "T") quando é diferente ou
    está vazia. Não cria <dCompet>, não converte fuso e não altera com <dhEmi> ausente/inválida."""
    emissoes = [e for e in raiz.iter() if nome_local(e.tag) == "dhEmi"]
    competencias = [e for e in raiz.iter() if nome_local(e.tag) == "dCompet"]
    if not emissoes:
        return 0, ["Competência: tag <dhEmi> não encontrada; nenhuma alteração."]
    if not competencias:
        return 0, ["Competência: tag <dCompet> não encontrada; nenhuma alteração."]
    alteracoes, mensagens = 0, []
    for indice, tag_competencia in enumerate(competencias):
        # Normalmente há um par por documento; havendo vários, relaciona por posição
        valor_emissao = _texto(emissoes[indice] if indice < len(emissoes) else emissoes[0])
        achado = re.match(r"^(\d{4}-\d{2}-\d{2})(?:T|$)", valor_emissao)
        if not achado:
            mensagens.append(f"Competência: valor inválido em <dhEmi> ('{valor_emissao}'); "
                             "<dCompet> não foi alterada.")
            continue
        data_emissao, valor_competencia = achado.group(1), _texto(tag_competencia)
        if valor_competencia == data_emissao:
            mensagens.append(f"Competência: <dCompet> já está correta ({data_emissao}).")
            continue
        tag_competencia.text = data_emissao
        alteracoes += 1
        mensagens.append(f"Competência corrigida: <dCompet> '{valor_competencia or '(vazio)'}' -> "
                         f"'{data_emissao}', conforme <dhEmi>.")
    return alteracoes, mensagens


# ------------------------------------------------------------------ documento inteiro
def corrigir_documento(raiz, resolvedor=None, cache_ceps=None, correcoes=None, cst_padrao=CST_PADRAO):
    """Aplica as correções pedidas (todas, se `correcoes` for None), na ordem do QG XML.
    Devolve (total de alterações, mensagens, alterações por correção)."""
    correcoes = set(IDS_CORRECOES if correcoes is None else correcoes)
    cache_ceps = {} if cache_ceps is None else cache_ceps
    etapas = (
        ("encoding", lambda: corrigir_encoding(raiz)),
        ("numero", lambda: preencher_numero_ausente(raiz)),
        ("cmun", lambda: corrigir_cmun(raiz, resolvedor, cache_ceps)),
        ("clocemi", lambda: corrigir_clocemi(raiz, resolvedor)),
        ("clocprestacao", lambda: corrigir_clocprestacao(raiz, resolvedor)),
        ("piscofins", lambda: corrigir_piscofins(raiz, cst_padrao)),
        ("iss", lambda: corrigir_aliquota_iss(raiz)),
        ("competencia", lambda: corrigir_competencia(raiz)),
    )
    mensagens, por_correcao = [], {}
    for identificador, aplicar in etapas:
        if identificador not in correcoes:
            continue
        quantidade, novas = aplicar()
        por_correcao[identificador] = quantidade
        mensagens.extend(novas)
    return sum(por_correcao.values()), mensagens, por_correcao
