# Validação 0.16.1

## Verificações locais

- Motor fiscal/eventos: 118 testes aprovados.
- Web/desktop: 195 testes encontrados, 194 aprovados e 1 teste nativo de DPAPI inaplicável ao Linux.
- Total local: 312 aprovados e 1 teste exclusivo do Windows não executado no Linux.
- Os 31 testes do Modo Simples cobrem configuração por empresa, persistência/backup e restauração em outra instalação, liberação explícita, concorrência de configurações, contexto de UF/IE/regime, perfis e alterações, preços/descontos/pagamentos, produtos permitidos, igualdade de cálculo e XML nos CRT 1/3, confirmação do resumo, preparação/assinatura e envio simulado pelo fluxo atual, idempotência de rascunho e preparação, estados fiscais incertos, recuperação, passagem ao modo completo, ambiente, autenticação/CSRF e aba de empresa desatualizada.
- JavaScript, compilação Python e git diff --check verificados.

## Interface

Usada somente empresa fictícia de regime normal em homologação. Pela interface foram criados e liberados o modelo Venda rápida • Alagoas e a preferência de abertura Simples. Nova NF-e abriu o fluxo Cliente → Produtos → Conferir e emitir. Pasta organizadora, quantidade 3, preço 12,50 e desconto 1,50 resultaram em 36,00, com atualização durante a digitação e conferência aprovada.

Após guardar, reabrir a página e recuperar a edição, modelo, cliente, quantidade, desconto e observações foram preservados, exigindo nova conferência. A tentativa sem certificado foi bloqueada antes de gerar documento fiscal; ficou um único rascunho. A passagem ao modo completo preservou os dados e salvou a mesma nota. Nenhum A1 real nem transmissão real foi usado.

## Windows

O workflow [43016451279](https://github.com/rodriguesviniciusf/VF-Emissor/actions/runs/43016451279) concluiu com sucesso em 11/11/2026 para o código 02d588546983b0892492598c9d616764f6cbbe8a. Foram aprovados 118 testes do motor e 194 dos 195 testes web/desktop. O único teste ignorado no Windows aplica-se a plataformas sem DPAPI; a proteção nativa DPAPI foi exercitada.

Também passaram sintaxe da interface, compilação NSIS, instalação e reinstalação silenciosas, atalho na área de trabalho, preservação do marcador na pasta de dados, inicialização da versão instalada e disponibilidade do catálogo offline e dos arquivos do Modo Simples. As consultas reais de CEP e CNPJ retornaram sucesso. A Release v0.16.1 foi publicada após essas verificações.

O instalador publicado tem 22.499.935 bytes e SHA-256 `68b2ea71bdc123c633c0e69f741f3e71e377d40fda8a31683c7a996336aa8e2d`. O download foi conferido e corresponde ao manifesto de atualização e ao digest publicado no GitHub.

## Limites

A avaliação de interface e os testes sintéticos não substituem a homologação dos cenários fiscais com o A1 da empresa. A cobertura permanece AL/SVRS, modelo 55, A1, CRT 1/3, ano 2026. Operações e grupos especiais continuam no modo completo. XML e dados originais permanecem locais; o Drive realiza uma cópia adicional via sua pasta sincronizada.
