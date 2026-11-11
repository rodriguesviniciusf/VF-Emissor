# Validação 0.14.0

## Testes automatizados

- Motor fiscal e eventos: 118 testes passaram.
- Web, configurações, desktop e rotinas operacionais: 133 testes encontrados; 132 passaram e 1 teste de DPAPI nativa foi ignorado no Linux.
- Total no Linux: **250 testes passaram; 1 teste de DPAPI nativa não se aplica ao Linux**.
- JavaScript verificado com node --check e módulos Python compilados.

As novas verificações incluem: CSV/XLSX e XML; identificadores com zeros; importação parcial explícita; preservação de duplicados; prévias por empresa; gravação idempotente; fornecedores; preferências simultâneas em duas empresas; estoque desativado; saldo inicial; autorização/consulta repetida; estorno único; conversão de unidade; vínculos pendentes; direção de NF-e de entrada emitida por terceiro; segregação entre empresas e ambientes; ZIP contábil com eventos e cancelamento no mês seguinte; neutralização de fórmulas no CSV; backup filtrado e com manifesto; integridade; ZIP Slip; CNPJ divergente; confirmação escrita; rollback; restauração de versão anterior; restauração com novo identificador de empresa; retenção; upload em partes; rejeição com link de NCM; impedimento de correção de situação incerta; clonagem com pagamentos/totais e revisão; cópia adicional e falha de Drive sem alterar o XML local nem a autorização; reposição de XML ausente sem repetir estoque.

## Conferência visual

Com dados fictícios no navegador: importação do modelo XLSX com dois produtos; prévia e gravação; tela de estoque com saldo 28 após saldo inicial 30 e saída 2; central de rejeições e salto ao campo NCM; backup manual, lista e conferência da restauração com CNPJ/quantidades; configurações de estoque/Drive; formulário do pacote mensal. A restauração real foi testada em bancos temporários, não em dados do usuário.

A planilha exemplo foi criada e renderizada, com identificadores textuais conferidos no XLSX exportado. Não houve transmissão fiscal real nem uso de A1 real. Os retornos de autorização/cancelamento nos testes são sintéticos.

## Windows, SEFAZ e nuvem

A execução [GitHub Actions #2](https://github.com/rodriguesviniciusf/VF-Emissor/actions/runs/42939901559), de 11/11/2026 UTC, passou no Windows: 118 testes do motor e 132 testes web/desktop; o teste exclusivo de plataformas sem DPAPI foi ignorado. A DPAPI nativa foi exercitada, incluindo reabertura do cofre em outro processo. O instalador foi instalado e reinstalado, com conferência do atalho na área de trabalho, preservação da pasta de dados e inicialização da versão 0.14.0. O arquivo publicado foi baixado e conferido pelo tamanho e SHA-256 do manifesto.

O primeiro fluxo detectou uma falha nos separadores do ZIP ao calcular o manifesto com o arquivo ainda aberto para escrita. A correção foi incluída no commit compilado `f21fcc28859258be06dcd72b1e1bf29018f9dea3`; a segunda execução passou.

O instalador oficial publicado tem SHA-256 `67041896f92f9babbc00f4c5c92a54414dc993cbd0567c9bd6989a4fd838415a` e 22.438.160 bytes. A verificação/download de atualizações possui testes automatizados; uma atualização completa pelo atalho com dados reais do escritório ainda precisa ser acompanhada no PC do usuário.

A cópia de XML foi testada para uma pasta temporária, incluindo destino indisponível e repetição. Não foi feito upload a uma conta Google real. A sincronização efetiva depende da pasta/conta e do aplicativo Google Drive para computador configurados pelo usuário.

A homologação com seu A1 e as operações reais da empresa permanece necessária antes de habilitar produção.
