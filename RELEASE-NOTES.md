VF Emissor 0.16.1

- Modo Simples com três etapas: Cliente → Produtos → Conferir e emitir.
- Tela própria em Configurações → Geral → Modo Simples, sem acrescentar abas. Preferência de abertura e modelos separados por empresa.
- Modelos por UF de destino e indicador de IE, com natureza, consumidor final, presença, pagamento, frete, observações e perfil tributário por produto ou pelo modelo.
- Liberação explícita dos modelos revisados, controle de versão, seleção opcional de produtos e permissões comerciais para preço, desconto e pagamento.
- Quantidade, preço, desconto e frete por item; totais calculados pelo motor existente. Fatura, parcelas e dados de transporte disponíveis no preenchimento.
- Conferência final com confirmação explícita para preparar e transmitir pelo mesmo serviço fiscal do modo completo.
- Recuperação da edição, revalidação após mudanças em cadastros/modelos e passagem ao modo completo preservando o preenchimento.
- Tentativas repetidas da mesma edição reutilizam o rascunho e sua numeração. Situações fiscais incertas seguem as consultas/bloqueios existentes.
- Configuração incluída no backup da empresa e identificada na prévia de restauração, com remapeamento correto ao restaurar em outra instalação.
- Pendências com atalhos para o campo correspondente e produtos ordenados pelo histórico do cliente.

Primeiro configure e libere um modelo em Geral; depois escolha Simples como modo padrão. Os modelos atendem NF-e normal de saída dentro da cobertura atual. ST, bases/valores retidos específicos, grupos ou ajustes especiais e pagamentos que exijam detalhamento adicional continuam no modo completo. O modelo não deduz enquadramento fiscal nem habilita produção.

Encerre o programa antigo antes de instalar manualmente. O atalho configurado no canal VF-Emissor verifica esta atualização ao iniciar uma nova execução. Dados, certificados protegidos e XML permanecem no PC e separados por empresa. Google Drive continua sendo uma cópia adicional para pasta sincronizada.

Cobertura fiscal preservada: AL/SVRS, A1, modelo 55, CRT 1/3 e 2026. Foram usados cadastros fictícios e certificado sintético nos testes; nenhuma nota real foi transmitida. Valide os cenários da empresa em homologação antes de usar produção.
