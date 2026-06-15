# Metabooks MCP Server

Permite que o **Claude** consulte o catálogo Metabooks diretamente na conversa: busque livros, veja metadados completos, capas e dados de editoras — sem sair do chat.

> O servidor roda **no seu próprio computador**. Suas credenciais Metabooks ficam salvas só na sua máquina e nunca saem dela.

---

## O que você vai precisar

Antes de começar, separe:

- **Node.js** instalado no seu computador (explicado no Passo 1)
- **Claude Desktop** instalado ([baixe aqui](https://claude.ai/download))
- Suas **credenciais Metabooks** — usuário e senha, **ou** um token de metadados fornecido pela MVB

---

## Instalação passo a passo

### Passo 1 — Instalar o Node.js

O Node.js é o programa que executa o servidor Metabooks. Você provavelmente já tem ele instalado — veja como checar:

1. Pressione `Win + R`, digite `cmd` e pressione Enter para abrir o Prompt de Comando
2. Digite o comando abaixo e pressione Enter:
   ```
   node --version
   ```
3. Se aparecer algo como `v20.11.0` (qualquer número ≥ 18), você já tem o Node.js. **Pule para o Passo 2.**
4. Se aparecer um erro, baixe e instale o Node.js em [nodejs.org](https://nodejs.org) (escolha a versão **LTS**). Após instalar, reinicie o computador.

---

### Passo 2 — Baixar o Metabooks MCP

1. Nesta página do GitHub, clique no botão verde **`< > Code`** (no canto superior direito da lista de arquivos)
2. Clique em **Download ZIP**
3. Abra o arquivo ZIP baixado
4. Extraia o conteúdo para a pasta **`C:\Metabooks-mcp`**

   > Se aparecer a pergunta "Deseja substituir arquivos existentes?", clique em **Sim**.

Ao final, você deve ter uma pasta `C:\Metabooks-mcp` com os arquivos do projeto dentro.

---

### Passo 3 — Abrir o arquivo de configuração do Claude Desktop

O Claude Desktop usa um arquivo de configuração para saber quais servidores MCP iniciar. Você precisa editar esse arquivo.

> **Importante:** Feche o Claude Desktop **antes** de editar. Clique com o botão direito no ícone da bandeja do sistema → **Sair**. Se o Claude Desktop estiver aberto enquanto você edita, ele vai sobrescrever suas alterações ao reiniciar.

1. Pressione `Win + R`, cole o caminho abaixo e pressione Enter:
   ```
   %APPDATA%\Claude
   ```
2. Uma pasta se abrirá. Procure o arquivo **`claude_desktop_config.json`**.
   - Se ele não existir, crie um arquivo de texto com esse nome exato (incluindo a extensão `.json`).
3. Abra o arquivo com o **Bloco de Notas** (clique com o botão direito → Abrir com → Bloco de Notas).

---

### Passo 4 — Adicionar o servidor Metabooks ao Claude Desktop

Há dois casos — leia qual se aplica a você:

#### Caso A: o arquivo está vazio ou não tem nenhum outro servidor MCP

Cole o bloco completo abaixo (escolha de acordo com o tipo de credencial):

**Se você tem usuário e senha Metabooks:**

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "node",
      "args": ["C:\\Metabooks-mcp\\dist\\index.cjs"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_USERNAME": "seu_usuario_aqui",
        "METABOOKS_PASSWORD": "sua_senha_aqui"
      }
    }
  }
}
```

**Se você tem token de metadados (staging/rc):**

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "node",
      "args": ["C:\\Metabooks-mcp\\dist\\index.cjs"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_METADATA_TOKEN": "seu_token_aqui"
      }
    }
  }
}
```

#### Caso B: o arquivo já tem outros servidores MCP configurados

**Não apague o conteúdo existente.** Encontre a linha `"mcpServers": {` e adicione a entrada do Metabooks dentro dela, separada por vírgula dos outros servidores. Exemplo de como o arquivo deve ficar:

```json
{
  "mcpServers": {
    "outro-servidor-existente": {
      "command": "...",
      "args": ["..."]
    },
    "metabooks": {
      "command": "node",
      "args": ["C:\\Metabooks-mcp\\dist\\index.cjs"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_USERNAME": "seu_usuario_aqui",
        "METABOOKS_PASSWORD": "sua_senha_aqui"
      }
    }
  }
}
```

---

Substitua `seu_usuario_aqui`, `sua_senha_aqui` ou `seu_token_aqui` pelos seus dados reais.

Salve o arquivo (`Ctrl + S`).

> **Atenção:** O JSON é sensível a vírgulas e aspas. Verifique que cada servidor está separado por vírgula do próximo, e que não há vírgula após o último servidor.

**Validar o JSON antes de abrir o Claude Desktop** (recomendado): abra o Prompt de Comando e execute:
```
node -e "JSON.parse(require('fs').readFileSync(process.env.APPDATA+'/Claude/claude_desktop_config.json','utf8'));console.log('JSON valido')"
```
Se aparecer `JSON valido`, está correto. Se aparecer um erro, revise o arquivo.

---

### Passo 5 — Reiniciar o Claude Desktop

Feche o Claude Desktop **completamente** (clique com o botão direito no ícone da bandeja do sistema → Sair) e abra de novo.

