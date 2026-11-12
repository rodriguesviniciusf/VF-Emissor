# VF Emissor

## Candidata 0.19.0 — acesso e assinaturas

Conta por e-mail/senha com aprovação manual da conta e de cada CNPJ, painel de administração, renovações por meses e licença assinada por instalação. Consulte **ACESSO-E-ASSINATURAS.md** para implantação, uso e testes. O controle comercial precisa de projeto Supabase e conta administradora configurados; não ativa automaticamente sobre os dados existentes. A candidata é validada separadamente antes de substituir a versão estável.

Emissor local de NF-e para Windows, com interface no navegador, dados por empresa e XML guardados no PC de emissão.

## Instalar

Baixe o instalador da seção Releases deste repositório, encerre a versão anterior e execute o arquivo EXE. O instalador cria o atalho VF Emissor na área de trabalho.

Empresas, notas, configurações e XML ficam em `%LOCALAPPDATA%\VFEmissor\Dados`, separados da pasta do programa. Certificados A1 salvos são protegidos pela conta do Windows.

## Recursos da versão 0.15.0

Cidade com IBGE offline; endereço pelo CEP; consulta de CNPJ com prévia; cópia automática da edição da NF-e e do produto; painel de pendências; certificado, estoque e Google Drive reunidos na aba Geral.

Mantidos: importação assistida de produtos, clientes e fornecedores por planilha/XML; modelo XLSX; backup automático e restauração guiada; central de rejeições com atalhos de correção; estoque opcional por empresa; pacote contábil mensal; clonagem de notas; cópia adicional dos XML para pasta sincronizada do Google Drive.

Leia **LEIA-PRIMEIRO.md**, **COBERTURA.md** e **VALIDACAO.md** para instruções e limites. O projeto ainda não cobre todos os recursos de um ERP nem todos os cenários fiscais. Escopo atual: AL/SVRS, A1, modelo 55, CRT 1/3 e ano de 2026. Homologue as operações antes de usar produção.

## Publicar atualizações

O repositório contém código e recursos, sem dados de empresas, senhas, certificados ou binários do runtime. O workflow **Publicar VF Emissor para Windows** prepara o Python embarcado oficial, instala as dependências públicas, executa testes, compila e verifica o instalador antes de publicar.

Ao enviar uma nova versão em `version.json` à branch `main`, o workflow inicia automaticamente. Também é possível publicar a tag correspondente `vX.Y.Z` ou executar o workflow manualmente. O programa consulta Releases deste repositório ao iniciar uma nova execução.

## Desenvolvimento

Requer Python 3.12 no Windows. Execute `python scripts/bootstrap_windows.py` para preparar o runtime e depois `portable\python.exe -m unittest discover -s tests`. Para uso portátil, execute `INICIAR-WINDOWS.bat`.

O programa mantém o arquivo fiscal original no PC. A opção Google Drive faz somente uma cópia adicional para uma pasta sincronizada configurada pelo usuário.


## Modo Simples — 0.16.0

Abra **Configurações → Geral → Modo Simples → Configurar Modo Simples**. Use **Criar modelo**, informe nome, natureza, UF do cliente, indicador de IE, consumidor final, presença, pagamento e transporte. Escolha se cada produto usa seu perfil tributário ou se o modelo aplica um perfil definido. O perfil deve estar revisado e ser compatível com a UF, o regime e a operação. Marque produtos somente se quiser restringir a seleção; nenhum marcado oferece os produtos compatíveis do cadastro.

Defina as permissões de preço, desconto e pagamento. Confira os parâmetros e marque a confirmação antes de escolher **Liberado para emitir**. Na tela de configuração, selecione **Simples** como modo de emissão padrão, escolha o modelo preferido e clique em **Salvar preferência**. Cada empresa mantém sua própria escolha. Não foi criada uma aba adicional nas configurações.

Ao abrir **Nova NF-e**, escolha o cliente, adicione produtos e ajuste quantidades. O pagamento padrão e a modalidade de transporte ficam visíveis; fatura, parcelas e dados da transportadora estão em seções próprias. Clique em **Conferir nota**, leia o resumo e confirme com **Emitir NF-e**. Esse último botão prepara e transmite, sem repetir uma segunda confirmação equivalente. Só o retorno da SEFAZ indica autorização. Sem A1 utilizável, a preparação é bloqueada e o rascunho permanece salvo.

**Guardar e voltar** mantém as cópias confirmadas da edição. Ao recuperar, confira novamente a nota. **Salvar rascunho** grava uma nota local sem transmitir. **Abrir modo completo** preserva os dados e a identidade do rascunho. Modelos alterados ou cadastros/perfis modificados exigem revalidação; o botão **Revalidar modelo e itens** reaplica os parâmetros atuais após confirmação. Se preço estiver bloqueado no modelo, essa revisão usa o preço atual do cadastro.

Esta entrega simplifica NF-e normal de saída com pagamento em dinheiro, cheque, boleto, depósito, PIX ou transferência. Operações especiais, ST, bases/valores retidos específicos, quantidades tributáveis ou créditos/ajustes particulares e pagamentos que exijam grupos adicionais devem ser conferidos no modo completo. A tributação nunca é inferida apenas pelo nome do modelo. O conector, as exigências e as limitações fiscais do motor continuam descritos em **COBERTURA.md**.
