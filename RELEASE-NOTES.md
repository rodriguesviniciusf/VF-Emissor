VF Emissor 0.15.0

- Município com pesquisa por UF e código IBGE automático, usando tabela oficial incluída no instalador. Pesquisa disponível sem internet e identificação reversa pelo código.
- Consulta de CEP pelo ViaCEP, com endereço/município/UF/IBGE, prévia e aplicação seletiva. Número e complemento permanecem para conferência.
- Consulta pontual de CNPJ pela BrasilAPI, com prévia dos dados e indicação de situação cadastral/CNAE. IE, regime e tributação não são substituídos.
- Cópia automática da edição da NF-e, incluindo produto ainda aberto, no banco local por empresa/ambiente. Recuperação após reinício, controle de versões e opção de nova nota quando a original mudou ou foi finalizada. Sem reservar numeração ou transmitir XML.
- Painel de pendências: cópias recuperáveis, vencimento do A1, backup pendente/atrasado e cópias de XML pendentes para o Drive.
- Configurações simplificadas: certificado, estoque e Google Drive reunidos em Geral, reduzindo oito abas para seis e mantendo a gravação por empresa.
- Proteção de contexto para impedir gravações de uma aba antiga após troca de empresa em outro acesso.
- Publicação de instaladores pelo GitHub ao enviar uma nova versão em version.json para main.

Encerre o programa antigo antes de instalar manualmente. Os dados da instalação continuam na pasta fixa do usuário. Ao abrir pelo atalho, a versão 0.14.0 configurada neste repositório pode receber esta atualização automaticamente.

CEP/CNPJ dependem da internet e da disponibilidade dos serviços públicos. As consultas não enviam XML, certificados ou senhas. Os XML originais continuam no PC de emissão; Google Drive permanece uma cópia adicional.

Cobertura fiscal preservada: AL/SVRS, A1, modelo 55, CRT 1/3 e 2026. Valide os cenários da empresa em homologação antes da produção.
