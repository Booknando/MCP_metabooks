# Metabooks MCP Server: Guia de Instalação para Mac

Permite que o Claude consulte o catálogo Metabooks diretamente na conversa: busque livros, veja metadados completos, capas e dados de editoras, sem sair do chat.

O servidor roda no seu próprio computador. Suas credenciais Metabooks ficam salvas só na sua máquina e nunca saem dela.

> Usuário de Windows? Veja o [README.md](../README.md).

## O que você vai precisar

Antes de começar, separe:

- Python 3.12 ou superior instalado no seu Mac (explicado no Passo 1)
- Claude Desktop instalado ([baixe aqui](https://claude.ai/download))
- Suas credenciais Metabooks: usuário e senha, ou um token de metadados fornecido pela MVB

## Instalação passo a passo

### Passo 1: Instalar o Python

O macOS já vem com uma versão de Python pré-instalada, mas geralmente é antiga (algo como 3.9) e não atende ao mínimo exigido de 3.12+.

1. Abra o Terminal (Cmd + Espaço, digite "Terminal" e Enter, ou Aplicativos > Utilitários > Terminal).
2. Digite o comando abaixo e pressione Enter:
```
python3 --version
```
3. Se aparecer `Python 3.12.x` ou superior, você já tem o necessário. Pule para o Passo 2.
4. Se aparecer uma versão abaixo de 3.12 (o caso mais comum), acesse [python.org/downloads/macos](https://www.python.org/downloads/macos/) e baixe o instalador mais recente (arquivo `.pkg`).
5. Abra o arquivo baixado e siga o instalador (Continuar, Aceitar, Instalar). Pode pedir sua senha do Mac.
6. Depois de instalar, **abra um novo Terminal** (feche o antigo e abra outro, ou o PATH não atualiza) e confirme com o comando versionado da instalação que você fez, por exemplo:
```
python3.13 --version
```
Anote esse número de versão (no exemplo, `3.13`). Você vai usar esse mesmo número nos próximos comandos.

### Passo 2: Baixar e instalar o Metabooks MCP

1. Acesse a [página do repositório no GitHub](https://github.com/Booknando/MCP_metabooks), clique no botão verde **`< > Code`** e depois em **Download ZIP** (ou baixe direto por [este link](https://github.com/Booknando/MCP_metabooks/archive/refs/heads/main.zip)).
2. O Mac geralmente descompacta o arquivo automaticamente na pasta Downloads, criando uma pasta chamada `MCP_metabooks-main`. Se não descompactar, dê duplo clique no `.zip`.
3. No Terminal, instale com o comando (troque `3.13` pela versão que você instalou no Passo 1):
```
python3.13 -m pip install ~/Downloads/MCP_metabooks-main
```
4. Ao final da instalação, o Terminal costuma mostrar um aviso parecido com:
```
WARNING: The script metabooks-mcp is installed in '/Library/Frameworks/Python.framework/Versions/3.13/bin' which is not on PATH.
```
**Guarde esse caminho.** Ele é diferente para cada pessoa, dependendo da versão do Python instalada, e você vai precisar dele no Passo 4.

5. Para confirmar que a instalação funcionou, use o caminho completo do aviso acima:
```
/Library/Frameworks/Python.framework/Versions/3.13/bin/metabooks-mcp --help
```
Se aparecer uma tela de ajuda do comando, está tudo certo.

### Passo 3: Abrir o arquivo de configuração do Claude Desktop

> **Importante:** Feche o Claude Desktop completamente antes de editar (Cmd + Q). No Mac não existe ícone de bandeja como no Windows; se o app continuar aberto enquanto você edita, ele sobrescreve suas alterações ao reiniciar.

No Mac, o arquivo fica em outro lugar (não é `%APPDATA%\Claude`). Para editar com segurança, recomendamos usar o Terminal em vez do TextEdit, porque o TextEdit pode salvar em formato rich text e quebrar o JSON sem avisar.

1. No Terminal, rode:
```
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```
2. Se o arquivo não existir, o nano cria um novo automaticamente.

### Passo 4: Adicionar o servidor Metabooks ao Claude Desktop

> **Diferença importante em relação ao Windows:** no Mac, o Claude Desktop não herda o PATH do Terminal. Por isso, o campo `"command"` precisa ser o **caminho completo** do executável (aquele que você guardou no Passo 2), e não apenas `metabooks-mcp`.

Há dois casos, leia qual se aplica a você:

#### Caso A: o arquivo está vazio ou não tem nenhum outro servidor MCP

Cole o bloco completo abaixo de acordo com o tipo de credencial (ajuste o caminho do `command` para o que você anotou no Passo 2):

Se você tem usuário e senha Metabooks:
```json
{
  "mcpServers": {
    "metabooks": {
      "command": "/Library/Frameworks/Python.framework/Versions/3.13/bin/metabooks-mcp",
      "env": {
        "METABOOKS_USERNAME": "seu_usuario_aqui",
        "METABOOKS_PASSWORD": "sua_senha_aqui"
      }
    }
  }
}
```

Se você tem token de metadados (staging/rc):
```json
{
  "mcpServers": {
    "metabooks": {
      "command": "/Library/Frameworks/Python.framework/Versions/3.13/bin/metabooks-mcp",
      "env": {
        "METABOOKS_METADATA_TOKEN": "seu_token_aqui"
      }
    }
  }
}
```

#### Caso B: o arquivo já tem outros servidores MCP configurados

Não apague o conteúdo existente. Adicione a entrada do Metabooks dentro da chave `"mcpServers"`, separada por vírgula dos outros servidores:
```json
{
  "mcpServers": {
    "outro-servidor-existente": {
      "command": "...",
      "args": ["..."]
    },
    "metabooks": {
      "command": "/Library/Frameworks/Python.framework/Versions/3.13/bin/metabooks-mcp",
      "env": {
        "METABOOKS_USERNAME": "seu_usuario_aqui",
        "METABOOKS_PASSWORD": "sua_senha_aqui"
      }
    }
  }
}
```

Substitua `seu_usuario_aqui`, `sua_senha_aqui` ou `seu_token_aqui` pelos seus dados reais.

No nano, navegue com as setas do teclado. Para salvar: **Ctrl + O**, depois **Enter**. Para sair: **Ctrl + X**.

> **Atenção:** o JSON é sensível a vírgulas e aspas. Cada servidor deve estar separado por vírgula do próximo, sem vírgula após o último.

### Passo 5: Reiniciar o Claude Desktop

Feche o Claude Desktop completamente com **Cmd + Q** (fechar a janela não é suficiente) e abra de novo.

Depois de reiniciar, em qualquer conversa, clique no botão **"+"** próximo da caixa de mensagem e depois em **Conectores**. O `metabooks` deve aparecer na lista, com um indicador de que está ativo.

### Passo 6: Testar

Na caixa de conversa do Claude, peça algo como:

- "Busque na Metabooks livros sobre Linux"
- "Me dê os detalhes do ISBN 9788575228517"
- "Mostre a capa do ISBN 9788530951382" (exige token de capa configurado)

Se o Claude responder com dados do catálogo Metabooks, a instalação está funcionando.

## Problemas comuns

**O servidor não aparece no Claude Desktop**
- Verifique se o `pip install` foi concluído sem erros.
- Confirme que o `claude_desktop_config.json` foi salvo corretamente (sem erros de vírgula ou aspas). Você pode validar o JSON rodando `python3.13 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json` no Terminal; se ele reimprimir o conteúdo sem erro, está válido.
- Reinicie o Claude Desktop completamente com Cmd + Q (fechar a janela não basta).

**Erro: "metabooks-mcp: command not found" no Terminal**
- Isso é esperado no Mac, já que o script não fica no PATH por padrão. Use sempre o caminho completo (ex.: `/Library/Frameworks/Python.framework/Versions/3.13/bin/metabooks-mcp`).

**Erro de credenciais / "Sem credenciais de metadados"**
- Verifique se substituiu os valores no JSON pelas suas credenciais reais.
- Aspas, maiúsculas e minúsculas importam.
- Se você fez várias tentativas seguidas e passou a receber erro de login, pode ser um bloqueio temporário da API (não senha errada). Aguarde alguns minutos e tente de novo.

**A entrada `metabooks` some toda vez que reinicio o Claude Desktop**
- O Claude Desktop remove entradas com erros de JSON para poder iniciar.
- Causa mais comum: vírgula faltando ou sobrando, aspas erradas, ou arquivo editado com o Claude Desktop ainda aberto.
- Sempre feche o Claude Desktop com Cmd + Q antes de editar o arquivo.

**Tenho outro servidor MCP configurado no Claude Desktop**
- Não apague os servidores existentes. Siga o Caso B do Passo 4.

## O que o Metabooks MCP consegue fazer

| Ferramenta | O que faz |
|---|---|
| Buscar por palavras-chave | Encontra livros por título, autor, editora, ISBN e outros filtros |
| Busca em lote de ISBNs | Consulta até 500 ISBNs de uma vez |
| Detalhes de um livro | Retorna todos os metadados de um título (JSON ou ONIX 3.0) |
| Detalhes de vários livros | Consulta vários UUIDs ao mesmo tempo |
| Visualizar capa | Exibe a imagem da capa direto na conversa (exige token de capa) |
| URL da capa | Retorna o link direto para a imagem da capa (uso autenticado; não abre no navegador) |
| Listar mídias | Lista as mídias do título (quarta capa, miolo, sumário, foto do autor) |
| Visualizar mídia | Exibe uma imagem de mídia (quarta capa, miolo, foto do autor) direto na conversa |
| Baixar mídia | Salva qualquer mídia em arquivo — capas extras, miolo, sumário em PDF, áudio |
| Autocomplete | Sugere autores, editoras, títulos e palavras-chave |
| Dados de editora | Retorna nome, endereço, CNPJ e prefixos ISBN da editora |

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

## Usando capas e arquivos de mídia

As ferramentas de capa e mídia/MMO precisam de tokens separados. Se a MVB forneceu esses tokens, acrescente no bloco `env` do `claude_desktop_config.json`:
```json
"METABOOKS_COVER_TOKEN": "seu_token_de_cover",
"METABOOKS_MMO_TOKEN": "seu_token_de_mmo"
```

Com o token de capa configurado, peça por exemplo "mostre a capa do ISBN 9788530951382" e o Claude exibe a imagem direto na conversa.

## Ambientes disponíveis

Por padrão, o servidor acessa a produção. Para usar staging ou RC, acrescente no bloco `env`:
```json
"METABOOKS_BASE_URL": "https://staging.kubernetes.br.metabooks.com/api/v2"
```

URLs disponíveis:
- Produção (padrão): `https://api.metabooks.com/api/v2`
- Staging: `https://staging.kubernetes.br.metabooks.com/api/v2`
- RC: `https://rc.kubernetes.br.metabooks.com/api/v2`

> No ambiente de teste (staging/rc), o acesso é exclusivamente via token (METABOOKS_METADATA_TOKEN / METABOOKS_COVER_TOKEN / METABOOKS_MMO_TOKEN). Em produção, funciona tanto por login (usuário/senha) quanto por token. O link de staging/rc pode variar conforme o sistema em deploy na semana.

## Atualizando para uma nova versão

1. Baixe o novo ZIP do repositório (mesmo processo do Passo 2).
2. No Terminal, instale por cima com a flag de upgrade (troque `3.13` pela sua versão e o caminho da pasta pela nova):
```
python3.13 -m pip install --upgrade ~/Downloads/MCP_metabooks-main
```
3. Reinicie o Claude Desktop (Cmd + Q e abrir de novo).

Não é necessário alterar o `claude_desktop_config.json`, a configuração continua valendo, a menos que o caminho do executável tenha mudado (confira com o mesmo comando do Passo 2, item 5).

## Segurança

- Suas credenciais ficam só no seu computador, dentro do `claude_desktop_config.json`.
- O servidor roda localmente e se comunica diretamente com a API da Metabooks, nenhum dado passa por servidores de terceiros.
- Não compartilhe o arquivo `claude_desktop_config.json` com outras pessoas.

## Licença

Uso interno Booknando. A API Metabooks pertence à MVB.

---

Informações técnicas para desenvolvedores: consulte [DEVELOPERS.md](../DEVELOPERS.md).
