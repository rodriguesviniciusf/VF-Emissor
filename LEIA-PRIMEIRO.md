# VF Emissor 0.16.0 — Windows

## Instalar e abrir

1. Encerre a versão antiga do emissor.
2. Execute **VF-Emissor-Setup-0.16.0.exe** e conclua a instalação. Requer Windows 10/11 de 64 bits.
3. Abra o atalho **VF Emissor** criado na área de trabalho ou no menu Iniciar.
4. Se você já usava a versão anterior, antes de cadastrar empresas clique em **Já usava o emissor? Importar meus dados** e informe o caminho da pasta antiga do emissor ou sua pasta `dados`. A origem não será apagada.
5. Entre com o CNPJ e a senha da empresa que já utilizava. Não é necessário refazer os cadastros após a importação.

O programa é instalado no Windows e usa o navegador para sua interface. O serviço local inicia pelo atalho. Para encerrar por completo, use **Encerrar programa**. Fechar apenas a aba do navegador mantém o serviço em execução; clicar no atalho enquanto ele já está aberto reaproveita a instância existente.

## Seus dados ficam em lugar fixo

`%LOCALAPPDATA%\VFEmissor\Dados`

A pasta de instalação é separada: `%LOCALAPPDATA%\Programs\VFEmissor`.

Cadastros, notas e configurações ficam no banco local. Os XML emitidos são arquivados em `Dados\notas-fiscais\CNPJ\ambiente\ano-mês`. Os XML importados ficam em `Dados\xml-importados\empresa`. Abra a pasta dos XML em **Configurações → Instalação e atualizações**.

Cada empresa tem seus próprios cadastros, perfis, parâmetros e documentos. Downloads e backup são filtrados pela empresa acessada. Atualizar ou desinstalar o programa não apaga a pasta fixa de dados.

## Certificado e senha

Em **Configurações → Geral → Certificado A1**, selecione o A1 da empresa e deixe marcada a opção de salvar neste computador. Arquivo e senha são guardados juntos, criptografados pela DPAPI da conta do Windows. O certificado é restaurado nos próximos acessos sem selecionar o PFX e digitar a senha novamente.

O cofre é separado por empresa. Um certificado vencido ou que não possa ser aberto gera uma indicação para recarregá-lo. Em outro computador/conta do Windows, carregue o A1 novamente. Use **Remover A1 salvo** para apagar somente o cofre da empresa ativa.

## Produtos

A página Produtos carrega a listagem ao abrir. Digite descrição, código ou NCM para reduzir a lista. Dentro da nota, clique em **Nome do produto** ou **Escolher produto cadastrado**: a lista abre antes de digitar e preenche os dados ao selecionar. Produtos salvos pelo item da nota entram imediatamente no cadastro e na lista.

## Atualizações

O atalho verifica atualizações automaticamente no início de uma nova execução. Quando houver uma versão estável mais recente no canal configurado, o programa baixa e confere o instalador, faz uma cópia do banco antes da atualização e instala antes de abrir a emissão. Os dados locais são preservados. Sem internet ou com falha na conferência, abre a versão instalada e tenta novamente na próxima inicialização.

O canal do emissor é configurado para o repositório próprio VF-Emissor. As atualizações exigem a publicação de uma Release estável com instalador e manifesto nesse repositório. Em **Configurações → Instalação e atualizações**, confira o canal. O canal de outro programa não deve ser usado.

Para publicar versões, use o pacote de código e leia **PUBLICAR-ATUALIZACOES.md**. Nenhum CNPJ, XML, certificado ou senha precisa ir para o GitHub.

## Verificação e limites

Leia **VALIDACAO.md** e **COBERTURA.md**. O fluxo da versão 0.15.0 executa testes nativos do Windows, DPAPI e verificações de instalação/reinstalação, atalho, preservação de dados e catálogo offline antes da publicação. Consulte o resultado desta versão em VALIDACAO.md. A homologação com seu A1 e seus cenários fiscais ainda precisa ser realizada antes de habilitar produção.

