# Metabooks MCP Server

Permite que o **Claude** consulte o catálogo Metabooks diretamente na conversa: busque livros, veja metadados completos, capas e dados de editoras — sem sair do chat.

> O servidor roda **no seu próprio computador**. Suas credenciais Metabooks ficam salvas só na sua máquina e nunca saem dela.

---

## O que você vai precisar

Antes de começar, separe:

- **Python 3.12+** instalado no seu computador (explicado no Passo 1)
- **Claude Desktop** instalado ([baixe aqui](https://claude.ai/download))
- Suas **credenciais Metabooks** — usuário e senha, **ou** um token de metadados fornecido pela MVB

---

## Instalação passo a passo

> 🍎 **No Mac?** Os caminhos e comandos são diferentes (o executável não fica no PATH do Claude Desktop). Siga o guia dedicado: **[docs/instalacao-mac.md](docs/instalacao-mac.md)**. As instruções abaixo são para **Windows**.

### Passo 1 — Instalar o Python

1. Pressione `Win + R`, digite `cmd` e pressione Enter para abrir o Prompt de Comando
2. Digite o comando abaixo e pressione Enter:
   ```
   python --version
   ```
3. Se aparecer algo como `Python 3.12.x` (qualquer número ≥ 3.12), você já tem o Python. **Pule para o Passo 2.**
4. Se aparecer um erro, baixe e instale o Python em [python.org](https://www.python.org/downloads/) (escolha a versão mais recente).
   - Durante a instalação, marque a opção **"Add Python to PATH"**.
   - Após instalar, reinicie o computador.

---

### Passo 2 — Baixar e instalar o Metabooks MCP

1. Nesta página do GitHub, clique no botão verde **`< > Code`** e depois em **Download ZIP**
2. Extraia o conteúdo para a pasta **`C:\Metabooks-mcp`**
3. Abra o Prompt de Comando (`Win + R` → `cmd`) e execute:
   ```
   pip install C:\Metabooks-mcp
   ```

Isso instala o comando `metabooks-mcp` no seu Python. Para verificar, execute:
```
metabooks-mcp --help
```

---

### Passo 3 — Abrir o arquivo de configuração do Claude Desktop

> **Importante:** Feche o Claude Desktop **antes** de editar. Clique com o botão direito no ícone da bandeja do sistema → **Sair**. Se o Claude Desktop estiver aberto enquanto você edita, ele vai sobrescrever suas alterações ao reiniciar.

1. Pressione `Win + R`, cole o caminho abaixo e pressione Enter:
   ```
   %APPDATA%\Claude
   ```
2. Procure o arquivo **`claude_desktop_config.json`**.
   - Se não existir, crie um arquivo de texto com esse nome exato (incluindo a extensão `.json`).
3. Abra o arquivo com o **Bloco de Notas** (clique com o botão direito → Abrir com → Bloco de Notas).

---

### Passo 4 — Adicionar o servidor Metabooks ao Claude Desktop

Há dois casos — leia qual se aplica a você:

#### Caso A: o arquivo está vazio ou não tem nenhum outro servidor MCP

Cole o bloco completo abaixo de acordo com o tipo de credencial:

**Se você tem usuário e senha Metabooks:**

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "metabooks-mcp",
      "env": {
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
      "command": "metabooks-mcp",
      "env": {
        "METABOOKS_METADATA_TOKEN": "seu_token_aqui"
      }
    }
  }
}
```

#### Caso B: o arquivo já tem outros servidores MCP configurados

**Não apague o conteúdo existente.** Adicione a entrada do Metabooks dentro da chave `"mcpServers"`, separada por vírgula dos outros servidores:

```json
{
  "mcpServers": {
    "outro-servidor-existente": {
      "command": "...",
      "args": ["..."]
    },
    "metabooks": {
      "command": "metabooks-mcp",
      "env": {
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

> **Atenção:** O JSON é sensível a vírgulas e aspas. Cada servidor deve estar separado por vírgula do próximo, sem vírgula após o último.

---

### Passo 5 — Reiniciar o Claude Desktop

Feche o Claude Desktop **completamente** (bandeja → Sair) e abra de novo.

Após reiniciar, clique no ícone de **martelo** ou **conector** na interface do Claude. O servidor `metabooks` deve aparecer com as ferramentas disponíveis.

---

### Passo 6 — Testar

Na caixa de conversa do Claude, peça algo como:

> *"Busque na Metabooks livros sobre Linux"*

> *"Me dê os detalhes do ISBN 9788575228517"*

> *"Mostre a capa do ISBN 9788530951382"* (exige token de capa configurado)

Se o Claude responder com dados do catálogo Metabooks, a instalação está funcionando.

---

## Problemas comuns

**O servidor não aparece no Claude Desktop**
- Verifique se o `pip install` foi concluído sem erros.
- Confirme que o `claude_desktop_config.json` foi salvo corretamente (sem erros de vírgula ou aspas).
- Reinicie o Claude Desktop completamente (fechar pela bandeja, não só minimizar).

**Erro: "metabooks-mcp não foi reconhecido"**
- O Python não está no PATH ou a instalação via pip falhou.
- Reinstale o Python marcando "Add Python to PATH" e tente o `pip install` novamente.

**Erro de credenciais / "Sem credenciais de metadados"**
- Verifique se substituiu os valores no JSON pelas suas credenciais reais.
- Aspas, maiúsculas e minúsculas importam.
- Se você fez várias tentativas seguidas e passou a receber erro de login, pode ser um bloqueio temporário da API (não senha errada). Aguarde alguns minutos e tente de novo.

**A entrada `metabooks` some toda vez que reinicio o Claude Desktop**
- O Claude Desktop remove entradas com erros de JSON para poder iniciar.
- Causa mais comum: vírgula faltando ou sobrando, aspas erradas, ou arquivo editado com o Claude Desktop aberto.
- **Sempre feche o Claude Desktop antes de editar o arquivo** (bandeja → Sair).

**Tenho outro servidor MCP configurado no Claude Desktop**
- Não apague os servidores existentes. Siga o **Caso B** do Passo 4.

---

## O que o Metabooks MCP consegue fazer

| Ferramenta | O que faz |
|---|---|
| Buscar por palavras-chave | Encontra livros por título, autor, editora, ISBN e outros filtros |
| Busca em lote de ISBNs | Consulta até 500 ISBNs de uma vez |
| Detalhes de um livro | Retorna todos os metadados de um título (JSON ou ONIX 3.0) |
| Detalhes de vários livros | Consulta vários UUIDs ao mesmo tempo |
| Visualizar capa | Exibe a imagem da capa direto na conversa (exige token de capa) |
| URL da capa | Retorna o link direto para a imagem da capa |
| Arquivos de mídia | Lista URLs de capa, sumário, amostras e foto do autor |
| Autocomplete | Sugere autores, editoras, títulos e palavras-chave |
| Dados de editora | Retorna nome, endereço, CNPJ e prefixos ISBN da editora |

---

## Exemplos de busca

Você pode pedir ao Claude em linguagem natural. Se quiser usar a sintaxe avançada da Metabooks:

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

As ferramentas de **capa** e **mídia/MMO** precisam de tokens separados. Se a MVB forneceu esses tokens, acrescente no bloco `env` do `claude_desktop_config.json`:

```json
"METABOOKS_COVER_TOKEN": "seu_token_de_cover",
"METABOOKS_MMO_TOKEN": "seu_token_de_mmo"
```

Com o token de capa configurado, peça por exemplo *"mostre a capa do ISBN 9788530951382"* e o Claude exibe a imagem direto na conversa (a capa é baixada e devolvida como imagem — o token nunca aparece numa URL).

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

> No ambiente de teste (staging/rc), o acesso é **exclusivamente via token**. Em produção, funciona tanto por login (usuário/senha) quanto por token.

---

## Atualizando para uma nova versão

1. Baixe o novo ZIP do repositório (mesmo processo do Passo 2)
2. Extraia e substitua os arquivos em `C:\Metabooks-mcp`
3. Execute novamente: `pip install C:\Metabooks-mcp`
4. Reinicie o Claude Desktop

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
> Instalação no macOS: consulte [docs/instalacao-mac.md](docs/instalacao-mac.md).
