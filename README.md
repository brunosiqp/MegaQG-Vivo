<div align="center">

# ⚡ MEGA QG VIVO — Central de Operações Fiscais

**Automação em lote das operações fiscais da Vivo: NFCom e NFSe num só lugar.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-2dd4bf)
![Status](https://img.shields.io/badge/status-em%20produção-33d17a)
![License](https://img.shields.io/badge/license-privado%20%2F%20interno-8890a6)

[Visão geral](#-visão-geral) •
[MEGA QG NFCom](#-mega-qg-vivo-nfcom) •
[MEGA QG NFSe](#-mega-qg-vivo-nfse) •
[Instalação](#-instalação) •
[Changelog](#-changelog)

</div>

---

## 📌 Visão geral

Este repositório reúne as ferramentas internas de automação fiscal da Vivo, criadas para tirar do manual (e do erro humano) operações repetitivas de alto volume feitas contra os ambientes de SEFAZ, WebHooks e integrações fiscais internas.

Cada "QG" é um app desktop (Tkinter, tema dark) que centraliza várias operações que antes eram scripts avulsos (`main.py`, `Itgr.py`, `CancelamentoMassivoNFCom_v2.2.0.py`, etc.) rodados um a um, sem interface, sem progresso visual e sem log padronizado.

| QG | Documento fiscal | Status |
|---|---|---|
| [MEGA QG VIVO NFCom](#-mega-qg-vivo-nfcom) | Nota Fiscal de Comunicação | ✅ Em produção — v2.1 |
| [MEGA QG VIVO NFSe](#-mega-qg-vivo-nfse) | Nota Fiscal de Serviço Eletrônica | ✅ v2.0 — mesma base do NFCom |

Além dos apps desktop, existe também uma **versão web (Flask) do QG NFCom** em desenvolvimento, pensada para rodar como serviço interno acessível pelo navegador em vez de exigir instalação local — veja [`/front-web`](./front-web) (em progresso).

---

## 🧾 MEGA QG VIVO NFCOM

App único reunindo 5 operações fiscais de NFCom que antes eram scripts separados.

### Módulos

| Módulo | O que faz |
|---|---|
| 🔎 **Consulta SEFAZ** | Verifica em lote o status de processamento de chaves NFCom, dividindo automaticamente entre os grupos **SVRS** (fila compartilhada) e **MG / MS / MT** (UFs com SEFAZ própria), cada um com seu próprio ritmo de envio e pausas obrigatórias. |
| 🛑 **Cancelamento de Notas** | Dispara eventos de cancelamento (`110111`) em lote a partir de uma lista de chaves, com **modal de confirmação obrigatória** antes de qualquer requisição — ação irreversível junto ao SEFAZ. |
| 📥 **Download de XMLs** | Baixa em lote os XMLs de notas NFCom a partir de uma lista de IDs, salvando localmente e registrando falhas num `.txt` separado para reprocessamento. |
| 🔁 **Reenvio à SEFAZ** | Reenvia XMLs de uma pasta local para o ambiente de Produção ou Homologação, extraindo `chNFCom` e UF diretamente do XML. |
| 🔔 **Reenvio de WebHook** | Cria (opcional) e reenvia webhooks por subscrição a partir de uma lista de IDs, com relatório de quantos eventos foram efetivamente reenviados. |

Todos os módulos têm: barra de progresso, log de execução colorido por status (`OK` / `INFO` / `WARN` / `ERROR`), contadores em tempo real, gravação de log em arquivo, e botão de **Parar** (interrompe respeitando requisições já em voo).

### Destaques técnicos

- **Arquitetura de página única (Tk)**: um container troca "páginas" via `tkraise()` — sem abrir janelas novas, sem travar a UI.
- **Engine ↔ GUI desacoplada**: cada operação roda numa `Thread` própria com `ThreadPoolExecutor` internamente, e conversa com a interface só através de uma `queue.Queue` consumida via `widget.after()`. Isso significa que a lógica de negócio (as classes `*Engine`) não depende do Tkinter — dá pra reusar em outro front (é exatamente o que a versão web faz).
- **Consulta SEFAZ com controle de fila por grupo**: SVRS processa em lotes de 2 chaves a cada 3s; MG/MS/MT processam em lotes de 30 chaves a cada 2 minutos (ver [Changelog](#-changelog) — limite ajustado na v2.1).
- **ETA em tempo real**: o card de resumo da Consulta SEFAZ mostra o tempo estimado de conclusão, recalculado a cada lote processado com base no throughput real observado (não é uma estimativa fixa).
- **Ambientes PRD/HML**: todos os 5 módulos suportam Produção e Homologação, com a URL correspondente escolhida automaticamente.

### Estrutura

```
qg.py                  # App completo: engines + páginas + tema dark, tudo num arquivo
```

### Como rodar

```bash
pip install requests
python qg.py
```

Sem dependências além do `requests` — Tkinter já vem com o Python padrão.

---

## 🧾 MEGA QG VIVO NFSE

App único reunindo 5 operações fiscais de NFSe, construído na mesma base arquitetural do QG de NFCom — mesmo padrão de engine (`Queue` + `ThreadPoolExecutor` + tema dark), com cor de assinatura própria (ciano) pra diferenciar visualmente dos dois QGs.

### Módulos

| Módulo | O que faz |
|---|---|
| 📥 **Download de XMLs** | Baixa XMLs em lote por lista de IDs. Tem 2 modos, escolhidos por rádio: **lote simples** (salva tudo direto na pasta de destino) ou **separar por endereço** (cria automaticamente as subpastas `COM CEP` / `SEM CEP`, verificando se `toma/end` e `dest/end` têm CEP, logradouro, número e bairro preenchidos no XML). |
| 📊 **Relatório DPS sem Endereço** | Lê os XMLs de uma pasta (tipicamente a saída "SEM CEP" do módulo acima), extrai `nDPS` + nome/CPF do tomador, agrupa por cliente (juntando as DPS repetidas separadas por vírgula) e gera uma planilha `.xlsx` com 2 abas: os dados encontrados + uma aba em branco pronta pro preenchimento manual do endereço. |
| 🧩 **Expandir DPS no CSV** | Pega um CSV — normalmente a planilha do módulo acima já preenchida com o endereço — onde uma coluna tem vários valores separados por vírgula, e "explode" em uma linha por valor, duplicando as demais colunas. Delimitador, nome da coluna e codificação de entrada (Windows-1252, UTF-8, UTF-8 com BOM) configuráveis na tela. |
| 🔁 **Reenvio de XML** | Reenvia em lote os XMLs de uma pasta local para o endpoint de processamento, salvando a lista dos que falharem em `xml_com_erro_nfse.txt` para reprocessamento. |
| 🔍 **Consulta DPS** | Consulta em lote o status de processamento de identificadores DPS junto à prefeitura, com log de status HTTP + resposta de cada consulta. |

Todos os módulos têm: barra de progresso, log de execução colorido por status, contadores em tempo real, gravação de log em arquivo, e botão de **Parar**.

### Destaques técnicos

- **Mesma arquitetura do NFCom**: página única via `tkraise()`, engines desacopladas da GUI via `Queue` + `Thread`/`ThreadPoolExecutor`, tema dark idêntico na estrutura (cards em `Canvas`, cor de assinatura própria — ciano `#22d3ee`).
- **Paralelização adicionada em cima dos scripts originais**: os 4 scripts que deram origem a este QG (`Baixar_XMLs.py`, `baixarxmlcomsemcep.py`, `Reenviar_XML.py`, `Consulta_DPS.py`) rodavam sequencialmente; aqui cada um ganhou `ThreadPoolExecutor` com número de threads configurável — colocar `Threads = 1` reproduz o comportamento 100% serial original.
- **Geração de planilha sem depender do Excel aberto**: o Relatório DPS sem Endereço usava automação COM do Excel no script original (`Excel.Application`); a versão do QG gera o `.xlsx` direto com `openpyxl`, mais rápido e sem precisar do Excel instalado/aberto por trás.
- **Log adicionado onde não existia**: Download de XMLs, Download COM/SEM CEP e Consulta DPS originalmente só imprimiam no console — agora têm log opcional em arquivo com rastreabilidade completa (status + resposta de cada chamada), no mesmo padrão do NFCom.
- **Endpoint próprio**: as chamadas HTTP do NFSe vão pra porta `30019` (vs. `30016` do NFCom) nos mesmos hosts internos — são serviços fiscais distintos na mesma infraestrutura.

### Estrutura

```
qg_nfse.py             # App completo: engines + páginas + tema dark, mesmo padrão do qg.py
```

### Como rodar

```bash
pip install requests openpyxl
python qg_nfse.py
```

O `openpyxl` só é necessário para o módulo **Relatório DPS sem Endereço** — os outros 4 módulos rodam só com `requests`. Se abrir esse módulo sem a lib instalada, o app avisa com a mensagem de erro pedindo o `pip install openpyxl` em vez de travar sem explicação.

---

## ⚙️ Instalação

Pré-requisitos: **Python 3.10+** (recomendado 3.11+).

```bash
git clone <url-do-seu-repositório>
cd <pasta-do-repositório>
pip install -r requirements.txt   # ou: pip install requests openpyxl
python qg.py         # QG de NFCom
python qg_nfse.py     # QG de NFSe
```

> Os apps fazem chamadas HTTP para hosts internos da Vivo (`svvivowor*`, `svvivohlnx*`). Rode numa máquina/rede com acesso a esses endereços — normalmente a mesma que já usava os scripts avulsos anteriores.

---

## 📝 Changelog

### NFCom

**v2.1**
- Ambiente de Homologação (HML) adicionado em Consulta SEFAZ, Cancelamento de Notas e Reenvio de WebHook (Download de XMLs e Reenvio à SEFAZ já tinham).
- Consulta SEFAZ: limite de processamento de MG/MS/MT ajustado de 60 notas/5min para **30 notas/2min** (SVRS sem alteração).
- Consulta SEFAZ: novo campo de **tempo estimado (ETA)** no card de resumo, atualizado em tempo real.

**v2.0**
- Central única reunindo Consulta SEFAZ, Cancelamento, Download de XMLs, Reenvio à SEFAZ e Reenvio de WebHook num só app com tema dark.

### NFSe

**v2.0**
- Central única reunindo 5 operações fiscais de NFSe (Download de XMLs com modo COM/SEM CEP, Relatório DPS sem Endereço, Expandir DPS no CSV, Reenvio de XML, Consulta DPS), na mesma base arquitetural do QG de NFCom.
- Paralelização (`ThreadPoolExecutor`) adicionada em cima dos 4 scripts originais, que rodavam sequencialmente.
- Geração de planilha do Relatório DPS sem Endereço migrada de automação COM do Excel para `openpyxl`.
- Log em arquivo adicionado aos módulos que originalmente só imprimiam no console (Download de XMLs, Download COM/SEM CEP, Consulta DPS).

---

## 🗺️ Roadmap

- [ ] Ambientes PRD/HML no QG de NFSe (atualmente os 5 módulos usam URL fixa — o QG de NFCom já resolveu isso na v2.1, é candidato natural pra próxima leva de melhorias)
- [ ] Confirmar com o time de infra os hosts reais de Homologação adicionados na v2.1 do NFCom (Consulta SEFAZ, Cancelamento, Reenvio de WebHook — atualmente seguem o mesmo padrão de host de módulos já existentes, mas não foram validados contra a infraestrutura real)
- [ ] Finalizar a versão web (Flask) do QG NFCom como alternativa ao app desktop

---

<div align="center">

Feito por **Bruno Siqueira**

</div>
