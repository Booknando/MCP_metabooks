# Instalação guiada no Windows e no macOS

Baixe o **Source code (zip)** da versão desejada em
[Releases](https://github.com/Booknando/MCP_metabooks/releases) e extraia **todos** os arquivos.
Enquanto não houver release, use o ZIP da branch que contém o instalador.
O Metabooks continua distribuído exclusivamente pelo GitHub; o pip baixa suas
dependências do índice Python. É necessária conexão com a internet.

1. Instale o Claude Desktop e feche-o completamente, inclusive na bandeja/menu.
2. No Windows, abra **Instalar-Windows.cmd**. No Mac, abra **Instalar-Mac.command**.
3. Se faltar Python 3.12+, o navegador abrirá a página oficial. Instale-o
   (no Windows, marque **Add Python to PATH**) e abra o instalador novamente.
4. Informe usuário/senha de produção ou token de staging/RC. Os tokens de capas
   e mídias são opcionais. As entradas secretas não aparecem enquanto você digita.
5. Aguarde a mensagem de conclusão e reabra o Claude Desktop.

No macOS, se o ZIP não conservar a permissão de execução, abra Terminal, digite
`bash ` (com espaço), arraste **Instalar-Mac.command** para a janela e pressione Enter.
Use o mesmo procedimento para o atualizador. Não é necessário usar sudo.

O instalador cria um ambiente Python exclusivo em `%LOCALAPPDATA%\MetabooksMCP`
(Windows) ou `~/Library/Application Support/MetabooksMCP` (Mac), instala o pacote,
verifica dependências e construção do servidor e só então configura a entrada
`metabooks` no Claude. Outros servidores e opções são preservados. Se você já
cadastrou este MCP com outro nome, remova a entrada duplicada manualmente.

As credenciais ficam no campo `env` da configuração local do Claude, como na
instalação manual. Não são enviadas durante a instalação nem verificadas contra
a API; o MCP as utilizará para autenticar consultas. Configuração e backups
contêm segredos: não os compartilhe. No Mac os novos arquivos têm acesso restrito
ao usuário; no Windows herdam as permissões da pasta do perfil.

## Atualizar

Guarde a pasta extraída. Abra **Atualizar-Windows.cmd** ou **Atualizar-Mac.command**.
O atualizador consulta a última **release pública estável** do GitHub, cria outro
ambiente, verifica-o e troca o caminho usado pelo Claude, preservando credenciais
e um eventual `--env-file`. Feche e reabra o Claude ao concluir.

Sem release publicada, ele informa o motivo e mantém a instalação atual.
Para instalar uma versão específica ou de desenvolvimento, baixe seu ZIP e execute
**Instalar**: escolha preservar as credenciais existentes. Não há atualização
silenciosa, serviço em segundo plano ou publicação no PyPI.

## Falhas e restauração

Se a instalação ou validação falhar, a configuração anterior permanece ativa.
JSON inválido ou alterado durante a operação não é sobrescrito. Cada substituição
gera um `claude_desktop_config.json.backup-...` na mesma pasta da configuração;
o caminho aparece ao concluir. Para voltar, feche o Claude e copie o backup
desejado sobre `claude_desktop_config.json`. Os ambientes anteriores são mantidos
para isso; remova os antigos apenas depois de confirmar que não são mais usados.

O teste de instalação é offline em relação à API Metabooks. Confirme suas
permissões fazendo uma consulta no Claude. Nunca envie senha/token em relatos
de problemas. Para cancelar antes de concluir, pressione Ctrl+C.
