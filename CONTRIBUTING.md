# Como contribuir com o MegaQG Vivo

## Commits

1. **Coautoria obrigatória do Ab3lFonseca.** A partir de 01/10/2026, **todo commit** termina com esta linha,
   exatamente assim, separada do corpo da mensagem por uma linha em branco:

   ```
   Co-authored-by: Abel Fonseca <129634676+Ab3lFonseca@users.noreply.github.com>
   ```

   - O e-mail é o endereço "noreply" do GitHub do Abel: é ele que liga o commit à conta `@Ab3lFonseca`.
     Não troque por outro e-mail.
   - Commits feitos pelo próprio Abel (ele como autor) não precisam da linha.
   - Para não esquecer, ative o modelo de mensagem do repositório (uma vez por clone):
     ```
     git config commit.template .gitmessage
     ```
     O `git commit` (sem `-m`) passa a abrir a mensagem já com a linha de coautoria.
2. **Mensagem em inglês** (título e corpo). Escreva a mensagem num arquivo e use `git commit -F <arquivo>`.
3. **Título curto no imperativo** (ex.: "Add NFCe contingency return"), corpo com o que mudou e por quê.

## Segurança

- **Nunca versionar** `config.json`, senhas, endereços de servidor ou URLs internas. Tudo isso fica no
  `config.json` (fora do git) ou em variáveis `MEGAQG_*`.
- Antes de cada commit, rode a varredura nos arquivos preparados (não pode retornar nada):
  ```
  git grep --cached -n -I -E "\b(10|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}|https?://[^\"/#]+:[0-9]{2,5}|password\"[[:space:]]*:[[:space:]]*\"[^\"<.]" -- . ":!CONTRIBUTING.md"
  ```
  Acrescente à expressão os nomes dos servidores internos que você conhece (a lista fica fora do repositório
  público, para não expor a infraestrutura).
- O `MegaQGVivo.exe` contém a configuração embutida: não anexe o exe nem o pacote de `dist\` em e-mail, chat
  ou GitHub.

## Antes de enviar

```
.venv\Scripts\python tests\testar_engines.py
.venv\Scripts\python tests\abrir_telas.py
```

Os dois precisam passar. Mudança visual: anexe prints (`tests\abrir_telas.py <pasta>` gera um de cada tela).
