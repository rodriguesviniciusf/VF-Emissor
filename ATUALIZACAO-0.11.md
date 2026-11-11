# VF Emissor Web 0.11.0 beta

Esta atualização usa o ZIP enviado em 10/11/2026 como base. Mantém o login por empresa, edição de destinatário/emitente na nota, observações do item, opção de atualizar o cadastro do produto, exclusão de rascunho, prévia de DANFE e os demais arquivos da versão recebida.

## Instalar sem perder seus dados

1. Encerre o emissor e faça uma cópia da sua pasta completa atual.
2. Extraia este ZIP em uma pasta nova. Ele contém programa, código e Python portátil; não contém a pasta `dados`.
3. Copie a pasta **dados inteira da sua versão atual**, com o programa encerrado, para dentro da nova pasta `VF-Emissor-Web`.
4. Execute `INICIAR-WINDOWS.bat`. Se já utiliza outro modo de inicialização, os arquivos de inicialização enviados foram mantidos.
5. Confira seus cadastros e rascunhos antes de continuar o trabalho.

## Produto na NF-e

- Um seletor de CST troca o grupo tributário correspondente e os campos disponíveis. A mudança de ICMS 20 para 41 remove os campos de ICMS próprio; PIS/COFINS por quantidade mostram quantidade e valor por unidade; IPI tributado e não tributado usam grupos distintos.
- Resumo lateral e cartões dos impostos atualizam durante a digitação. A resposta de um cálculo anterior não substitui um resultado mais recente.
- MVA aparece na modalidade 4; pauta abre o preço unitário. A base ST pode ser informada manualmente ou calculada pela modalidade explicitamente selecionada.
- Fórmula ST por MVA: `(valor do item - desconto + frete + seguro + despesas + IPI) × (1 + MVA/100) × (1 - redução/100)`. Pauta: `quantidade × preço de pauta × (1 - redução/100)`. Modalidade 6: valor da operação acrescido de IPI e reduzido pelo percentual informado. O ICMS próprio ou a dedução informada é subtraído do imposto ST.
- As fórmulas não implementam cálculo por dentro, ajuste automático de MVA ou definição de enquadramento. Nesses casos, informe a base final revisada. Itens antigos continuam com sua base manual se não houver seleção explícita da fórmula.
- A prévia pode calcular um formulário ainda incompleto. A conferência e a preparação fiscal continuam exigindo os campos, os grupos e a validação estrita do XML.
- IBS/CBS usa a cópia da tabela oficial SVRS consultada em 10/11/2026. CST filtra as classificações para NF-e e suas vigências na data do rascunho. Os indicadores abrem os grupos básicos, redução e diferimento. Percentuais de redução vêm da classificação selecionada; alíquotas e demais condições da operação precisam de revisão.

## Configurações

Abas **Geral**, **Fiscal**, **Dados tributários**, **Contábil**, **Certificado** e **Backup e exportação**.

- Dados gerais: cadastro da empresa, IM e CNAE. Nome fantasia, IM e CNAE passam para o XML quando informados e válidos.
- Fiscal: ambiente, séries, numeração, natureza, CFOP, destinatário final, presença, frete, pagamento, perfil padrão, município do fato gerador, autorizados a acessar o XML e textos adicionais.
- Preferências valem para novas notas e novos itens; documentos existentes mantêm seus dados. Autorizações de XML e município do fato gerador ficam visíveis no rascunho para revisão.
- Dados tributários: lista e acesso aos perfis existentes e revisão do regime da empresa.
- Contábil: cadastro persistente do contador e exportação do relatório CSV.
- Certificado: operações já existentes do A1 e consulta de status da SEFAZ.
- Backup: cópia dos dados e instruções de restauração.

## Cobertura

Esta atualização aproxima a interface e o comportamento do NF-e Mais; não reproduz todos os módulos desse serviço. SMTP e envio automático, configuração multiusuário por papéis, API pública, NFS-e/NFC-e, distribuição automática DF-e e demais pendências da versão anterior não foram integrados nesta atualização. Os dados do contador são um cadastro para consulta, sem envio automático de documentos.

O conector fiscal continua AL/SVRS, CRT 1 ou 3, ano 2026, A1. Grupos especiais, regimes de produtos, regras estaduais e toda a reforma tributária não têm enquadramento automático completo. As listas e o XSD não substituem todas as regras da SEFAZ. O suporte RTC no XML do Simples Nacional continua pendente.

## Verificação

181 testes Python passaram: 118 do motor e 63 da camada web/regime normal/configurações. JavaScript passou pela verificação de sintaxe. Testes de navegador usaram somente dados fictícios e verificaram campos dinâmicos, valores calculados, configurações persistentes e rascunho salvo/reaberto com XML válido. Não houve transmissão de nota ou evento real. Não foi executado nativamente no Windows nem usado o A1 do usuário.

Tabela oficial: https://dfe-portal.svrs.rs.gov.br/Cff/ClassificacaoTributaria (cópia obtida em 10/11/2026). A atualização de tabelas continua manual.
