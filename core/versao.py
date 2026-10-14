"""Versão e novidades do MegaQG Vivo (mostradas no rodapé do hub)."""

APP_NOME = "MegaQG Vivo"
APP_VERSION = "v3.9"

CHANGELOG = {
    "v3.9": [
        "Visão para o cliente, na janela de temas: para compartilhar a tela, troca a logo e o ícone do Pikachu "
        "pelos da Vivo e some com todos os Pokémon (do início e do canto das telas). Vale na hora, sem perder "
        "o que está preenchido, e fica guardada até ser desligada no mesmo botão.",
    ],
    "v3.8": [
        "NFCom, Consulta SEFAZ: a chave que volta HTTP 422 tem o ID buscado no banco (documento_fiscal) e é "
        "reenviada pela API de reenvio (Helper/documents/resend), em lotes com o corpo [id, id, ...]. O código "
        "HTTP de cada lote aparece no log; lote que volta 422 fica registrado e o reenvio segue com os "
        "próximos. Novos contadores: REENVIADAS e REENVIO C/ ERRO.",
        "Pokémon parados em outras máquinas: o app desligava as animações sempre que o Windows estava com os "
        "efeitos de animação desligados, o que é o padrão em Área de Trabalho Remota e em muitos servidores. "
        "Agora a opção \"Animações e Pokémon\" da janela de temas vale acima do Windows, e a Área de "
        "Trabalho Remota não desliga mais as animações.",
    ],
    "v3.7": [
        "Pokémon de verdade: os 50 mais icônicos (iniciais, lendários, míticos e clássicos) andam sem parar pelo "
        "início, para os lados e para cima e para baixo, com a animação de andar em 8 direções (sprites de "
        "Pokémon Mystery Dungeon). Ficam só em volta do título e da busca e nas margens dos cards, nunca por "
        "cima deles, e se revezam: de tempos em tempos um sai pela lateral e outro entra.",
        "Os pequenos aparecem ampliados e os grandes (Lugia, Rayquaza, Ho-Oh...) quase no tamanho original, e a "
        "quantidade na tela acompanha o espaço livre, para o início não ficar poluído.",
        "Interações: passe o mouse bem perto de um e às vezes ele começa a seguir o ponteiro por alguns segundos "
        "(os outros dão um pulinho com um coração ou uma nota). Com Pokémon seguindo, cada clique seu vira um "
        "golpe deles na direção do ponteiro, com uma faísca. Clique em cima de um para ele pular feliz, e repare "
        "quando dois se encontram: param e se cumprimentam.",
        "Cada tela tem um Pokémon pequeno andando de um lado para o outro no canto do cabeçalho, sorteado a cada "
        "vez que a tela abre; ele pula quando o mouse passa e dá um golpe quando é clicado.",
        "Leve: os Pokémon só se mexem com o início à vista (param com o app minimizado ou noutra tela) e ficam "
        "parados com o movimento reduzido.",
    ],
    "v3.6": [
        "Corrigido: em janelas mais estreitas, trocar o tema (ou voltar ao início) fazia os cards e a busca "
        "pularem para o lado. A grade do início agora se ajusta à largura (3, 2 ou 1 coluna) e não sai do lugar.",
        "Pokémon em pixel art: de vez em quando um Pikachu ou um Pidgey atravessa o topo do início, e cada tela "
        "tem um companheiro no canto do cabeçalho (Pikachu, Bulbasaur, Squirtle ou Charmander, conforme a área). "
        "São só decoração: ficam atrás dos textos e dos campos e não atrapalham nenhum clique.",
        "Animações suaves: cards que entram em sequência e sobem ao passar o mouse, transição ao abrir uma tela, "
        "troca de tema com esmaecimento, janelas que abrem e fecham com fade e contadores que acendem quando mudam.",
        "Movimento reduzido: se o Windows estiver com os efeitos de animação desligados, ou se a opção "
        "\"Animações e Pokémon\" for desmarcada na janela de temas, nada se move.",
        "NFSe, Relatório DPS sem Endereço: uma linha por DPS (antes as DPS de um mesmo cliente ficavam juntas "
        "numa linha), abas \"DPS sem endereço\" e \"Dados de endereço\" (agora com os dados "
        "de endereço do XML) e nome padrão \"Planilha -dd-mm-aaaa\" com a data do dia.",
    ],
    "v3.5": [
        "NFSe: Correção de XMLs (QG XML). Corrige em lote os XMLs de DPS de uma pasta: caracteres corrompidos, "
        "número do endereço, cMun pelo CEP, cLocEmi, cLocPrestacao, PIS/COFINS, alíquota do ISS e data de "
        "competência. Cada correção pode ser desmarcada; só as notas alteradas são salvas, as que dependem de "
        "correção manual vão para pastas separadas e todas as alterações ficam no histórico.",
    ],
    "v3.4": [
        "Visual novo, mais limpo: linhas finas, títulos leves, contadores e cartões redesenhados.",
        "Temas: 7 prontos (Nebulosa, Neon, Aurora, Violeta, Grafite, Clássico e Claro) no botão Tema, no topo.",
        "Crie o seu tema: parta de qualquer tema, escolha cada cor com prévia na hora, salve, edite ou exclua. "
        "A escolha fica guardada para o seu usuário.",
        "A roda do mouse rola a tela em qualquer ponto dela (antes só com o ponteiro fora dos campos e botões).",
        "A barra lateral pode ser recolhida para só os ícones: a seta no meio da borda dela (ou Ctrl+B) "
        "recolhe e mostra a barra.",
    ],
    "v3.3": [
        "NFCom Reenvio à SEFAZ: XML sem chNFCom (ou ilegível) não é mais ignorado. O documento é reenviado "
        "pelo ID, que é o nome do arquivo, e o código HTTP do retorno (200, 422, 500...) aparece no log.",
        "NFCe: Retorno Cupom (Autorizada) e Retorno de Rejeitados numa tela só, com o tipo escolhido na tela.",
        "NFCe: Download de XMLs em massa a partir de um .txt de chaves de acesso.",
        "NFCe: Reprocessamento a partir de um .txt de chaves. Baixa o XML, muda o IND_STATUS_NFE da nota "
        "para 3 e reenvia o XML completo, com prévia no banco, simulação e o código HTTP de cada envio no log.",
        "Ícone e logo do Pikachu de volta.",
    ],
    "v3.2": [
        "NFCe (piloto): Retorno Cupom (Autorizada) e Retorno de Rejeitados. Lê um .txt de chaves "
        "(A_ID), mostra a prévia no banco (inseridas, não encontradas, status divergente, já pendentes), "
        "permite simular sem gravar e grava os comandos na COMANDO_NFEPACK em blocos, com confirmação.",
    ],
    "v3.1": [
        "Ícone e logo da Vivo no lugar do Pikachu.",
        "Logs de todas as operações fixos em C:\\ScriptPS\\logs.",
        "Visual revisado em todas as telas: campos, listas, botões, caixas de seleção e barras de "
        "rolagem no tema escuro; texto nítido em telas com escala de 125%/150%; telas rolam quando o "
        "conteúdo não cabe na janela; confirmação do Cancelamento centralizada.",
        "O ambiente aparece em cada tela e só se troca no topo do app (antes cada tela tinha um seletor).",
        "Reenvio de WebHook: o card só fica Pronto com as URLs de criação e de reenvio configuradas.",
    ],
    "v3.0": [
        "MEGA QG VIVO NFCom (v2.3), MEGA QG VIVO NFSe (v2.0) e o Exportador de Relatório num app só.",
        "Hub com seções NFCom, NFSe e Relatórios, busca de operação e barra lateral para trocar de tela.",
        "Ambiente Produção/Homologação único, no topo, com indicador discreto na cor do ambiente. "
        "O Cancelamento mostra o ambiente na confirmação.",
        "Cards mostram o que falta no config.json para cada operação rodar no ambiente escolhido.",
        "NFSe: URLs saíram do código para o config.json e ganharam Homologação.",
        "Exportador de Relatório: por dia ou período único (mês inteiro ou dia X a Y), "
        "todas as notas ou somente canceladas, XML em Produção ou Homologação.",
        "Configuração única (config.json, mesmo formato dos QGs) embutida no exe como reserva.",
        "NFCe em construção: próxima etapa, já sinalizada no hub e na barra lateral.",
        "Cards do hub redesenhados: ícone em destaque, estado (Pronto / Configurar / Em construção) e "
        "cantos arredondados.",
    ],
    "v2.3 (NFCom)": [
        "Endpoints e credenciais fora do código; Exportador com modo consolidado, split de arquivos "
        "grandes e autenticação Windows.",
    ],
    "v2.0 (NFSe)": [
        "Central única com Download de XMLs (COM/SEM CEP), Relatório DPS sem Endereço, Expandir DPS "
        "no CSV, Reenvio de XML e Consulta DPS.",
    ],
}