## Visual 0.14.0

O ambiente de trabalho segue a tela de acesso: verde escuro, tons de sálvia, formulários claros, navegação com ícones, tabelas e janelas com mais espaço. A tela inicial destaca valores autorizados, quantidade de notas, rascunhos e produtos; os indicadores de notas respeitam o período e a busca aplicados. Em telas menores, o menu passa para a parte inferior.

## Importar cadastros

Abra **Produtos**, **Clientes** ou **Fornecedores → Importar planilha / XML**. Baixe a planilha exemplo XLSX, substitua os exemplos e preserve a primeira linha. O programa escolhe a aba correspondente ao tipo de cadastro. Aceita também CSV UTF-8/Windows-1252 e cadastros de XML modelo 55, até 8 MB e 10.000 linhas. A prévia mostra dados, erros e duplicados. Cadastros existentes não são sobrescritos. Linhas inválidas só são ignoradas se você marcar essa escolha.

Extrair cadastros de uma NF-e não registra entrada nem define a tributação dos produtos. Para registrar o documento, use **Importar XML**. XML de documentos só pode ser registrado se pertencer à empresa acessada; a extração de cadastros pode usar outra NF-e como fonte.

## Backup automático e restauração

Em **Configurações → Backup e exportação**, escolha Sim/Não, intervalo e retenção. Por padrão, o programa verifica um backup a cada 24 horas enquanto estiver aberto, inclusive ao iniciar. Não é um agendador que funciona com o programa encerrado. A pasta padrão é `Dados\backups-empresas\CNPJ`; você pode escolher outra pasta existente. A retenção remove somente os backups automáticos excedentes desta empresa; os manuais permanecem.

Use **Fazer backup agora** a qualquer momento. **Ver backups disponíveis** permite baixar ou conferir uma restauração. Também é possível selecionar um ZIP do VF Emissor, enviado em partes, até 250 MB. O assistente verifica CNPJ, integridade e conteúdo, pede confirmação escrita e cria um backup do estado anterior. A substituição afeta somente a empresa acessada, mantendo as outras empresas. Após restaurar, a produção fica desabilitada até você revisar série e numeração com a SEFAZ e outros emissores. O A1 pode precisar ser recarregado em outra conta do Windows/PC.

## Central de rejeições

Abra **Retornos SEFAZ**. Uma rejeição confirmada pode ser aberta para correção, com atalhos sugeridos pelo retorno e pendências da conferência local. O atalho abre o campo na nota, no cliente, no emitente ou no item. A correção mantém a série, o número e a identidade fiscal original. Depois de corrigir, use **Salvar e enviar** para preparar novamente e confirme a transmissão no resumo.

Documentos autorizados, cancelados e denegados não são alterados por este fluxo. Situações incertas/em processamento exigem consulta; o programa não reenvia automaticamente uma operação incerta. Os atalhos são sugestões a partir do texto do retorno, não uma classificação fiscal automática.

## Estoque opcional por empresa

Em **Configurações → Geral → Estoque e Google Drive**, escolha **Controlar estoque? Sim/Não**. O padrão é Não. Ao ativar, informe o saldo inicial por ajuste. Não há lançamento retroativo automático das notas já autorizadas. Cada ambiente tem seu saldo: homologação não movimenta produção.

Novas NF-e autorizadas movimentam o estoque conforme o tipo de operação. XML recebidos podem movimentar estoque na importação, com escolha do produto e fator de conversão de unidade. Sem vínculo, o item fica pendente para revisão. Quantidade do XML × fator equivale à quantidade na unidade do cadastro. NF-e de entrada emitida por terceiro tem o sentido inverso para o estoque do destinatário. Cancelamento confirmado ou importado com evento processado gera um estorno vinculado, sem apagar o movimento original. Consultas repetidas não duplicam movimentos.

