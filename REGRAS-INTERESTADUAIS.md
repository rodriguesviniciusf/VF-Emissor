# AL → Brasil — fontes e alcance da versão 0.18.0

Conferência realizada em 12/11/2026. Emitente permanece AL/SVRS. O destino não muda o autorizador do emitente.

| Verificação | Implementação / limites |
|---|---|
| UF, IBGE, tipo e CFOP | UFs brasileiras, município compatível, idDest interno/interestadual e prefixo do CFOP, tabela oficial instalada, indicadores de devolução/retorno/remessa. Não converte arbitrariamente CFOPs por trocar o primeiro dígito. |
| ICMS próprio, N16-20/693 e N16-04/663 | Limites em saídas normais AL; referência 12% para origens nacionais/exceções e 4% para origens 1/2/3/8 nos CST pertinentes. Alíquotas menores não são elevadas pela validação. Retornos/anulações da tabela, operações à ordem e grupo ICMSPart são tratados separadamente. O assistente aplica referência apenas após ação do operador. |
| DIFAL, NA01-20/694 | Em saída interestadual normal para consumidor final não contribuinte CRT 3, exige grupo quando não se enquadra nas exceções contempladas. Não exige automaticamente em CRT 1, entrada, complementar/ajuste, CST 40/41, partilha especial, CFOP de retorno/remessa, CFOP 6552/6922/6929 ou devolução com chave anterior a 2016. Produtos combustíveis/veículos/serviços e entrega/retirada em UF diversa não são integrados ao formulário atual; não são presumidos como exceções. |
| Contexto DIFAL, NA01-30/695 | Confere interestadual, consumidor final e não contribuinte; a ausência de exigência não significa proibição universal do grupo. |
| NA09 / 697-698 e NA11 / 699 | Origem e alíquota do DIFAL verificadas nas operações normais pertinentes; partilha 100% no ano de emissão normal 2026. Não força essa partilha em devoluções/retornos/complementos que dependem da nota original. |
| Valores | Recalcula DIFAL/FCP nas bases automáticas e confere valores manuais com tolerância de um centavo. FCP tem campo próprio, separado da alíquota interna. Bases especiais/por dentro exigem informação e conferência manual. |
| E16a-30 / 805 | Lista atual da NT 2025.001 v1.03: AL, AM, BA, CE, DF, ES, GO, MG, MS, MT, PB, PE, RJ, RN, RS, SE, SP. Considera exceções de ST destacada/retida e operações integralmente isentas/imunes/não tributadas. Não modifica a condição cadastral para contornar rejeição. Configuração do autorizador e cadastro real continuam prevalecendo. |

## Fontes oficiais consultadas

- Resolução do Senado 22/1989: https://legis.senado.leg.br/norma/586152/publicacao/15646891
- Resolução do Senado 13/2012: https://legis.senado.leg.br/norma/586999/publicacao?tipoDocumento=RSF&tipoTexto=ATU
- MOC 7.0, Anexo I, pp. 86, 109–110 e 115–117 (Confaz): https://www.confaz.fazenda.gov.br/legislacao/arquivo-manuais/moc7-anexo-i-leiaute-e-rv.pdf
- NT 2025.001 v1.03, p.9 (substitui a relação antiga de IE): https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?AspxAutoDetectCookieSupport=1&conteudo=NvuzQGYd6E8%3D
- NT 2025.002-RTC v1.30, NA01-20 e exceções: https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=6vT0rTNhFLY%3D
- Orientação SEFAZ/AL sobre alíquotas interestaduais: https://www.sefaz.al.gov.br/nise/faq/icms/465-2-difal-3-base-de-calculo-e-aliquotas

## Parâmetros por produto e UF

Não há uma alíquota interna ou FCP universal para cada UF. Os valores salvos em Configurações > Fiscal são referências da empresa, com vigência e fundamento, e devem ser confirmados para a mercadoria antes de aplicar no item. A instalação não inclui uma tabela genérica de alíquotas estaduais preenchida automaticamente. Obrigações de ST, MVA, antecipação, benefícios, DIFAL do adquirente contribuinte e recolhimentos não são decididas pelo endereço ou NCM isoladamente. Não emite GNRE ou guias estaduais. A autorização e a situação cadastral são verificadas pela SEFAZ na transmissão.
