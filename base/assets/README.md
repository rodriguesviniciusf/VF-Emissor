# NCM oficial

`ncm.json.gz` contém a árvore oficial vigente do Siscomex, compactada em JSON UTF-8. Referência inicial: 11/11/2026, 15.157 nós e 10.516 códigos completos. O arquivo inclui a URL de origem, o ato publicado, as datas de início/fim e o SHA256 do JSON original. Descrições com HTML são convertidas em texto.

Fonte: https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO

Documentação da Receita: https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul

Regerar: `python scripts/refresh_ncm.py` ou `python scripts/refresh_ncm.py --source-file caminho/arquivo-oficial.json`. Nenhuma biblioteca adicional é necessária.

O aplicativo tenta atualizar em segundo plano quando muda a data de referência. Falhas preservam a cópia anterior e geram aviso de vigência não confirmada. A consulta funciona sem internet. A fonte contém somente códigos vigentes: não confirma códigos ausentes em datas históricas/futuras, nem determina qual NCM é adequado ao produto. Códigos comprovadamente ausentes na tabela da data da emissão impedem a preparação/transmissão inicial. Para outras datas/cópias antigas, o aplicativo exibe advertência e não inventa uma data de extinção.