Após reiniciar, clique no ícone de **martelo** ou **conector** na interface do Claude. O servidor `metabooks` deve aparecer na lista com as ferramentas disponíveis.

---

### Passo 6 — Testar

Na caixa de conversa do Claude, peça algo como:

> *"Busque na Metabooks livros sobre Linux"*

> *"Me dê os detalhes do ISBN 9788575228517"*

Se o Claude responder com dados do catálogo Metabooks, a instalação está funcionando.

---

## Problemas comuns

**O servidor não aparece no Claude Desktop**
- Verifique se o arquivo `C:\Metabooks-mcp\dist\index.cjs` realmente existe.
- Confirme que o arquivo `claude_desktop_config.json` foi salvo corretamente (sem erros de vírgula ou aspas no JSON).
- Reinicie o Claude Desktop completamente (fechar pela bandeja, não só minimizar).

**Erro: "node não foi reconhecido"**
- O Node.js não está instalado ou não foi reiniciado o computador após a instalação. Instale em [nodejs.org](https://nodejs.org) e reinicie.

**Erro de credenciais / "Sem credenciais de metadados"**
- Verifique se substituiu os valores no JSON pelas suas credenciais reais.
- O campo `TRANSPORT` deve ser exatamente `stdio` (letras minúsculas).

**A entrada `metabooks` some toda vez que reinicio o Claude Desktop**
- O Claude Desktop detecta erros de JSON e remove a entrada com problema para poder iniciar.
- Causa mais comum: vírgula faltando ou sobrando, aspas erradas, ou arquivo editado com o Claude Desktop aberto.
- **Sempre feche o Claude Desktop antes de editar o arquivo** (bandeja → Sair).
- Valide o JSON antes de reabrir (veja o comando no Passo 4).

**Tenho outro servidor MCP configurado no Claude Desktop**
- Não apague os servidores existentes. Siga o **Caso B** do Passo 4.

---

## O que o Metabooks MCP consegue fazer

| Ferramenta | O que faz |
|---|---|
| Buscar por palavras-chave | Encontra livros por título, autor, editora, ISBN, palavra-chave e outros filtros |
| Busca em lote de ISBNs | Consulta até 500 ISBNs de uma vez |
| Detalhes de um livro | Retorna todos os metadados de um título específico |
| Detalhes de vários livros | Consulta vários UUIDs ao mesmo tempo |
| Arquivos de mídia | Lista URLs de capa, sumário, amostras e foto do autor |
| URL da capa | Retorna o link direto para a imagem da capa |
| Autocomplete | Sugere autores, editoras, títulos e palavras-chave |
| Dados de editora | Retorna nome, endereço, CNPJ e prefixos ISBN da editora |

---

## Exemplos de busca

Você pode pedir ao Claude diretamente em linguagem natural. Mas se quiser usar a sintaxe de busca avançada da Metabooks, aqui está uma referência:

| O que você quer | O que digitar |
|---|---|
| Busca geral | `ST=Linux` |
| Por autor | `AU="Knuth, Donald"` |
| Por título | `TI=algoritmos` |
| Por editora | `VL=Novatec` |
| Por ISBN | `IS=9788575228517` |
| Somente e-books | `PF=E*` |
| Por palavra-chave | `SW=programação` |
| Por faixa de preço | `PR=40^80` |
| Por data de atualização | `AD=20240101^20241231` |

Combine com `and`, `or`, `not` e parênteses. Exemplo: `VL=Novatec and PF=E*` (e-books da Novatec).

---

## Usando capas e arquivos de mídia

Por padrão, as ferramentas de **capa** e **mídia/MMO** precisam de tokens separados. Se a MVB forneceu esses tokens para você, acrescente as linhas abaixo no bloco `env` do seu `claude_desktop_config.json`:

```json
"METABOOKS_COVER_TOKEN": "seu_token_de_cover",
"METABOOKS_MMO_TOKEN": "seu_token_de_mmo"
```

---

## Ambientes disponíveis

Por padrão, o servidor acessa a **produção**. Para usar staging ou RC, acrescente no bloco `env`:

```json
"METABOOKS_BASE_URL": "https://staging.kubernetes.br.metabooks.com/api/v2"
```

URLs disponíveis:
- Produção (padrão): `https://api.metabooks.com/api/v2`
- Staging: `https://staging.kubernetes.br.metabooks.com/api/v2`
- RC: `https://rc.kubernetes.br.metabooks.com/api/v2`

---

## Atualizando para uma nova versão

1. Baixe o novo ZIP do repositório (mesmo processo do Passo 2)
2. Extraia e substitua os arquivos em `C:\Metabooks-mcp`
3. Reinicie o Claude Desktop

Não é necessário alterar o `claude_desktop_config.json` — a configuração continua valendo.

---

## Segurança

- Suas credenciais ficam **só no seu computador**, dentro do `claude_desktop_config.json`.
- O servidor roda localmente e se comunica diretamente com a API da Metabooks — nenhum dado passa por servidores de terceiros.
- Não compartilhe o arquivo `claude_desktop_config.json` com outras pessoas.

---

## Licença

Uso interno Booknando. A API Metabooks pertence à MVB.

---

> Informações técnicas para desenvolvedores: consulte [DEVELOPERS.md](DEVELOPERS.md).
