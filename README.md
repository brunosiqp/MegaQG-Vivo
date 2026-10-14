# MegaQG Vivo

[Português](#português) · [English](#english)

## Português

Central de operações fiscais da Vivo: o **MEGA QG VIVO NFCom**, o **MEGA QG VIVO NFSe** e o **Exportador de
Relatório** num só app desktop (`MegaQGVivo.exe`), com hub, barra lateral e ambiente Produção/Homologação único.

> **Repositório público e sanitizado (LGPD).** Aqui estão o código-fonte e um `MegaQGVivo.exe` compilado **sem**
> `config.json`: nenhum endereço, host, senha ou dado de cliente. Para usar, coloque um `config.json` (a partir do
> `config.example.json`) ao lado do exe. Os documentos internos de implantação não são publicados. Os exes
> `Vivo MegaQG (NFCom).exe` e `Vivo MegaQG (NFSe).exe` são os QGs separados da v2.x (legado).

### Operações

| Área | Operação | Pasta |
|---|---|---|
| NFCom | Consulta SEFAZ (SVRS / MG / MS / MT; chave com HTTP 422 é reenviada pelo ID) | `modulos/nfcom/consulta_sefaz/` |
| NFCom | Cancelamento de Notas (110111, com confirmação obrigatória) | `modulos/nfcom/cancelamento/` |
| NFCom | Download de XMLs | `modulos/nfcom/download_xmls/` |
| NFCom | Reenvio à SEFAZ (XML sem chave é reenviado pelo ID do arquivo) | `modulos/nfcom/reenvio_sefaz/` |
| NFCom | Reenvio de WebHook | `modulos/nfcom/reenvio_webhook/` |
| NFSe | Download de XMLs (lote ou COM/SEM CEP) | `modulos/nfse/download_xmls/` |
| NFSe | Relatório DPS sem Endereço (.xlsx, uma linha por DPS, nome padrão `Planilha -dd-mm-aaaa`) | `modulos/nfse/relatorio_dps/` |
| NFSe | Expandir DPS no CSV | `modulos/nfse/expandir_csv/` |
| NFSe | Reenvio de XML | `modulos/nfse/reenvio_xml/` |
| NFSe | Consulta DPS | `modulos/nfse/consulta_dps/` |
| NFSe | Correção de XMLs (QG XML): encoding, endereço, cMun pelo CEP, cLocEmi, cLocPrestacao, PIS/COFINS, ISS e competência | `modulos/nfse/correcao_xml/` |
| NFCe | Retorno de Contingência: Autorizada (Retorno Cupom) ou Rejeitada, escolhida na tela — piloto | `modulos/nfce/retorno_contingencia/` |
| NFCe | Download de XMLs em massa por chave de acesso | `modulos/nfce/download_xmls/` |
| NFCe | Reprocessamento por chave: baixa o XML, grava `IND_STATUS_NFE = 3` e reenvia o XML completo | `modulos/nfce/reprocessamento/` |
| Relatórios | Exportador de Relatório: por dia ou período único, todas ou só canceladas, XML opcional | `modulos/exportador_relatorio/` |

As operações NFCom e NFSe foram portadas dos QGs originais **sem alterar a lógica** (`tools/portar_qgs.py` extrai cada
classe do `qg.py` original). Mudou só o necessário para viverem juntas: ambiente global, volta ao hub e, no NFSe,
URLs lidas do `config.json` com Produção e Homologação.

A exceção é o **Reenvio à SEFAZ**, mantido à mão desde a v3.3: o XML do qual não dá para extrair a chave (sem
`<chNFCom>`, malformado ou ilegível) não é mais ignorado. O nome do arquivo é o ID do documento no banco
(`123456.xml`), e esse ID é reenviado pela API de reenvio por ID (`reenvio_sefaz_id_url_prd/_hml`) com o corpo JSON
`[ID]`. O código HTTP de cada retorno (200, 422, 500...) aparece no log de execução. Só continua ignorado o arquivo
cujo nome não é um ID numérico.

A **Consulta SEFAZ** também é mantida à mão, desde a v3.8: terminada a consulta, as chaves que voltaram **HTTP 422**
têm o ID buscado no banco do NFCom (`SELECT id FROM documento_fiscal WHERE chave_nf = <chave>`, ver
`modulos/nfcom/banco.py`) e são reenviadas pela API `checksefaz_reenvio_url_prd/_hml` (`.../Helper/documents/resend`),
num POST com o corpo JSON `[id, id, ...]`, em lotes de até 100. O código HTTP de cada lote aparece no log; um lote que
volta 422 (ou outro erro) fica registrado e o reenvio segue com os próximos. Chave que não está no banco aparece no
log como "sem ID". O banco de Produção usa as chaves `relatorio_db_*` do Exportador quando as `nfcom_db_*` estão
vazias; Homologação precisa de `nfcom_db_server_hml` e `nfcom_db_database_hml`.

A **Correção de XMLs** de NFSe (v3.5) é o QG XML v4 trazido para o app: não veio do `qg.py` e não passa pelo porte.
As oito correções estão em `modulos/nfse/correcao_xml/correcoes.py` e a consulta de CEP em `cep.py`. Em relação ao
script original: `cLocEmi` e `cLocPrestacao` passaram a funcionar em XML com `xmlns` e pelo CNPJ do emitente, o
PIS/COFINS usa arredondamento fiscal e o arquivo é regravado sem trocar os namespaces por `ns0:`. As APIs de CEP,
CNPJ e IBGE são serviços públicos da internet, por isso ficam no código. Os caches de CEP ficam em
`%APPDATA%\MegaQGVivo` e o histórico das notas em `C:\ScriptPS\logs\nfse_correcao_xml_historico.txt`.

O **Relatório DPS sem Endereço** também é mantido à mão desde a v3.6: a planilha tem **uma linha por DPS** (a chave
é o `Id` de `<infDPS>`; XMLs repetidos da mesma DPS viram uma linha só, com valores diferentes juntados com ` | `),
a aba "DPS sem endereço" (DPS, Nome, CPF) e a aba "Dados de endereço" (a mesma DPS com CEP,
código do município, logradouro, número, complemento e bairro do tomador e o nome do arquivo). O nome padrão do
arquivo é `Planilha -dd-mm-aaaa.xlsx`, com a data do momento em que a planilha é gerada.

### Interface

- **Hub** com seções NFCom, NFSe, NFCe e Relatórios, busca de operação e cards que mostram o que falta no
  `config.json`.
- **Barra lateral** para trocar de operação sem voltar ao início. A seta no meio da borda da barra (ou Ctrl+B)
  recolhe a barra para só os ícones e a mostra de novo.
- **Ambiente no topo** (Produção/Homologação) valendo para todas as telas, com indicador discreto na cor do
  ambiente (linha fina e seletor contornado). Não dá
  para trocar com uma operação rodando. O Cancelamento mostra o ambiente na confirmação.
- **Temas** no botão "Tema" do topo: 7 prontos (Nebulosa, Neon, Aurora, Violeta, Grafite, Clássico e Claro) e os
  criados pelo usuário, com editor de cores e prévia. Trocar de tema recria as telas abertas, por isso não troca
  com uma operação rodando. A escolha é de cada usuário e fica em `%APPDATA%\MegaQGVivo\preferencias.json`, fora
  do `config.json`.
- **Roda do mouse** rola a tela (e a barra lateral) em qualquer ponto; num log, rola o log até o fim e depois a
  tela.
- **Grade responsiva** no início: 3, 2 ou 1 coluna de cards conforme a largura, sem nada fora da área visível.
- **Pokémon andando** (`ui/pokemon.py`): os 50 mais icônicos andam sem parar pelo início, com as animações de
  andar, golpe e pulo em 8 direções, só em volta do bloco central (título, busca e dica) e nas margens dos cards,
  nunca por cima deles. A quantidade acompanha o espaço livre e eles se revezam pelas laterais. Interações: com o
  mouse bem perto, alguns seguem o ponteiro por alguns segundos (os outros pulam com um balão); com Pokémon
  seguindo, cada clique vira um golpe deles na direção do ponteiro; clicar em um faz ele pular; dois que se
  encontram se cumprimentam. O clique é só observado (nunca consumido), então tudo funciona igual por baixo deles.
  Cada tela tem um Pokémon pequeno andando no canto do cabeçalho, que pula com o mouse e golpeia quando clicado. Só
  se mexem com a tela à vista, e só os que estão na tela ficam carregados na memória. Os sprites são do
  [PMD SpriteCollab](https://github.com/PMDCollab/SpriteCollab) (CC BY-NC 4.0), preparados por
  `tools/preparar_pokemon.py` em `assets/pokemon/`; créditos em `assets/pokemon/CREDITOS.md`.
- **Animações** (`ui/animacao.py`): transições de cor no hover, cards que entram em sequência e sobem ao passar o
  mouse, tela que desliza ao abrir, troca de tema com esmaecimento, janelas com fade e contadores que acendem quando
  mudam. Só mudam cor, posição ou a opacidade da janela; nenhuma recalcula o layout.
- **Visão para o cliente** (botão na janela de temas, de propósito fora do topo): para compartilhar a tela, troca a
  logo e o ícone do Pikachu pelos da Vivo (`assets/vivo_logo.png`, `assets/vivo.ico`) e some com todos os Pokémon.
  Vale na hora, sem recriar as telas, e fica guardada nas preferências até ser desligada.
- **Movimento reduzido:** com "Animações e Pokémon" desmarcado na janela de temas as transições viram troca
  direta e os Pokémon ficam parados. Sem escolha nessa opção, vale o Windows (efeitos de animação desligados =
  movimento reduzido), exceto na Área de Trabalho Remota, em que o Windows desliga as animações só para economizar
  banda. Marcar a opção liga as animações mesmo com o Windows desligado. O `--autoteste` registra o estado.

### Estrutura

```
main.py                     entrada (--cli: exportador no terminal; --autoteste: abre todas as telas)
core/config.py              configuração única (config.json + variáveis MEGAQG_*)
core/preferencias.py        aparência de cada usuário (tema, temas criados, barra lateral)
core/                       infra compartilhada (banco, log, CSV em blocos, XML, versão)
ui/                         paleta e estilos (theme.py), temas (temas.py, tema_dialogo.py), animações
                            (animacao.py), Pokémon (pokemon.py), widgets, hub e janela
modulos/registro.py         lista das operações (hub e barra lateral leem daqui)
modulos/nfcom/, nfse/       uma pasta por operação: engine.py (lógica) + page.py (tela)
modulos/exportador_relatorio/
clientes/vivo/config.py     parâmetros do exportador (sem servidor, URL nem senha)
tests/                      testes sem VPN (engines com HTTP/banco simulados, abertura de telas)
tools/                      porte dos QGs, diagnóstico de conexão
```

### Configuração (`config.json`)

**Nenhuma URL, host ou senha fica no código ou no git.** Copie `config.example.json` para `config.json` e preencha.
É o mesmo formato do `config.json` dos QGs originais (um de produção do NFCom continua valendo), com as chaves do NFSe
e do banco do Exportador acrescentadas. Ordem de leitura:

1. variável de ambiente `MEGAQG_<CHAVE>` (ex.: `MEGAQG_DOWNLOAD_URL_PRD`);
2. `config.json` ao lado do `MegaQGVivo.exe` (ou na raiz, rodando como .py): troca endpoint/senha sem recompilar;
3. `config.json` embutido no exe pelo build: o exe roda sozinho no servidor.

### Como rodar

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

O Exportador usa o **ODBC Driver 17 for SQL Server** (driver do Windows) e o banco só responde na rede da empresa.

### Testes

```
.venv\Scripts\python tests\testar_engines.py
.venv\Scripts\python tests\abrir_telas.py
```

No servidor, `MegaQGVivo.exe --autoteste` abre todas as telas e grava o resultado em `C:\ScriptPS\logs\autoteste.txt`.

**Logs:** todas as operações gravam em `C:\ScriptPS\logs` (pasta fixa, não configurável).

### Gerar o .exe

`build.bat` cria o `.venv`, compila `dist\MegaQGVivo.exe` e embute o `config.json` local. Sempre compile pelo
`.venv`: o PyInstaller global (< 6.22.3) gera um exe que quebra com `_tcl_data not found` no Python 3.14. O exe
compilado com um `config.json` preenchido contém a senha do banco: não o distribua fora da rede interna (o deste
repositório foi compilado sem `config.json`).

### Contribuidores

- [Bruno Siqueira (@brunosiqp)](https://github.com/brunosiqp)
- [Abel Fonseca (@Ab3lFonseca)](https://github.com/Ab3lFonseca)

## English

Vivo's tax operations hub: **MEGA QG VIVO NFCom**, **MEGA QG VIVO NFSe** and the **Report Exporter** in a single
desktop app (`MegaQGVivo.exe`), with a hub, a sidebar and one Production/Homologation switch.

> **Public, sanitized repository (LGPD).** It holds the source code and a `MegaQGVivo.exe` built **without**
> `config.json`: no address, host, password or customer data. To use it, put a `config.json` (based on
> `config.example.json`) next to the exe. Internal deployment documents are not published. `Vivo MegaQG (NFCom).exe`
> and `Vivo MegaQG (NFSe).exe` are the separate v2.x QGs (legacy).

### Operations

| Area | Operation | Folder |
|---|---|---|
| NFCom | SEFAZ status check (SVRS / MG / MS / MT; a key that gets HTTP 422 is resent by ID) | `modulos/nfcom/consulta_sefaz/` |
| NFCom | Document cancellation (110111, mandatory confirmation) | `modulos/nfcom/cancelamento/` |
| NFCom | XML download | `modulos/nfcom/download_xmls/` |
| NFCom | Resend to SEFAZ (an XML without a key is resent by the ID in its file name) | `modulos/nfcom/reenvio_sefaz/` |
| NFCom | WebHook resend | `modulos/nfcom/reenvio_webhook/` |
| NFSe | XML download (batch or with/without ZIP code) | `modulos/nfse/download_xmls/` |
| NFSe | DPS without address report (.xlsx, one row per DPS, default name `Planilha -dd-mm-aaaa`) | `modulos/nfse/relatorio_dps/` |
| NFSe | Expand DPS in CSV | `modulos/nfse/expandir_csv/` |
| NFSe | XML resend | `modulos/nfse/reenvio_xml/` |
| NFSe | DPS status check | `modulos/nfse/consulta_dps/` |
| NFSe | XML correction (QG XML): encoding, address, cMun from the ZIP code, cLocEmi, cLocPrestacao, PIS/COFINS, ISS and competence date | `modulos/nfse/correcao_xml/` |
| NFCe | Contingency return: authorized or rejected, chosen on the screen — pilot | `modulos/nfce/retorno_contingencia/` |
| NFCe | Bulk XML download by access key | `modulos/nfce/download_xmls/` |
| NFCe | Reprocessing by access key: downloads the XML, sets `IND_STATUS_NFE = 3` and resends the full XML | `modulos/nfce/reprocessamento/` |
| Reports | Report Exporter: per day or single period, all or cancelled only, optional XML | `modulos/exportador_relatorio/` |

The NFCom and NFSe operations were ported from the original QGs **without changing their logic**
(`tools/portar_qgs.py` extracts each class from the original `qg.py`). Only what they need to live together changed:
the global environment, going back to the hub and, for NFSe, URLs read from `config.json` with Production and
Homologation.

The exception is **Resend to SEFAZ**, maintained by hand since v3.3: an XML whose key cannot be extracted (no
`<chNFCom>`, malformed or unreadable) is no longer skipped. The file name is the document ID in the database
(`123456.xml`), and that ID is resent through the resend-by-ID API (`reenvio_sefaz_id_url_prd/_hml`) with the JSON
body `[ID]`. The HTTP code of each response (200, 422, 500...) shows in the execution log. Only a file whose name is
not a numeric ID is still skipped.

**SEFAZ status check** is also maintained by hand, since v3.8: once the check ends, the keys that got **HTTP 422**
have their ID looked up in the NFCom database (`SELECT id FROM documento_fiscal WHERE chave_nf = <key>`, see
`modulos/nfcom/banco.py`) and are resent through the `checksefaz_reenvio_url_prd/_hml` API
(`.../Helper/documents/resend`), in a POST with the JSON body `[id, id, ...]`, in batches of up to 100. The HTTP code of
each batch shows in the log; a batch that gets 422 (or any other error) is recorded and the resend goes on with the
next ones. A key missing from the database shows in the log as "sem ID". The Production database uses the Report
Exporter's `relatorio_db_*` keys when the `nfcom_db_*` ones are empty; Homologation needs `nfcom_db_server_hml` and
`nfcom_db_database_hml`.

The NFSe **XML correction** (v3.5) is QG XML v4 brought into the app: it did not come from `qg.py` and is not
ported. The eight corrections live in `modulos/nfse/correcao_xml/correcoes.py` and the ZIP code lookup in `cep.py`.
Compared with the original script: `cLocEmi` and `cLocPrestacao` now work on XML with `xmlns` and through the
issuer's CNPJ, PIS/COFINS uses fiscal rounding, and the file is rewritten without turning namespaces into `ns0:`.
The ZIP code, CNPJ and IBGE APIs are public internet services, which is why they are in the code. ZIP code caches
live in `%APPDATA%\MegaQGVivo` and the per-note history in `C:\ScriptPS\logs\nfse_correcao_xml_historico.txt`.

The **DPS without address report** is also maintained by hand since v3.6: the spreadsheet has **one row per DPS**
(keyed by the `<infDPS>` `Id`; repeated XMLs of the same DPS become one row, with differing values joined by ` | `),
the "DPS sem endereço" sheet (DPS, name, CPF) and the "Dados de endereço" sheet (the same DPS
with the taker's ZIP code, city code, street, number, complement and district, plus the file name). The default file
name is `Planilha -dd-mm-aaaa.xlsx`, with the date the spreadsheet is generated.

### Interface

- **Hub** with NFCom, NFSe, NFCe and Reports sections, operation search and cards showing what is missing in
  `config.json`.
- **Sidebar** to switch operations without going back home. The arrow in the middle of its edge (or Ctrl+B)
  collapses it to icons only and opens it again.
- **Environment switch** (Production/Homologation) at the top for every screen, with a subtle indicator in the
  environment color (thin line and outlined selector). It
  cannot change while an operation runs. Cancellation shows the environment in its confirmation.
- **Themes** under the "Tema" button at the top: 7 built-in ones (Nebulosa, Neon, Aurora, Violeta, Grafite,
  Clássico and Claro) plus user-made themes, with a color editor and live preview. Switching themes rebuilds the
  open screens, so it is blocked while an operation runs. The choice is per user and lives in
  `%APPDATA%\MegaQGVivo\preferencias.json`, outside `config.json`.
- **Mouse wheel** scrolls the screen (and the sidebar) from anywhere; over a log it scrolls the log to its end and
  then the screen.
- **Responsive grid** on the home screen: 3, 2 or 1 column of cards depending on the width, nothing off screen.
- **Walking Pokémon** (`ui/pokemon.py`): the 50 most iconic ones keep walking around the home screen, with walk,
  attack and hop animations in 8 directions, only around the central block (title, search and hint) and in the
  margins beside the cards, never over them. How many are shown follows the free space, and they take turns through
  the sides. Interactions: with the pointer very close, some follow it for a few seconds (the others hop with a
  bubble); while some are following, every click becomes an attack of theirs towards the pointer; clicking one makes
  it hop; two that meet greet each other. Clicks are only observed (never consumed), so everything under them works
  as before. Every screen has a small Pokémon walking in a corner of its header that hops on hover and attacks when
  clicked. They only move while visible, and only the ones on screen stay loaded in memory. Sprites come from
  [PMD SpriteCollab](https://github.com/PMDCollab/SpriteCollab) (CC BY-NC 4.0), prepared by
  `tools/preparar_pokemon.py` into `assets/pokemon/`; credits in `assets/pokemon/CREDITOS.md`.
- **Animations** (`ui/animacao.py`): hover color transitions, cards entering in sequence and lifting on hover,
  screens sliding in, theme switch behind a fade, windows fading in and out, and counters lighting up when they
  change. They only change color, position or window opacity; none of them recomputes the layout.
- **Client view** (button in the theme window, on purpose not in the top bar): for screen sharing, it swaps the
  Pikachu logo and icon for the Vivo ones (`assets/vivo_logo.png`, `assets/vivo.ico`) and hides every Pokémon. It
  applies at once, without rebuilding the screens, and stays saved in the preferences until turned off.
- **Reduced motion:** with "Animações e Pokémon" unchecked in the theme window, transitions become instant and the
  Pokémon stand still. Without a choice there, Windows decides (animation effects off = reduced motion), except in a
  Remote Desktop session, where Windows turns animations off only to save bandwidth. Checking the option turns
  animations on even when Windows has them off. `--autoteste` records the state.

### Layout

```
main.py                     entry point (--cli: exporter in the terminal; --autoteste: opens every screen)
core/config.py              single configuration (config.json + MEGAQG_* variables)
core/preferencias.py        per-user appearance (theme, user-made themes, sidebar)
core/                       shared infrastructure (database, logging, chunked CSV, XML, version)
ui/                         palette and styles (theme.py), themes (temas.py, tema_dialogo.py), animations
                            (animacao.py), Pokémon (pokemon.py), widgets, hub and window
modulos/registro.py         operation list (hub and sidebar read from it)
modulos/nfcom/, nfse/       one folder per operation: engine.py (logic) + page.py (screen)
modulos/exportador_relatorio/
clientes/vivo/config.py     exporter parameters (no server, URL or password)
tests/                      tests without VPN (engines with mocked HTTP/database, screen opening)
tools/                      QG port, connection diagnostics
```

### Configuration (`config.json`)

**No URL, host or password lives in the code or in git.** Copy `config.example.json` to `config.json` and fill it in.
It is the same format as the original QGs' `config.json` (an NFCom production one still works), plus the NFSe and
exporter database keys. Lookup order:

1. environment variable `MEGAQG_<KEY>` (e.g. `MEGAQG_DOWNLOAD_URL_PRD`);
2. `config.json` next to `MegaQGVivo.exe` (or at the root, running from source): change endpoints/password without
   rebuilding;
3. `config.json` embedded in the exe by the build: the exe runs standalone on the server.

### Running

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

The exporter needs the **ODBC Driver 17 for SQL Server** (Windows driver) and the database is only reachable on the
company network.

### Tests

```
.venv\Scripts\python tests\testar_engines.py
.venv\Scripts\python tests\abrir_telas.py
```

On the server, `MegaQGVivo.exe --autoteste` opens every screen and writes the result to `C:\ScriptPS\logs\autoteste.txt`.

**Logs:** every operation writes to `C:\ScriptPS\logs` (fixed folder, not configurable).

### Building the .exe

`build.bat` creates `.venv`, builds `dist\MegaQGVivo.exe` and embeds the local `config.json`. Always build through
`.venv`: the global PyInstaller (< 6.22.3) produces an exe that fails with `_tcl_data not found` on Python 3.14. The
exe built with a filled `config.json` contains the database password: do not distribute it outside the internal
network (the one in this repository was built without `config.json`).

### Contributors

- [Bruno Siqueira (@brunosiqp)](https://github.com/brunosiqp)
- [Abel Fonseca (@Ab3lFonseca)](https://github.com/Ab3lFonseca)
