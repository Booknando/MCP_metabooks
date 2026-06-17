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

**Aviso ao instalar: "The script metabooks-mcp.exe is installed in '...\Scripts' which is not on PATH"**
- A instalação **funcionou** — esse aviso apenas diz que a pasta onde o comando `metabooks-mcp.exe` foi colocado **não está no PATH** do Windows. Se você não corrigir, o Claude Desktop não encontra o comando e dá o erro *"metabooks-mcp não foi reconhecido"* (acima).
- O próprio aviso mostra o caminho exato da pasta `Scripts` — algo como `C:\Users\SEU_USUARIO\AppData\Local\Python\pythoncore-3.14-64\Scripts`. **Copie esse caminho**, ele será usado nas soluções abaixo.

  **Solução A — adicionar a pasta ao PATH (recomendada):** a configuração da documentação (`"command": "metabooks-mcp"`) passa a funcionar sem alterações.
  1. Menu Iniciar → digite *"variáveis de ambiente"* → abra **Editar as variáveis de ambiente do usuário**.
  2. Em **Variáveis de usuário**, selecione `Path` → **Editar** → **Novo** → cole o caminho da pasta `Scripts` → **OK** em todas as janelas.
  3. Feche o Claude Desktop pela bandeja (**Sair**) e abra de novo — programas só leem o PATH novo ao reiniciar.

  Alternativa por linha de comando (PowerShell), substituindo o caminho pelo seu:
  ```powershell
  $dir = 'C:\Users\SEU_USUARIO\AppData\Local\Python\pythoncore-3.14-64\Scripts'
  [Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';' + $dir, 'User')
  ```

  **Solução B — usar o caminho completo na configuração (sem mexer no PATH):** no `claude_desktop_config.json`, troque `"command": "metabooks-mcp"` pelo caminho completo do executável, com **barras duplas**:
  ```json
  "command": "C:\\Users\\SEU_USUARIO\\AppData\\Local\\Python\\pythoncore-3.14-64\\Scripts\\metabooks-mcp.exe"
  ```
  Atenção: esse caminho fica preso à versão do Python — se você atualizar o Python depois, ajuste o caminho.

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

## Exibição da capa e quedas da VM (perguntas frequentes)

**"A capa aparece dentro do cartão recolhido *Usou uma ferramenta*, não direto na conversa"**

Isso é comportamento do **cliente** (Claude Desktop e Cowork), não do MCP. Imagens devolvidas por uma ferramenta MCP são sempre renderizadas **dentro do cartão de resultado da ferramenta**, que vem recolhido — basta clicar para expandir. A capa está correta e completa; o Claude apenas não consegue "reemitir" a imagem na própria bolha de resposta (só descrevê-la). Não há configuração no servidor que mude **onde** o cliente coloca a imagem.

> Há um modo **experimental** (app HTML via MCP Apps) que tenta exibir a capa em destaque. Está desligado por padrão — veja `METABOOKS_ENABLE_UI_APP` em [DEVELOPERS.md](DEVELOPERS.md).

**"O espaço de trabalho do Claude cai: *VM service not running. The service failed to start*"**

Essa é a **VM do Cowork** (o ambiente que executa código e arquivos dentro do Claude Desktop) — um serviço **separado** do MCP metabooks. O servidor metabooks roda como um processo local comum e **não usa essa VM**, então não é a causa da queda. Para destravar:

1. Reinicie o Claude Desktop; se persistir, reinicie o Windows.
2. Atualize o Claude Desktop para a versão mais recente.
3. Verifique a virtualização do Windows: habilite **Plataforma de Máquina Virtual** e **Hyper-V**, atualize o WSL2 (`wsl --update`) e confirme que a virtualização está ligada na BIOS.
4. Verifique se antivírus/firewall corporativo está bloqueando o serviço de VM.
5. Se o aviso oferecer o link **"reinstalar o workspace"**, use-o.

Para confirmar a recuperação, veja `%APPDATA%\Roaming\Claude\logs\cowork_vm_node.log` (a linha de sucesso é `[VM:start] Windows VM service configured`).

**"Como sei qual cópia do MCP o Claude está usando?"**

Abra `%APPDATA%\Roaming\Claude\logs\mcp-server-metabooks.log` e procure a linha `Using MCP server command:` — ela mostra o caminho do executável realmente iniciado. Se você instalou o `metabooks-mcp` em mais de um ambiente Python, podem existir cópias diferentes; garanta que o `claude_desktop_config.json` aponta para a correta. (Observação: a versão mostrada no handshake é a do SDK MCP, não a do projeto.)

---

## O que o Metabooks MCP consegue fazer

| Ferramenta | O que faz |
|---|---|
| Buscar por palavras-chave | Encontra livros por título, autor, editora, ISBN e outros filtros |
| Busca em lote de ISBNs | Consulta até 500 ISBNs de uma vez |
| Detalhes de um livro | Retorna todos os metadados de um título (JSON ou ONIX 3.0) |
| Detalhes de vários livros | Consulta vários UUIDs ao mesmo tempo |
| Visualizar capa | Exibe a imagem da capa direto na conversa, em tamanho leve (exige token de capa) |
| Baixar capa | Salva a capa em arquivo no disco — use para o tamanho original (exige token de capa) |
| URL da capa | Retorna o link direto para a imagem da capa (uso autenticado; não abre no navegador) |
| Listar mídias | Lista as mídias do título (quarta capa, miolo, sumário, foto do autor) com seus `asset_id` |
| Visualizar mídia | Exibe uma imagem de mídia (quarta capa, miolo, foto do autor) direto na conversa (exige token de MMO) |
| Baixar mídia | Salva qualquer mídia em arquivo — capas extras, miolo, sumário em PDF, áudio (exige token de MMO) |
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

Para exibição, o tamanho é gerenciado automaticamente (versões leves, que sempre renderizam inline). A capa em **tamanho original** (~1,3 MB) não aparece bem inline em alguns clientes — para ela, peça *"baixe a capa original do ISBN 9788530951382"* e o Claude salva o arquivo em disco (por padrão na pasta `Downloads`).

Com o **token de MMO**, o Claude também acessa as **demais mídias** do título — quarta capa, amostras do miolo, foto do autor, sumário em PDF etc. Peça *"mostre a quarta capa"* ou *"mostre as amostras do miolo"* e a imagem aparece **inline** (é baixada e reduzida para renderizar bem; o token nunca vai numa URL). Para arquivos que não são imagem (sumário em PDF, áudio) ou para a imagem em resolução original, peça *"baixe o sumário"* e o Claude salva em disco. As URLs cruas de mídia **não abrem no navegador** — exigem o token no cabeçalho —, por isso a exibição é sempre feita pela própria ferramenta, sem links.

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