Os movimentos e ajustes ficam no histórico. O controle é quantitativo: não calcula custo médio, CMV, inventário fiscal ou apuração de tributos. Saldo negativo é exibido para revisão e não bloqueia uma emissão fiscal.

## Pacote contábil mensal

Abra **Relatórios → Pacote mensal para a contabilidade** e selecione mês e ambiente. O ZIP reúne XML de emitidas, canceladas, eventos e documentos importados, com relatório CSV e HTML. Entradas importadas aparecem mesmo com o estoque desativado. Produção e homologação são exportadas separadamente.

O período considera emissão; cancelamentos também entram no mês de registro do evento. A situação dos XML importados é a declarada no arquivo, sem consulta atual à SEFAZ. A chave é preservada como texto no CSV. Um XML de entrada ausente impede a geração de pacote incompleto: importe novamente o mesmo arquivo para repor a cópia local, preservando os movimentos existentes. O pacote serve à conferência/importação de XML no processo contábil e não gera SPED nem substitui a apuração no Domínio.

## Duplicar e clonar

Em **Detalhes da nota → Duplicar**, reaproveite os dados em novo rascunho. A tela inicial também oferece **Clonar última NF-e** salva no ambiente ativo. A cópia recebe nova numeração e data, preserva os dados comerciais e exige revisão da tributação, pagamentos detalhados e totais especiais. Não copia autorização, protocolo nem chave fiscal original. Duplicar não transmite a nova nota.

## XML local e cópia adicional no Google Drive

O XML original permanece no PC de emissão, no arquivo local do emissor. Em **Configurações → Geral → Estoque e Google Drive**, ative a cópia e indique uma pasta existente sincronizada pelo Google Drive para computador, da sua conta ou compartilhada pelo escritório. Cada empresa escolhe suas opções; as cópias usam subpastas de CNPJ, ambiente e mês.

O emissor faz somente cópias adicionais dos XML autorizados e eventos registrados. Opcionalmente copia também XML de entrada. Não move ou apaga os originais e não envia certificado, senha nem banco de dados. Falha na cópia não altera uma autorização nem impede a emissão; a rotina tenta novamente enquanto o programa estiver aberto. O status **Copiado para a pasta sincronizada** confirma a cópia no sistema de arquivos. A confirmação do envio à nuvem e a disponibilidade da conta são informadas pelo aplicativo Google Drive.


## Cadastros assistidos — 0.15.0

Em emitentes, clientes e fornecedores, escolha a UF e comece a digitar o município. Ao escolher um nome da lista, o IBGE de sete dígitos é preenchido. A tabela oficial DTB/IBGE de 31/12/2025 está no instalador; a pesquisa funciona sem internet. Também é possível informar o código completo para identificar município e UF.

Ao completar um CEP de oito dígitos, ou clicar em **Buscar CEP**, o emissor consulta o ViaCEP e abre uma prévia. Escolha os campos e clique em **Aplicar dados selecionados**. Número e complemento da residência não são deduzidos do CEP. Município/UF/IBGE são aplicados em conjunto.

Para CNPJ, clique em **Consultar CNPJ**. A BrasilAPI retorna os dados disponíveis e a prévia exibe situação cadastral e CNAE para conferência. Nome, endereço e outros campos só são preenchidos após aplicar a prévia; use **Salvar** para gravar o cadastro. IE, regime e tributação não são alterados. A consulta pública suporta CNPJ numérico; outros formatos permanecem com preenchimento manual. Somente o CEP ou CNPJ consultado é enviado ao provedor indicado, sem XML, A1 ou senhas. Os serviços gratuitos podem ficar indisponíveis; o formulário e o preenchimento manual continuam disponíveis.

## Cópia automática de edição — 0.15.0

Ao editar uma NF-e, as alterações são copiadas para o banco local após cerca de um segundo de pausa. A faixa no formulário informa quando o banco confirmou a gravação ou quando houve falha. Também existe **Salvar cópia agora**. A cópia inclui o produto ainda em edição, mas não o grava no cadastro geral, não reserva numeração e não prepara nem transmite XML.

