# VF Emissor

Emissor local de NF-e para Windows, com interface no navegador, dados por empresa e XML guardados no PC de emissão.

## Instalar

Baixe o instalador da seção Releases deste repositório, encerre a versão anterior e execute o arquivo EXE. O instalador cria o atalho VF Emissor na área de trabalho.

Empresas, notas, configurações e XML ficam em `%LOCALAPPDATA%\VFEmissor\Dados`, separados da pasta do programa. Certificados A1 salvos são protegidos pela conta do Windows.

## Recursos da versão 0.15.0

Cidade com IBGE offline; endereço pelo CEP; consulta de CNPJ com prévia; cópia automática da edição da NF-e e do produto; painel de pendências; certificado, estoque e Google Drive reunidos na aba Geral.

Mantidos: importação assistida de produtos, clientes e fornecedores por planilha/XML; modelo XLSX; backup automático e restauração guiada; central de rejeições com atalhos de correção; estoque opcional por empresa; pacote contábil mensal; clonagem de notas; cópia adicional dos XML para pasta sincronizada do Google Drive.

Leia **LEIA-PRIMEIRO.md**, **COBERTURA.md** e **VALIDACAO.md** para instruções e limites. O projeto ainda não cobre todos os recursos de um ERP nem todos os cenários fiscais. Escopo atual: AL/SVRS, A1, modelo 55, CRT 1/3 e ano de 2026. Homologue as operações antes de usar produção.

## Publicar atualizações

O repositório contém código e recursos, sem dados de empresas, senhas, certificados ou binários do runtime. O workflow **Publicar VF Emissor para Windows** prepara o Python embarcado oficial, instala as dependências públicas, executa testes, compila e verifica o instalador antes de publicar.

Ao enviar uma nova versão em `version.json` à branch `main`, o workflow inicia automaticamente. Também é possível publicar a tag correspondente `vX.Y.Z` ou executar o workflow manualmente. O programa consulta Releases deste repositório ao iniciar uma nova execução.

## Desenvolvimento

Requer Python 3.12 no Windows. Execute `python scripts/bootstrap_windows.py` para preparar o runtime e depois `portable\python.exe -m unittest discover -s tests`. Para uso portátil, execute `INICIAR-WINDOWS.bat`.

O programa mantém o arquivo fiscal original no PC. A opção Google Drive faz somente uma cópia adicional para uma pasta sincronizada configurada pelo usuário.
