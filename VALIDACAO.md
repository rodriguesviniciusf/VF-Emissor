# Validação 0.16.0

## Verificações locais

- Motor fiscal/eventos: 118 testes aprovados.
- Web/desktop: 194 testes encontrados, 193 aprovados e 1 teste nativo de DPAPI inaplicável ao Linux.
- Total local: 311 aprovados e 1 teste exclusivo do Windows não executado no Linux.
- Os 30 testes do Modo Simples cobrem configuração por empresa, persistência/backup, liberação explícita, concorrência de configurações, contexto de UF/IE/regime, perfis e alterações, preços/descontos/pagamentos, produtos permitidos, igualdade de cálculo e XML nos CRT 1/3, confirmação do resumo, preparação/assinatura e envio simulado pelo fluxo atual, idempotência de rascunho e preparação, estados fiscais incertos, recuperação, passagem ao modo completo, ambiente, autenticação/CSRF e aba de empresa desatualizada.
- JavaScript, compilação Python e git diff --check verificados.

## Interface

Usada somente empresa fictícia de regime normal em homologação. Pela interface foram criados e liberados o modelo Venda rápida • Alagoas e a preferência de abertura Simples. Nova NF-e abriu o fluxo Cliente → Produtos → Conferir e emitir. Pasta organizadora, quantidade 3, preço 12,50 e desconto 1,50 resultaram em 36,00, com atualização durante a digitação e conferência aprovada.

Após guardar, reabrir a página e recuperar a edição, modelo, cliente, quantidade, desconto e observações foram preservados, exigindo nova conferência. A tentativa sem certificado foi bloqueada antes de gerar documento fiscal; ficou um único rascunho. A passagem ao modo completo preservou os dados e salvou a mesma nota. Nenhum A1 real nem transmissão real foi usado.

## Windows

O workflow da versão executa a suíte completa com Python portátil, DPAPI, sintaxe da interface, compilação NSIS, instalação/reinstalação, atalho e preservação dos dados. Também confere os arquivos do Modo Simples na instalação. O resultado final é publicado em Actions do repositório VF-Emissor antes da Release estável.

## Limites

A avaliação de interface e os testes sintéticos não substituem a homologação dos cenários fiscais com o A1 da empresa. A cobertura permanece AL/SVRS, modelo 55, A1, CRT 1/3, ano 2026. Operações e grupos especiais continuam no modo completo. XML e dados originais permanecem locais; o Drive realiza uma cópia adicional via sua pasta sincronizada.
