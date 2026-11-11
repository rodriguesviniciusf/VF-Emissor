# Cobertura e trabalho restante — 0.14.0

Este arquivo distingue implementação, verificação local e validação com a SEFAZ. O projeto ainda não reproduz integralmente o NF-e Mais.

| Área | Implementado | Limite / validação restante |
|---|---|---|
| Empresas e regimes | Empresas separadas; CRT 1 e CRT 3; IRPJ separado de CRT; série/número por ambiente | CRT 2/4 e emitente em outras UFs não estão habilitados |
| Regime normal | Todos os grupos clássicos de ICMS do XSD; IPI/II; PIS/COFINS e ST; FCP; DIFAL; IBS/CBS/IS | Fórmulas comuns testadas; classificações, alíquotas e grupos especiais exigem revisão; falta homologação real |
| Monofásico e partilha | Campos tipados e totais do leiaute; cálculo manual revisado | Sem enquadramento automático, cadastro ANP ou garantia de cobertura das regras dos produtos |
| Reforma tributária | Escolha explícita de aplicabilidade, grupos e totais tipados; cálculo percentual comum e conferência das somas principais | Sem motor completo de todas as regras tributárias, tabelas externas atualizadas automaticamente ou todos os eventos RTC |
| Pagamentos | Forma simplificada ou múltiplos pagamentos detalhados e troco | Informações de integração/instituições são fornecidas pelo usuário; sem integração financeira |
| NF-e e documentos | Rascunho, assinatura, reserva, envio/consulta/status, XML/protocolo, DANFE e arquivo por ambiente | Conector AL/SVRS, A1, modelo 55 e 2026; sem validação real com A1 do usuário |
| Eventos | CC-e, cancelamento e inutilização do motor existente | Sem cancelamento extemporâneo pela interface; sem todos os eventos da reforma/manifestação |
| Recebidas/fornecedores | Importação de XML processado pertencente à empresa | Importação e cancelamento por arquivo; sem distribuição automática DF-e, NSU, manifestação ou busca sem arquivo |
| Configurações | Abas por assunto; padrões usados em novos rascunhos; dados do contador; autorizados XML e município do fato gerador | Sem SMTP, envio automático, gestão de papéis de usuários ou API pública |
| Interface dos produtos | CST troca o grupo; campos por modalidade; resumo lateral e cartões durante digitação; ST por fórmula explícita ou base manual | Sem enquadramento automático, MVA ajustada ou cálculo por dentro |
| Cadastros | Clientes, produtos e perfis; perfil de tributação a partir do item | Importação assistida CSV/XLSX/XML de produtos/clientes/fornecedores; sem consulta automática de IE, NCM/CEST/benefícios nem migração integral de outro ERP |
| Produtos e operações especiais | Tributação tipada dos grupos fiscais | DI/adições, exportação/drawback, veículos, medicamentos, rastreabilidade, demais grupos de produto e operações especiais não estão integrados à interface/XML |
| Finanças | Faturas/duplicatas e relatórios de notas autorizadas | Sem contas bancárias, conciliação, baixa de recebimentos ou ERP completo |
| Infraestrutura | Windows portátil, dados SQLite, backup local, proteção de acesso local | Sem execução Windows neste ambiente; sem hospedagem pública, HTTPS/login multiusuário, A3, NFC-e ou NFS-e |

## Antes de considerar o emissor pronto para uso fiscal

1. Validar no Windows com dados reais revisados e certificado A1 carregado localmente.
2. Emitir cenários de homologação para as operações efetivamente utilizadas pela empresa; conferir XML, DANFE e retornos.
3. Tratar rejeições e ampliar os grupos de produto/operações que a empresa usa, conforme os exemplos de XML.
4. Rever tabelas, esquemas e vigências das notas técnicas, especialmente antes de mudar a data/ano de emissão ou ampliar UFs.
5. Habilitar produção somente com série/número conciliados com todos os emissores e a revisão fiscal concluída.


## Instalação e persistência — 0.12.0

Instalador Windows por usuário, atalho na área de trabalho/menu Iniciar, dados fora do diretório do programa, importação inicial da pasta anterior, cofre A1 por empresa com DPAPI, lista/busca imediata de produtos, backup e downloads restritos à empresa da sessão. Atualizador por Release pública do GitHub no início, integridade do instalador e cópia do banco antes da atualização. Canal ainda precisa ser configurado/publicado no repositório do escritório. Instalação nativa e atualização de ponta a ponta no Windows ainda não executadas neste ambiente Linux. O workflow Windows incluído faz essas verificações antes da publicação.

## 0.13.0 — identidade visual

Ambiente interno alinhado ao login: navegação verde escura com ícones vetoriais, indicadores por empresa, formulários, tabelas, janelas e resumo fiscal em tons de verde e sálvia. Os arquivos workspace.css/workspace-ui.js tratam da apresentação; o motor de cálculo e os fluxos de emissão permanecem os existentes.

## 0.14.0 — rotinas do escritório

Importação assistida com modelo XLSX; fornecedores; estoque quantitativo opcional por empresa/ambiente, ajustes, vínculos, conversão e estorno; backup automático enquanto o aplicativo está aberto e restauração por empresa; central de rejeições com atalhos; pacote mensal com XML e CSV/HTML; clonagem da última nota; cópia adicional dos XML em pasta sincronizada do Google Drive.

A restauração cria cópia anterior e desabilita produção para revisão de numeração. A cópia para pasta sincronizada não é uma confirmação de upload à nuvem. Não há autenticação direta na API Google, controle de custo médio/CMV, SPED, apuração fiscal nem novas UFs/regimes nesta versão. Continua necessária homologação com A1 real, SEFAZ e validação da instalação no Windows.
