# Publicar atualizações do VF Emissor

## Preparar o canal uma vez

1. Crie um repositório **público** no GitHub para o programa, por exemplo `seu-usuario/vf-emissor`.
2. Extraia o pacote de código. A raiz do repositório precisa conter `server.py`, `version.json`, `portable`, `installer`, `scripts`, `static`, `base`, `tests` e a pasta `.github`.
3. Adicione esses arquivos ao repositório com Git/GitHub Desktop, incluindo `.github/workflows/release-windows.yml` e `portable/python312.zip`. O `.gitignore` preserva a biblioteca ZIP do Python e exclui dados, PFX e bancos de dados. Nunca publique sua pasta de dados local.
4. Em **Actions**, habilite o workflow e execute **Publicar VF Emissor para Windows**. Você também pode enviar a tag `v0.14.0`, correspondente ao `version.json`.
5. O workflow usa Windows, testa o programa e a DPAPI nativa, compila o NSIS, verifica instalação/reinstalação, atalho e preservação de dados e publica uma Release estável com o instalador e `update-manifest.json`.
6. Distribua o instalador dessa Release aos funcionários. Ele já contém o canal `dono/repositorio` do próprio GitHub Actions.

O instalador incluído nesta conversa está compilado com o canal vazio, pois o repositório ainda não foi informado. Para começar a usá-lo antes da primeira Release, configure o canal na tela de instalações de cada PC uma vez.

## Publicar a próxima versão

1. Faça as alterações no código e os testes.
2. Aumente a versão em **version.json**, por exemplo para `0.14.0`. O servidor, o lançador, o instalador e o manifesto usam esse arquivo; não é preciso alterar manualmente o código do atualizador.
3. Envie o código ao GitHub e crie a tag correspondente `v0.14.0`, ou execute o workflow manualmente.
4. A publicação só acontece depois que os testes e a compilação terminarem com sucesso. O instalador publicado precisa continuar chamado `VF-Emissor-Setup-VERSAO.exe` e o manifesto `update-manifest.json`.
5. Na próxima abertura completa pelo atalho, cada PC instala automaticamente essa versão. As empresas não precisam ser cadastradas novamente e os XML permanecem na máquina.

## Funcionamento técnico

- Canal público: API de Releases do GitHub, sem token salvo no computador dos funcionários.
- Apenas a última versão estável, com número maior que o instalado, é elegível; versões de teste e rascunhos não são aplicados.
- Endereço do instalador vinculado ao repositório configurado; tamanho, SHA-256, manifesto e digest do GitHub são conferidos quando disponíveis.
- Banco copiado para `Dados/backups/antes-atualizacao-VERSAO.sqlite3` antes da instalação; o instalador altera apenas a pasta do programa.
- Atualização ocorre antes de iniciar uma nova sessão do emissor. Uma instância que já está aberta é reaproveitada para preservar o trabalho em andamento. Use **Encerrar programa** ao terminar.
- Falha de rede/integridade mantém a versão instalada. O estado da última verificação aparece em Configurações.
- Compilação local alternativa: instale NSIS no Windows e execute `scripts/build-release.ps1 -Repository dono/repositorio`. Os arquivos saem em `dist`.

A verificação SHA-256 protege a integridade do download. O canal de publicação do escritório deve ser controlado pelas pessoas responsáveis pelo código. Não há assinatura Authenticode incluída neste pacote.

## Referências

- Releases do GitHub: https://docs.github.com/en/rest/releases/releases
- Instalação por usuário NSIS: https://nsis.sourceforge.io/Reference/RequestExecutionLevel
- Proteção Windows DPAPI: https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata

## Repositório do emissor

O emissor usa seu próprio repositório **VF-Emissor**. Não utilize o canal do outro programa VF Fiscal. Somente código e recursos públicos devem ir para o GitHub; exclua dados, arquivos de clientes, XML reais, certificados, senhas e pastas de backup. O runtime portátil é preparado pelo workflow a partir do Python oficial e das dependências públicas, sem versionar seus binários.

O workflow Windows está incluído e exige aprovação dos testes antes de publicar. A opção de execução manual também publica a tag correspondente à versão, apontando para o commit que foi compilado. Não publique duas compilações diferentes com a mesma versão; aumente `version.json` para distribuir uma correção.
