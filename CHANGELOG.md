# Histórico de versões

## 2.8.0

- Corrige renovação de sessão por tempo sem deixar o token antigo aberto e sem
  interromper consultas em andamento.
- Marca falhas de capa, mídia e consultas com `isError=true`; padroniza mensagens
  de autenticação, permissão, recurso ausente, rate limit e timeout.
- Reconhece WAV e valida mídia antes de salvar. Recusa HTML disfarçado de PDF,
  PDF truncado, ZIP sem identidade EPUB e tipos HTTP incompatíveis.
- Downloads em streaming para temporário, com limite de 50 MiB. Visualizações
  limitadas a 10 MiB e 25 milhões de pixels; processamento fora do loop assíncrono.
- Publica arquivos completos atomicamente e protege contra sobrescrita concorrente.
- Carrega `.env` de CWD explicitamente, adiciona `--env-file` e diagnóstico offline
  `--diagnose` sem exibir senhas/tokens.
- Evita misturar identificadores de produtos relacionados e preço/moeda de
  registros distintos na projeção compacta.
- Adiciona retry limitado para consultas em falhas transitórias e Retry-After.
- Recusa índice de mídia negativo e informa corretamente os efeitos das tools
  nas anotações MCP.
- Corrige caminhos de log Windows e exemplos de schema no guia de desenvolvimento.
- CI valida sdist, wheel instalado, configuração, recurso HTML e handshake stdio.
- Tags versionadas preparam releases **em rascunho no GitHub**. Distribuição
  continua somente pelo GitHub; bloqueio de upload ao PyPI preservado.

## 2.7.0

- Corrige construção do servidor no SDK MCP 1.x e publicação da versão no handshake.
- Expõe descrições de parâmetros no schema e atualiza guias Windows/macOS.
