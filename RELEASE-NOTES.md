VF Emissor 0.18.0

- AL → destinatários de todas as UFs brasileiras, incluindo Distrito Federal. AL → AL permanece interna; autorizador AL/SVRS e CRT 1/3 preservados.
- Conferência de operação/CFOP, limites de ICMS interestadual, origem importada, falta/contexto do DIFAL, partilha para emissão normal 2026, valores de DIFAL/FCP e IE isenta conforme NT 2025.001 v1.03, com exceções documentadas. Erros levam ao campo do item; assinatura/envio não ignoram a conferência.
- Botão Preparar operação interestadual no item da nota: CFOP conferido, referência interestadual da origem e DIFAL com alíquota interna/FCP informados pelo operador. Aplica somente no item, exige nova revisão e não altera cadastro, CST, benefícios ou notas antigas.
- Configurações > Fiscal > Alagoas → todo o Brasil: referências de ICMS interno/FCP por UF e empresa, com vigência, fundamento, edição e exclusão. Incluídas no backup e restauração inclusive em outra instalação da mesma empresa.
- Modo Simples confere os perfis no contexto da UF do modelo antes de disponibilizar os produtos.
- Testes estruturais em 27 UFs, dois regimes, dois indicadores de IE e dois ambientes, mais cenários importados, exceções e regressões. Não transmite NF-e reais nem usa certificado real.

Instalador Windows com o canal rodriguesviniciusf/VF-Emissor. Dados locais, XML e cofre A1 preservados. ST/MVA, benefícios e alíquotas internas/FCP dependem da mercadoria e da legislação revisada; não há emissão automática de guias nem garantia de autorização. Consulte REGRAS-INTERESTADUAIS.md. Mantido o escopo A1/modelo 55/emissão em 2026 e as limitações anteriores de cenários especiais do Simples Nacional.
