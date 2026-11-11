VF Emissor 0.16.2

- Corrige o erro Cannot read properties of null (reading checked) ao carregar o A1: o botão agora abre o formulário atual, com persistência marcada por padrão.
- Unifica o formulário do certificado e captura arquivo, senha e preferência antes da leitura assíncrona. Fechamento da janela ou troca de empresa interrompem a operação antes do envio.
- Certificado e senha são salvos no cofre DPAPI da conta do Windows, separados por empresa, e recarregados automaticamente nos próximos acessos/reinícios.
- Mensagens distinguem gravação protegida e uso somente na sessão; senha do formulário é limpa após a operação.

Encerre o emissor antes de instalar manualmente. A atualização automática continua pelo atalho e pelo canal VF-Emissor. Cadastros, modelos, XML e cofres existentes são preservados. Depois de atualizar, carregue o A1 uma vez com a opção de salvar marcada. Em outro computador ou conta do Windows, carregue-o novamente.

Testes usam certificados sintéticos. Nenhuma senha ou certificado real foi utilizado. Cobertura fiscal preservada: AL/SVRS, A1, modelo 55, CRT 1/3 e 2026.
