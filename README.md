<div align="center">

# ⚡ MEGA QG VIVO — Central de Operações Fiscais

**Automação em lote das operações fiscais da Vivo: NFCom, NFSe, NFCe e relatórios num só app.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-2dd4bf)
![Versão](https://img.shields.io/badge/vers%C3%A3o-v3.9-7c3aed)
![Status](https://img.shields.io/badge/status-em%20produ%C3%A7%C3%A3o-33d17a)
![License](https://img.shields.io/badge/license-privado%20%2F%20interno-8890a6)

[Visão geral](#-visão-geral) •
[Operações](#-operações) •
[Interface](#-interface) •
[Arquitetura](#️-arquitetura) •
[LGPD e segurança](#-lgpd-e-segurança) •
[Changelog](#-changelog)

</div>

---

## 📌 Visão geral

O MegaQG Vivo reúne as ferramentas internas de automação fiscal da Vivo, criadas para tirar do manual (e do erro
humano) operações repetitivas de alto volume feitas contra a SEFAZ, prefeituras, WebHooks e integrações fiscais
internas.

Até a v2.x eram dois apps separados (**MEGA QG VIVO NFCom** e **MEGA QG VIVO NFSe**). A partir da **v3.0** eles
viraram um app desktop único, o **MegaQG Vivo**, com hub, barra lateral, ambiente Produção/Homologação global e
novas áreas (NFCe e Relatórios).

| Área | Operações | Desde |
|---|---|---|
| NFCom | 5 | v2.0 (app único desde v3.0) |
| NFSe | 6 | v2.0 (app único desde v3.0) |
| NFCe | 3 | v3.2 |
| Relatórios | 1 | v3.0 |

### O que há neste repositório

Este é o repositório **público e sanitizado** do projeto: documentação e versões antigas compiladas. O código-fonte
atual e o executável v3.x ficam em repositório privado, porque o executável é distribuído com a configuração da rede
interna e só circula dentro da empresa.

```
README.md                    # esta documentação (v3.9)
Vivo MegaQG (NFCom).exe      # legado: QG NFCom v2.2, app separado
Vivo MegaQG (NFSe).exe       # legado: QG NFSe v2.1, app separado
vivo.ico                     # ícone
```

---

## 🧾 Operações

### NFCom

| Operação | O que faz |
|---|---|
| 🔎 **Consulta SEFAZ** | Verifica em lote o status de chaves NFCom, separando **SVRS** (fila compartilhada) e **MG / MS / MT** (SEFAZ própria), cada grupo com seu ritmo e pausas, e ETA em tempo real. Desde a v3.8, as chaves que voltam **HTTP 422** têm o ID localizado no banco e são reenviadas automaticamente em lotes de até 100, com o código HTTP de cada lote no log. |
| 🛑 **Cancelamento de Notas** | Dispara eventos de cancelamento (`110111`) em lote, com **confirmação obrigatória** mostrando o ambiente antes de qualquer requisição. |
| 📥 **Download de XMLs** | Baixa XMLs em lote a partir de uma lista de IDs, registrando as falhas para reprocessamento. |
| 🔁 **Reenvio à SEFAZ** | Reenvia XMLs de uma pasta. Desde a v3.4, o XML do qual não dá para extrair a chave não é mais ignorado: o nome do arquivo (ID do documento) é reenviado pela API de reenvio por ID. |
| 🔔 **Reenvio de WebHook** | Cria (opcional) e reenvia webhooks por subscrição, com relatório de quantos eventos foram reenviados. |

### NFSe

| Operação | O que faz |
|---|---|
| 📥 **Download de XMLs** | Lote simples ou **separado por endereço** (subpastas `COM CEP` / `SEM CEP`). |
| 📊 **Relatório DPS sem Endereço** | Gera `.xlsx` com **uma linha por DPS** (XMLs repetidos da mesma DPS viram uma linha só) e uma aba pronta para o preenchimento do endereço. Nome padrão `Planilha -dd-mm-aaaa.xlsx`. |
| 🧩 **Expandir DPS no CSV** | "Explode" uma coluna com valores separados por vírgula em uma linha por valor; delimitador, coluna e codificação configuráveis. |
| 🔁 **Reenvio de XML** | Reenvia XMLs de uma pasta, guardando a lista dos que falharem. |
| 🔍 **Consulta DPS** | Consulta em lote o status de DPS junto à prefeitura. |
| 🛠️ **Correção de XMLs (QG XML)** | Novo na v3.5. Oito correções em lote, cada uma desligável: caracteres corrompidos, número do endereço, `cMun` pelo CEP, `cLocEmi`, `cLocPrestacao`, PIS/COFINS (com arredondamento fiscal), alíquota de ISS e competência. A pasta de entrada nunca é alterada; só as notas corrigidas são gravadas e as que precisam de ajuste manual vão para pastas separadas. CEP resolvido por APIs públicas (ViaCEP, BrasilAPI, OpenCEP, AwesomeAPI) e confirmado no IBGE. |

### NFCe

| Operação | O que faz |
|---|---|
| ↩️ **Retorno de Contingência** | Piloto. Autorizada ou Rejeitada, escolhida na tela. Prévia somente leitura, **simulação com ROLLBACK**, confirmação e gravação em blocos de 1.000 com uma transação por bloco. |
| 📥 **Download de XMLs** | Download em massa por chave de acesso. |
| ♻️ **Reprocessamento** | Baixa o XML por chave, marca a nota para reprocessamento e reenvia o XML completo. Prévia, simulação, confirmação e log de HTTP e `cStat` por nota. |

### Relatórios

| Operação | O que faz |
|---|---|
| 📑 **Exportador de Relatório** | Por dia ou período único, todas as notas ou só canceladas, XML opcional. Também roda pelo terminal (`--cli`). |

Todas as operações têm barra de progresso, log colorido por status (`OK` / `INFO` / `WARN` / `ERROR`), contadores
em tempo real, log em arquivo e botão **Parar** (que respeita as requisições já em voo).

---

## 🎨 Interface

- **Hub** com as seções NFCom, NFSe, NFCe e Relatórios, busca de operação e cards que mostram o status
  (Pronto / Configurar) e o que falta configurar. Grade responsiva de 3, 2 ou 1 coluna.
- **Barra lateral** para trocar de operação sem voltar ao início; recolhe para só os ícones (Ctrl+B).
- **Ambiente global** (Produção/Homologação) no topo, com indicador discreto na cor do ambiente. Não troca com uma
  operação rodando.
- **Temas**: 7 prontos (Nebulosa, Neon, Aurora, Violeta, Grafite, Clássico e Claro) e temas criados pelo usuário,
  com editor de cores e prévia. A escolha fica nas preferências de cada usuário.
- **Pokémon andando** no início: os 50 mais icônicos, com animações de andar, golpe e pulo em 8 direções, sempre
  em volta do conteúdo e nunca por cima dos cards. Seguem o ponteiro, pulam quando clicados e se cumprimentam. O
  clique é só observado, nunca consumido. Sprites do
  [PMD SpriteCollab](https://github.com/PMDCollab/SpriteCollab) (CC BY-NC 4.0).
- **Animações** leves: transições de cor, cards que entram em sequência, telas que deslizam, troca de tema com
  esmaecimento. Nenhuma recalcula o layout.
- **Visão para o cliente** (v3.9): para compartilhar a tela, troca a logo e o ícone pelos da Vivo e esconde todos
  os Pokémon, na hora e sem perder nada preenchido.
- **Movimento reduzido**: a opção "Animações e Pokémon" desliga transições e Pokémon.
- **DPI awareness** para texto nítido em 125%/150%.

---

## 🏗️ Arquitetura

```
main.py           entrada (--cli: exportador no terminal; --autoteste: abre todas as telas)
core/             configuração, preferências, banco, log, XML, versão
ui/               temas, animações, Pokémon, widgets, hub e janela
modulos/          uma pasta por operação: engine.py (lógica) + page.py (tela)
  nfcom/  nfse/  nfce/  exportador_relatorio/
tests/            testes sem VPN, com HTTP e banco simulados
tools/            porte dos QGs originais, empacotamento, diagnóstico
```

- **Engine ↔ GUI desacoplada**: cada operação roda numa `Thread` com `ThreadPoolExecutor` e fala com a tela só
  por uma `queue.Queue` consumida via `widget.after()`. As engines não dependem do Tkinter.
- **Porte sem alterar a lógica**: as operações dos QGs v2.x foram extraídas automaticamente dos apps originais;
  só as que ganharam comportamento novo passaram a ser mantidas à mão.
- **Registro único de operações**: hub, busca e barra lateral leem da mesma lista.
- **Testes**: mais de 45 casos de engine com HTTP/banco simulados e um teste de interface que abre todas as telas
  em todos os temas.
- **Executável** gerado com PyInstaller.

---

## 🔒 LGPD e segurança

- **Nenhuma URL, host, porta ou senha fica no código-fonte nem no git.** Tudo é carregado em runtime de um
  `config.json` local (fora do versionamento) ou de variáveis de ambiente `MEGAQG_*`, que têm prioridade.
- Cada commit passa por uma varredura de segredos antes de ser enviado.
- Sem configuração, o app abre normalmente; cada card indica o que falta e a operação avisa em vez de travar.
- O executável v3.x contém a configuração da rede interna e **não é distribuído fora da empresa**, por isso não
  está neste repositório.
- **Saídas com dados pessoais** (planilhas, CSVs e XMLs com CPF, nome e endereço de clientes) e **logs de
  execução** (que registram respostas de API) nunca são versionados.
- As únicas chamadas externas fixas no código são a serviços públicos (CEP, CNPJ e IBGE).

---

## 📝 Changelog

### MegaQG Vivo (app único)

**v3.9**
- Visão para o cliente: logo e ícone da Vivo e nenhum Pokémon, para compartilhar a tela.

**v3.8**
- NFCom, Consulta SEFAZ: chaves com HTTP 422 são reenviadas automaticamente pelo ID, em lotes de até 100.
  Novos contadores REENVIADAS e REENVIO C/ ERRO.
- A opção "Animações e Pokémon" passa a valer acima da configuração do Windows (Área de Trabalho Remota não
  desliga mais as animações).

**v3.7**
- 50 Pokémon com sprites animados em 8 direções, interações com o mouse e revezamento pelas laterais.

**v3.6**
- Layout do início estável (os cards não "pulam" mais ao trocar de tema), grade responsiva e animações.
- NFSe, Relatório DPS sem Endereço: uma linha por DPS e nome padrão com a data.

**v3.5**
- NFSe: nova operação Correção de XMLs (QG XML), com oito correções em lote.

**v3.4**
- NFCom, Reenvio à SEFAZ: XML sem chave legível é reenviado pelo ID do arquivo.
- NFCe: Retorno de Contingência unificado, Download de XMLs e Reprocessamento por chave.
- Temas (7 prontos + criados pelo usuário), barra lateral recolhível, rolagem pelo mouse em qualquer ponto.

**v3.2**
- NFCe (piloto): Retorno de Contingência, com prévia, simulação com ROLLBACK e gravação em blocos.

**v3.1**
- Acabamento de tema em todos os widgets, DPI awareness, telas com rolagem, pasta de log fixa.

**v3.0**
- Integração do QG NFCom e do QG NFSe num app único, com hub, barra lateral, ambiente global e o Exportador de
  Relatório.

### QGs separados (legado, exes neste repositório)

**NFCom v2.2 / NFSe v2.1**
- Nenhuma URL interna no código-fonte: endpoints via `config.json` ou variáveis de ambiente.

**NFCom v2.1**
- Homologação na Consulta SEFAZ, Cancelamento e Reenvio de WebHook; MG/MS/MT em 30 notas a cada 2 min; ETA.

**NFCom v2.0 / NFSe v2.0**
- Central única de cada documento fiscal, com tema dark, paralelização e log em arquivo.

---

<div align="center">

Feito por **Bruno Siqueira** ([@brunosiqp](https://github.com/brunosiqp)) com
**Abel Fonseca** ([@Ab3lFonseca](https://github.com/Ab3lFonseca))

</div>
