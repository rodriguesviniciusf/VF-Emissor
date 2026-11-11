# Validação 0.16.2

Correção do formulário/handler de certificado e da leitura assíncrona da preferência de persistência. Testes de regressão da interface exercitam o código real do app com DOM de teste e cobrem abertura do formulário atual, persistência padrão, formulário legado sem checkbox, opção desmarcada, ausência de arquivo, falha e mudança de contexto/janela.

Os testes Python existentes exercitam o cofre separado por empresa, proteção contra adulteração, ausência de senha/PFX em texto claro, recuperação após reinício e DPAPI nativa no Windows. O workflow executa a suíte completa e a instalação/reinstalação antes de publicar.

Somente dados e certificados sintéticos são usados nos testes. Nenhum certificado real nem transmissão fiscal real é necessário para essa correção.
