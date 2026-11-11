# Validação 0.15.0

## Verificações locais

- Motor fiscal/eventos: 118 testes aprovados.
- Web, desktop e rotinas: 164 testes encontrados; 163 aprovados e 1 teste de DPAPI nativa não se aplica ao Linux.
- Total local: 281 aprovados e 1 teste exclusivo de Windows a executar no fluxo nativo.
- JavaScript verificado com node --check, módulos Python compilados e git diff --check.

Os 31 testes novos cobrem municípios e cidades homônimas, validação/formatação de CEP/CNPJ, campos permitidos, preservação de IE/regime, falhas de rede/limites/respostas, cache separado por contexto, cópias sem numeração ou XML, sobrevivência ao reabrir banco, empresa/ambiente, gravações concorrentes e repetição idempotente, produto incompleto, notas alteradas/finalizadas, renovação de revisões, tamanho, descarte versionado, backup filtrado, consulta antes do primeiro cadastro com CSRF e bloqueio de contexto após troca de empresa em outra aba.

## Interface e consultas reais

Com empresa fictícia: Arapiraca/AL preencheu IBGE 2700300. A consulta real ao CEP público de demonstração 01001000 mostrou Praça da Sé, São Paulo/SP, IBGE 3550308. Foi aplicado endereço/município preservando o número 999 e ignorando o bairro desmarcado. A consulta real ao CNPJ público de demonstração da própria documentação da BrasilAPI mostrou razão social, endereço, situação e CNAE. A prévia foi aplicada mantendo o número já digitado e sem preencher IE ou regime.

Uma nova edição com texto e produto incompleto foi copiada automaticamente. Após reiniciar o serviço e abrir outra página, ambos foram recuperados; quantidade 3 e preço 12,50 resultaram em 37,50 na conferência. A gravação manual criou somente o rascunho esperado e removeu a cópia correspondente; o catálogo de produtos não foi alterado e nenhum XML foi preparado.

Conferidas seis abas nas configurações. Geral contém certificado A1, estoque e Google Drive. A chave de estoque foi gravada e mantida nessa posição. As consultas também foram exercitadas com indisponibilidade, preservando o formulário e a alternativa manual.

## Windows e limites

O workflow [42996073370](https://github.com/rodriguesviniciusf/VF-Emissor/actions/runs/42996073370) concluiu com sucesso em 11/11/2026, usando o código c2ad03d8876eb01cf79fb5a52a1078109f1bc6b7. Foram aprovados 118 testes do motor e 163 dos 164 testes web/desktop; somente o teste destinado a plataformas sem DPAPI foi ignorado. O teste nativo de DPAPI, incluindo recuperação após reiniciar o processo, foi aprovado no Windows.

As consultas reais de CEP e CNPJ retornaram sucesso também no Windows. A compilação NSIS, instalação e reinstalação silenciosas, criação do atalho, preservação do marcador na pasta de dados, inicialização da versão instalada, catálogo offline e interface de recuperação foram aprovados antes da publicação da Release v0.15.0.

O instalador publicado e baixado para conferência tem 22.490.475 bytes. Seu SHA-256 é `bc174afe65024fbf3a379c9294ae5d02decdea03a3650143a5096bc4d8766a2d`, igual ao manifesto de atualização e ao digest do arquivo no GitHub.

Nenhum A1 real nem transmissão fiscal real foi utilizado. Os serviços de CEP/CNPJ podem variar ou ficar indisponíveis. A sincronização efetiva para a nuvem continua a cargo do Google Drive para computador. A homologação dos cenários reais permanece necessária antes da produção.
