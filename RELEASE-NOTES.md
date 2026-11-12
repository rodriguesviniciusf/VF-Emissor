VF Emissor 0.19.1

- Cadastro por e-mail/senha sem confirmação automática, pendente da administração; cada CNPJ possui solicitação e validade próprias.
- Painel com pendentes, ativos, vencimentos, vencidos, aprovar conta e empresa juntos, renovar 1/3/6/12 meses, suspender/reativar, computadores e histórico.
- Supabase Auth, tabelas protegidas, RPCs de autorização e Edge Function com assinatura Ed25519 vinculada à instalação. Recuperação assistida por código de uso único após conferência de identidade.
- Verificações nas rotas reais antes de preparar/transmitir; vencimento preserva consulta, XML e backup. Tokens e senha da conta não são persistidos no cliente.
- O instalador já inclui a configuração pública do acesso comercial. A atualização também exige e-mail/senha e aprovação dos CNPJs antigos, preservando cadastros, configurações, certificados e XML locais. O login antigo por CNPJ não libera a área fiscal.
- Recuperação da senha da administração por link enviado ao titular; renovação e recuperação assistida dos clientes pelo painel.
- Atualização pelo canal estável do GitHub, com teste de instalação sobre a versão real 0.18.0 e conferência do bloqueio do login anterior.
- Testes PostgreSQL/PGlite, HTTP, criptografia, Edge Function e regressões. Conferência visual com dados fictícios. Nenhum A1 real ou transmissão SEFAZ.

Histórico — VF Emissor 0.18.0

- AL → destinatários de todas as UFs brasileiras, incluindo Distrito Federal. AL → AL permanece interna; autorizador AL/SVRS e CRT 1/3 preservados.
- Conferência de operação/CFOP, limites de ICMS interestadual, origem importada, falta/contexto do DIFAL, partilha para emissão normal 2026, valores de DIFAL/FCP e IE isenta conforme NT 2025.001 v1.03, com exceções documentadas. Erros levam ao campo do item; assinatura/envio não ignoram a conferência.
- Botão Preparar operação interestadual no item da nota: CFOP conferido, referência interestadual da origem e DIFAL com alíquota interna/FCP informados pelo operador. Aplica somente no item, exige nova revisão e não altera cadastro, CST, benefícios ou notas antigas.
- Configurações > Fiscal > Alagoas → todo o Brasil: referências de ICMS interno/FCP por UF e empresa, com vigência, fundamento, edição e exclusão. Incluídas no backup e restauração inclusive em outra instalação da mesma empresa.
- Modo Simples confere os perfis no contexto da UF do modelo antes de disponibilizar os produtos.
- Testes estruturais em 27 UFs, dois regimes, dois indicadores de IE e dois ambientes, mais cenários importados, exceções e regressões. Não transmite NF-e reais nem usa certificado real.

Instalador Windows com o canal rodriguesviniciusf/VF-Emissor. Dados locais, XML e cofre A1 preservados. ST/MVA, benefícios e alíquotas internas/FCP dependem da mercadoria e da legislação revisada; não há emissão automática de guias nem garantia de autorização. Consulte REGRAS-INTERESTADUAIS.md. Mantido o escopo A1/modelo 55/emissão em 2026 e as limitações anteriores de cenários especiais do Simples Nacional.
