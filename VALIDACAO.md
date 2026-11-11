# Validação 0.17.0

Testes Python: catálogo completo e zeros iniciais; descrição por hierarquia; busca com acentos e prefixos; vigência nos limites; ausência em tabela atual versus datas não cobertas; fonte indisponível/arquivo inválido preservando a cópia anterior; consulta sem envio de dados empresariais; bloqueio do NCM inválido antes de carregar certificado/assinar; correção por campo nos modos completo e simples.

Operações: adicionar/excluir naturezas por empresa, inclusive todas as iniciais, persistência após reiniciar e restauração para outro identificador da mesma empresa. Notas e modelos existentes mantêm o texto. Exclusão de importação com confirmação, isolamento de empresa/ambiente, preservação do XML/documento fiscal, estorno uma única vez, cancelamento anterior, controle desativado, pendências de vínculo, reimportação e rollback integral se houver falha ao arquivar.

Suíte local: 118 testes do motor, 226 testes web/desktop (um teste DPAPI nativo reservado ao Windows) e oito regressões JavaScript do certificado. Sintaxe dos módulos JavaScript/Python conferida. Conferência visual e funcional da consulta NCM e das naturezas na prévia local com dados fictícios.

O workflow Windows repete os testes e verifica instalação/reinstalação, preservação dos dados, atalho, inicialização, assets da interface e consulta NCM offline com o runtime embarcado antes de publicar. Certificados reais e comunicação fiscal SEFAZ não foram utilizados nos testes.
