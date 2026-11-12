# VF Emissor — conta e aprovação de empresas (candidata 0.19.0)

## Situação desta entrega

Implementação e testes locais concluídos para o cliente instalado, painel e serviço de licenças. O projeto Supabase Free `VF Emissor` (`pwyeyerdbzeqwkguzjtt`, São Paulo) recebeu a migração e a função `vf-license` em 12/11/2026. A chave Ed25519 foi gerada no servidor e guardada no Vault sem exportar a chave privada. Ainda é necessário concluir as opções do Auth, cadastrar e conferir a primeira conta administradora e validar o fluxo completo antes de ativar o controle comercial nos clientes. Não há migração automática dos cadastros locais para contas na nuvem, nem licença liberada implicitamente para a primeira pessoa que se cadastrar.

O instalador de avaliação permanece no acesso local anterior até receber a configuração pública do projeto. Ativar o controle comercial exige aprovação da conta e dos CNPJs correspondentes. Atualizar o executável não exclui dados, senhas locais antigas, certificados ou XML. A versão estável anterior continua disponível enquanto a candidata é validada na infraestrutura real.

## Rotina de quem administra

1. Entre na Gestão de acessos com sua conta administradora.
2. Clique em **Aguardando aprovação** e abra **Aprovar e liberar 1 mês**.
3. Confira razão social, CNPJ, responsável, quantidade de computadores e a data de vencimento mostrada.
4. Confirme. O mesmo botão pode aprovar a conta e o primeiro CNPJ juntos.
5. Recebeu um pagamento? Use **Renovar 1 mês**. É possível escolher 1, 3, 6 ou 12 meses e anotar a referência do pagamento.

Uma assinatura ativa soma meses ao vencimento atual. Uma assinatura vencida começa o novo período no dia da renovação. O cálculo usa meses de calendário, inclusive fevereiro e fim de mês, com data de referência de Brasília. Cada operação é registrada e tem identificador único: repetir uma requisição não estende a validade novamente. Uma alteração feita em outra tela exige atualizar a lista.

Em **Gerenciar**, suspenda a empresa, altere o limite de computadores ou desative uma instalação antiga. Em **Contas dos usuários**, aprove/reprove/suspenda o responsável. Uma conta aprovada não libera automaticamente seus CNPJs. Reativação não altera o vencimento nem renova silenciosamente. Para renovar uma conta suspensa, reative-a primeiro.

O histórico mantém liberações, renovações, suspensões e solicitações de recuperação. O painel não recebe pagamentos nem faz cobrança bancária automática. Nesta etapa, cada conta responsável possui suas próprias solicitações de CNPJ; convites de funcionários e permissões por função são uma evolução separada.

## Rotina do cliente

Crie sua conta com nome, e-mail, senha de 10 a 128 caracteres, CNPJ e razão social. Não há e-mail automático de confirmação quando a configuração descrita abaixo está aplicada. A conta e a empresa começam pendentes. Até a aprovação, a tela mostra apenas as solicitações, sem acesso à área fiscal.

Após a liberação, entre em **Minhas empresas**, escolha o CNPJ e complete os dados fiscais locais. Empresas existentes neste PC são reconhecidas pelo CNPJ e reutilizadas. Empresas novas começam em homologação. Outro CNPJ requer outra solicitação; informar o CNPJ de terceiros não vincula automaticamente dados ou libera uma licença existente.

Vencimento ou suspensão bloqueiam novas NF-e e inutilizações, preservando consulta, download de XML, backup e tratamento dos documentos já transmitidos (consulta e eventos de cancelamento/correção dentro das regras fiscais anteriores). CNPJ, empresa local e licença são conferidos também nas rotas HTTP, antes de abrir o A1 ou preparar/transmitir uma nota.

O login exige internet. A sessão local dura no máximo 12 horas e não grava senha nem tokens de autenticação em disco. Durante uma sessão já aberta, falha temporária do serviço pode usar a última autorização assinada, limitada a 72 horas e ao vencimento da assinatura; na prática prevalece o menor prazo entre licença e sessão. Reiniciar o serviço exige novo login online. A autorização é conferida novamente antes de novas emissões; uma negativa explícita elimina a cópia em memória. Suspensões remotas não são instantâneas durante uma indisponibilidade. Documentos continuam fisicamente nas pastas locais mesmo sem acesso ao serviço.

Para recuperação, o suporte confere a identidade por um contato conhecido e gera um código de uso único. O cliente abre **Esqueci minha senha**, informa o código e define sua senha. O administrador não vê a senha. A aprovação manual não comprova a propriedade do e-mail; por isso a verificação de identidade na recuperação é indispensável. A recuperação da própria conta administradora é realizada fora desse painel, pelo operador do projeto.

## Implantação técnica — sem plano Pro obrigatório

