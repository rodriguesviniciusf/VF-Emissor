# Validação 0.16.3

Quatro testes de regressão verificam a prévia de produção com nome do destinatário, a manutenção da mensagem em homologação, o bloqueio do DANFE definitivo sem protocolo e o rodapé de prévia em todas as páginas de uma nota com 90 itens. Os quatro passaram localmente. A renderização de um PDF sintético foi conferida visualmente: destinatário legível, marca SEM VALOR FISCAL e rodapé sem sobrepor campos.

O XML de entrada permanece inalterado. A suíte completa e as verificações de instalação/reinstalação, atalho e preservação dos dados são executadas pelo workflow Windows antes de publicar a versão estável. Os testes não utilizam certificados reais nem transmitem notas fiscais reais.
