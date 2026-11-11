# Publicar atualizações do VF Emissor

O canal deste programa é `rodriguesviniciusf/VF-Emissor`. O repositório VF-Fiscal-Updates pertence a outro programa e não é usado por este emissor.

## Publicação automática

1. Atualize e teste o código na branch de trabalho.
2. Aumente a versão em `version.json`, sem reutilizar uma versão já publicada.
3. Envie a versão completa à branch `main`. Uma mudança em `version.json` dispara **Publicar VF Emissor para Windows**.
4. O GitHub prepara o Python oficial e dependências, executa os testes, compila o instalador e verifica instalação/reinstalação, atalho, preservação dos dados e recursos offline. A Release estável só é criada após aprovação dessas etapas.
5. A Release recebe `VF-Emissor-Setup-VERSAO.exe` e `update-manifest.json`. O lançador instalado consulta a última Release ao abrir pelo atalho, confere tamanho/SHA-256, preserva os dados e aplica a versão mais recente.

Também é possível executar o workflow manualmente em Actions ou enviar uma tag correspondente, como `v0.15.0`. Evite disparar os dois modos simultaneamente para a mesma versão. Para corrigir uma versão já publicada, incremente `version.json`.

## Código e dados

Versione código, schemas, recursos e `.github/workflows`. O runtime em `portable/` é gerado no CI por `scripts/bootstrap_windows.py`; não precisa ser enviado ao GitHub. Nunca publique a pasta de dados, XML de clientes, certificados, senhas, bancos ou backups.

O instalador usa o canal do próprio repositório de compilação. A pasta de dados fica em `%LOCALAPPDATA%\VFEmissor\Dados`, fora da instalação, com cadastros e configurações separados por empresa. Uma configuração antiga de canal pode ser conferida em **Configurações → Instalação e atualizações**.

## Compilar no Windows

Com Python 3.12 x64 e NSIS instalados, execute `python scripts/bootstrap_windows.py` e depois `scripts/build-release.ps1 -Repository rodriguesviniciusf/VF-Emissor`. Os arquivos ficam em `dist/`. Antes de distribuir, execute os testes e `scripts/smoke-install.ps1` em ambiente de avaliação.

Publicar atualização não transfere os XML do escritório para o GitHub. A cópia adicional dos XML é configurada em **Configurações → Geral → Estoque e Google Drive**.
