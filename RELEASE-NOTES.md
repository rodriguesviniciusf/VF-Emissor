VF Emissor 0.17.0

- Consulta automática do NCM completo no cadastro de produtos e no item da NF-e (Simples e Regime Normal): descrição, grupo completo, período informado pela fonte e referência da tabela oficial Receita/Siscomex.
- Pesquisa por código ou palavras da descrição. Seleção explícita do código, preservando a descrição comercial e os tributos do produto.
- Catálogo oficial offline com 10.516 NCM e 15.157 nós (referência inicial 11/11/2026), atualização diária em segundo plano e atualização manual. Falhas mantêm a última cópia e exibem aviso. A fonte contém somente a tabela vigente; consultas históricas/futuras ou sem tabela atual não são declaradas inválidas por mera ausência.
- Conferência local de NCM antes da preparação/primeira transmissão, com link para corrigir o item. O Modo Simples usa a mesma verificação e exibe os avisos de vigência.
- Configurações > Fiscal: lista de naturezas de operação por empresa, com inclusão e exclusão inclusive das opções iniciais. Sugestões disponíveis na NF-e, no padrão fiscal e nos modelos do Modo Simples. Exclusões não reescrevem notas, padrões ou modelos existentes e são preservadas no backup/restauração.
- NF-e de fornecedor/recebidas: botão Excluir importação com confirmação. Remove a importação das listas e do pacote mensal; estorna uma única vez os movimentos de estoque vinculados, mesmo com controle desativado. Preserva XML e eventos locais, movimentos originais e histórico. Não cancela a nota na SEFAZ nem altera notas emitidas. Reimportar o XML após a exclusão permite registrá-lo novamente.

Instale com o emissor encerrado ou abra novamente pelo atalho para receber a atualização do canal rodriguesviniciusf/VF-Emissor. Cadastros, XML, modelos e certificados protegidos são preservados. Não utiliza o canal VF-Fiscal-Updates.

Testes com documentos sintéticos; nenhuma NF-e real foi transmitida. Cobertura fiscal preservada: AL/SVRS, A1, modelo 55, CRT 1/3 e 2026. A consulta de vigência não determina a classificação adequada à mercadoria nem garante autorização pela SEFAZ.