Na tela inicial, use **Recuperar rascunhos** para conferir as cópias da empresa e ambiente atuais. Se a nota original mudou ou foi finalizada, a recuperação exige uma nova NF-e, renovando a identidade e as revisões fiscais. Confira data, itens e tributação antes de concluir. **Apenas salvar** grava a nota e remove a cópia de edição correspondente. **Guardar e voltar** mantém as cópias confirmadas. **Descartar cópia** apaga somente essa cópia, preservando notas salvas e XML. Há limite de 50 cópias por empresa/ambiente e 1 MB por cópia; salve a nota manualmente quando necessário. Caracteres digitados imediatamente antes de uma queda, sem confirmação de gravação, podem não ter sido copiados.

## Configurações e avisos — 0.15.0

Certificado A1, estoque e cópia adicional para o Google Drive estão na aba **Geral**. As abas separadas de Certificado e Estoque/Google Drive foram removidas. Cada grupo mantém seu botão de salvar e continua vinculado à empresa ativa.

A tela inicial mostra cópias recuperáveis, certificado próximo do vencimento, backup atrasado/pendente e cópias de XML pendentes para o Drive. Os atalhos abrem a seção correspondente. Nenhum alerta de Drive representa confirmação de envio à nuvem: o emissor confirma a cópia local; o aplicativo Google Drive realiza a sincronização.


## Modo Simples — 0.16.0

Abra **Configurações → Geral → Modo Simples → Configurar Modo Simples**. Use **Criar modelo**, informe nome, natureza, UF do cliente, indicador de IE, consumidor final, presença, pagamento e transporte. Escolha se cada produto usa seu perfil tributário ou se o modelo aplica um perfil definido. O perfil deve estar revisado e ser compatível com a UF, o regime e a operação. Marque produtos somente se quiser restringir a seleção; nenhum marcado oferece os produtos compatíveis do cadastro.

Defina as permissões de preço, desconto e pagamento. Confira os parâmetros e marque a confirmação antes de escolher **Liberado para emitir**. Na tela de configuração, selecione **Simples** como modo de emissão padrão, escolha o modelo preferido e clique em **Salvar preferência**. Cada empresa mantém sua própria escolha. Não foi criada uma aba adicional nas configurações.

Ao abrir **Nova NF-e**, escolha o cliente, adicione produtos e ajuste quantidades. O pagamento padrão e a modalidade de transporte ficam visíveis; fatura, parcelas e dados da transportadora estão em seções próprias. Clique em **Conferir nota**, leia o resumo e confirme com **Emitir NF-e**. Esse último botão prepara e transmite, sem repetir uma segunda confirmação equivalente. Só o retorno da SEFAZ indica autorização. Sem A1 utilizável, a preparação é bloqueada e o rascunho permanece salvo.

**Guardar e voltar** mantém as cópias confirmadas da edição. Ao recuperar, confira novamente a nota. **Salvar rascunho** grava uma nota local sem transmitir. **Abrir modo completo** preserva os dados e a identidade do rascunho. Modelos alterados ou cadastros/perfis modificados exigem revalidação; o botão **Revalidar modelo e itens** reaplica os parâmetros atuais após confirmação. Se preço estiver bloqueado no modelo, essa revisão usa o preço atual do cadastro.

Esta entrega simplifica NF-e normal de saída com pagamento em dinheiro, cheque, boleto, depósito, PIX ou transferência. Operações especiais, ST, bases/valores retidos específicos, quantidades tributáveis ou créditos/ajustes particulares e pagamentos que exijam grupos adicionais devem ser conferidos no modo completo. A tributação nunca é inferida apenas pelo nome do modelo. O conector, as exigências e as limitações fiscais do motor continuam descritos em **COBERTURA.md**.