1. Selecionar/criar um projeto Supabase **Free** exclusivo do VF Emissor. Não usar outro projeto sem conferir o conteúdo. Aplicar `supabase/migrations/202611120001_access.sql` em projeto novo; essa migração é de aplicação única e deve ser registrada no histórico do Supabase.
2. Em Auth, habilitar cadastro por e-mail/senha e desativar **Confirm email**. Não usar convite por e-mail ou envio SMTP como requisito desse fluxo. Definir validade de recuperação curta (por exemplo 1 hora), comprimento mínimo de senha de pelo menos 10 caracteres e limites de requisições apropriados. O banco sempre cria contas como `pending`, independentemente dos metadados enviados pelo usuário.
3. Gerar par Ed25519. A chave **privada PKCS8 em base64** fica somente no servidor. Pode ser armazenada no segredo `VF_LICENSE_PRIVATE_KEY` da Edge Function ou no Supabase Vault com nome `vf_emissor_license_ed25519`. O fallback Vault é acessível apenas pelo papel `service_role` na RPC `vf_runtime_config`; nunca consultar a chave pelo cliente. A chave **pública raw de 32 bytes em base64** vai na configuração dos clientes; a ação `public_key` da Edge devolve somente essa chave pública. Não substituir pela chave do certificado fiscal nem pelo segredo JWT.
4. Publicar `supabase/functions/vf-license/index.ts` com `verify_jwt=false` conforme `supabase/config.toml`. A função faz sua própria verificação de identidade em `/auth/v1/user`, compatível com JWT assimétrico. `SUPABASE_SERVICE_ROLE_KEY` fica exclusivamente no servidor para ler a configuração protegida e gerar recuperação assistida, após autorização administrativa e auditoria.
5. Configurar `VF_PORTAL_ORIGINS` com as origens HTTPS exatas do painel, separadas por vírgula, ou editar `vf_private.runtime_settings.allowed_origins` quando o servidor usar o fallback Vault. Para o painel local, adicionar a origem exata usada, por exemplo `http://127.0.0.1:8787`. Não usar `*`. A aplicação instalada chama a licença pelo servidor Python, sem CORS externo.
6. O responsável abre **Primeiro acesso** no painel e cria sua senha diretamente na tela. A conta fica pendente. O operador, por conexão administrativa, confere a identidade e o UUID exato e insere esse UUID em `public.vf_admins`, aprovando a linha correspondente em `vf_accounts`. O campo opcional público `first_access_email` apenas preenche o e-mail; não concede privilégios. Não há endpoint público de promoção, senha mestra embutida ou concessão de administrador pelo cadastro.
7. Criar configuração pública JSON com `url`, `publishable_key` e `verification_key`. Aceita chave `sb_publishable_...` ou JWT legado cujo papel seja `anon`. **Nunca colocar `service_role`, senha do banco ou chave privada no programa/painel.**
8. No painel, fornecer `portal/config.json` antes da hospedagem. O painel também pode ser aberto no programa em `/gestao/`, com a configuração pública do próprio cliente, e requer login de administrador. O arquivo de configuração pública pode ser importado na primeira abertura do painel quando ainda não estiver pré-configurado.
9. No instalador comercial, fornecer `commercial-config.json` antes da compilação ou ativar no cliente em **Configurações → Geral → Conta e acesso** importando o arquivo público. Para empresas já existentes, fazer backup e aprovar seus CNPJs antes de ativar. O arquivo é copiado para a pasta fixa `Dados/acesso`. Remover a configuração após ativar causa falha de acesso, sem retornar silenciosamente ao login local antigo.
10. Validar em projeto de homologação: cadastro sem e-mail, aprovação pendente, aprovação conjunta, login, licença assinada, seleção de CNPJ, suspensão/renovação/recuperação, negação entre duas contas e computadores, dados antigos e plano de restauração do banco online. Só depois distribuir a configuração comercial e promover a candidata para estável.

O banco na nuvem contém contas, solicitações, licenças, dispositivos e auditoria. XML, A1 e senha do certificado não são enviados. Tabelas têm RLS e não permitem acesso direto de `anon`/`authenticated`; as funções privilegiadas `SECURITY DEFINER` ficam no esquema não exposto `vf_private`, usam `search_path` vazio e verificam `auth.uid()`/a tabela protegida de administradores. As RPCs públicas são wrappers `SECURITY INVOKER` com execução limitada ao papel necessário. Aprovação não é lida de `user_metadata`. Assinaturas vinculam usuário, CNPJ, licença e instalação. O código executado no PC pode ser modificado por terceiros; não há proteção local inviolável.

Limites e pausas do plano Free continuam aplicáveis. Não há garantia de disponibilidade nem de custo zero permanente. O backup fiscal local não substitui o backup das contas/licenças no Supabase; definir cópia e restauração do projeto antes de depender dele comercialmente.

## Verificações reproduzíveis

- `python -m unittest discover -s tests`: regressões do emissor, assinatura Ed25519, isolamento, HTTP, bloqueio de emissão e download de backup após vencimento, sem usar A1 real.
- `node --test tests/access-edge.test.cjs`: autenticação e privilégios da Edge Function com Auth simulado e assinatura real, indisponibilidade como 503, recuperação somente por admin com confirmação de identidade e auditoria sem código/senha.
- `node --test tests/access-sql.test.cjs`: migração real em PostgreSQL/PGlite com papéis Auth simulados; privilégios, metadados maliciosos, isolamento, calendário, idempotência, revisões, dispositivos e vencimento. Requer `@electric-sql/pglite@0.5.16`, instalado fora da distribuição. `VF_PGLITE_PATH` pode apontar ao pacote local.
- `tests/preview-access.cjs`: demonstração isolada, PostgreSQL em memória e identidades fictícias. Serve somente pelo gerenciador de prévia de desenvolvimento. A aprovação e a renovação de 3 meses foram conferidas pela interface e no histórico. Não representa uma implantação real de Supabase nem confirma funcionamento do serviço hospedado.

Referências: https://supabase.com/docs/guides/auth/general-configuration ; https://supabase.com/docs/guides/database/postgres/row-level-security ; https://supabase.com/docs/guides/functions/secrets ; https://supabase.com/docs/reference/javascript/auth-admin-generatelink .
