# Validação 0.14.0

## Testes automatizados

- Motor fiscal e eventos: 118 testes passaram.
- Web, configurações, desktop e rotinas operacionais: 133 testes encontrados; 132 passaram e 1 teste de DPAPI nativa foi ignorado no Linux.
- Total neste ambiente: **250 testes passaram; 1 teste nativo do Windows pendente**.
- JavaScript verificado com node --check e módulos Python compilados.

As novas verificações incluem: CSV/XLSX e XML; identificadores com zeros; importação parcial explícita; preservação de duplicados; prévias por empresa; gravação idempotente; fornecedores; preferências simultâneas em duas empresas; estoque desativado; saldo inicial; autorização/consulta repetida; estorno único; conversão de unidade; vínculos pendentes; direção de NF-e de entrada emitida por terceiro; segregação entre empresas e ambientes; ZIP contábil com eventos e cancelamento no mês seguinte; neutralização de fórmulas no CSV; backup filtrado e com manifesto; integridade; ZIP Slip; CNPJ divergente; confirmação escrita; rollback; restauração de versão anterior; restauração com novo identificador de empresa; retenção; upload em partes; rejeição com link de NCM; impedimento de correção de situação incerta; clonagem com pagamentos/totais e revisão; cópia adicional e falha de Drive sem alterar o XML local nem a autorização; reposição de XML ausente sem repetir estoque.

## Conferência visual

Com dados fictícios no navegador: importação do modelo XLSX com dois produtos; prévia e gravação; tela de estoque com saldo 28 após saldo inicial 30 e saída 2; central de rejeições e salto ao campo NCM; backup manual, lista e conferência da restauração com CNPJ/quantidades; configurações de estoque/Drive; formulário do pacote mensal. A restauração real foi testada em bancos temporários, não em dados do usuário.

A planilha exemplo foi criada e renderizada, com identificadores textuais conferidos no XLSX exportado. Não houve transmissão fiscal real nem uso de A1 real. Os retornos de autorização/cancelamento nos testes são sintéticos.

## Windows, SEFAZ e nuvem

O instalador é compilado para Windows. A execução nativa de instalação/reinstalação, DPAPI e atualização de ponta a ponta depende da validação no Windows. O workflow incluído prepara o runtime e executa testes, instalação, atalho, preservação de dados e inicialização antes da publicação.

A cópia de XML foi testada para uma pasta temporária, incluindo destino indisponível e repetição. Não foi feito upload a uma conta Google real. A sincronização efetiva depende da pasta/conta e do aplicativo Google Drive para computador configurados pelo usuário.

A homologação com seu A1 e as operações reais da empresa permanece necessária antes de habilitar produção.
