# Referência e implementação

Data: 10/11/2026. Referência: NF-e Mais, conta fornecida pelo usuário, observação autenticada da lista de NF-e e formulários de nota e produto. Nenhuma nota ou alteração de cadastro foi salva no serviço de referência.

Foram observados: barra lateral escura, cabeçalho azul, ações verdes, abas NF-e / C. Correção / NFe Fornecedor / Recebidas, listagem por período e formulário de nota dividido em seções. O produto apresenta identificação e valores separados dos grupos tributários. A versão própria organiza os grupos em abas ICMS / ICMS ST / FECOEP ST / IPI / PIS / COFINS.

REA 6.8.0 foi executado por CLI em dois arquivos JavaScript públicos de referência (`det.class.js`, `detICMS.class.js`), sem executar o código analisado. Foram lidos 33.410 bytes, com duas fontes JavaScript analisadas sem erro de parsing. O relatório declara 78 pontos semânticos desconhecidos; a análise estática não comprova equivalência de comportamento nem dá acesso ao backend. O digest do artefato local analisado foi `7d922df709518679cb8592a84f78affcdd3cc51eede1dc9019843404153db56c`.

O frontend foi escrito do zero. O motor fiscal reutiliza o código do projeto VF Emissor 0.8.0 disponibilizado pelo próprio usuário, preservando validações e limites. Não há chamadas à API privada do NF-e Mais nem incorporação de seu código, logos, imagens, credenciais ou servidores no aplicativo.

O resultado é uma primeira versão funcional local, não uma reprodução integral ou certificação de compatibilidade com todas as funções do NF-e Mais. A cobertura e pendências estão no LEIA-PRIMEIRO.md.

## Atualização do regime normal

Em 10/11/2026, o acesso à empresa do regime normal foi realizado pelo formulário protegido. Confirmados CRT 3, emitente em AL e os grupos tributários apresentados no produto. O site informa que os campos RTC estão desativados nessa conta. Um XML autorizado foi baixado para conferir as bases e cálculos; não foram salvas notas nem alteradas configurações no serviço de referência. Credenciais, XML privado, identificadores e dados comerciais não integram a distribuição.

A ampliação foi implementada em código próprio, usando o XSD instalado para a definição dos campos. O acesso à referência não oferece o backend nem comprova que todos os cenários e funções foram reconstruídos.


## Comparação da interface — 10/11/2026, atualização 0.11

Consulta autenticada somente para leitura: abas Geral, Fiscal, Dados tributários e Contábil; dados da NF-e e campos padrão; cadastro do contador; formulário vazio de produto na nota. Foram observadas mudanças de CST e modalidade sem salvar a nota, o produto ou as configurações. A implementação local separa as configurações e faz o CST controlar a estrutura tributária correspondente, com resumo dos cálculos visível. Os módulos não integrados continuam documentados; não foram criados botões simulando envio automático, usuários por papéis ou API pública. Nenhuma credencial, certificado ou dado da empresa de referência foi incluído no código.
