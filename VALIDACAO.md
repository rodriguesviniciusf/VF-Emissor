# Validação 0.18.0

Matriz de 216 combinações AL → 27 UFs, CRT 1/3, destinatário contribuinte/não contribuinte e homologação/produção simuladas. Cada combinação gera XML, passa no XSD com assinatura por certificado sintético e confere UF, idDest, chave e presença/ausência de DIFAL. Mais 104 cenários cobrem as origens importadas 1/2/3/8 nos 26 destinos interestaduais. As taxas internas/FCP dos testes são fictícias, não uma tabela para uso fiscal.

Vinte testes novos verificam a matriz, limites próprios/partilha/valores manuais, CFOP/destino/IBGE, exceções de DIFAL, lista atual de IE isenta, assistente sem mutação de cadastro/nota, Simples sem destaque indevido, perfis por UF do Modo Simples, isolamento/persistência/datas e restauração em outro identificador da mesma empresa.

Regressões locais: 118 testes do motor, 246 testes web/desktop (um teste DPAPI nativo reservado ao Windows) e oito testes JavaScript do certificado. A conferência visual usou empresa fictícia: identificou CFOP/ICMS/DIFAL inadequados, aplicou parâmetros só no item, exigiu nova revisão e aprovou a validação estrutural sem transmitir. Nenhum certificado real ou chamada de autorização SEFAZ foi utilizado.

O workflow Windows repete os testes antes da publicação e verifica instalação/reinstalação, preservação de dados, atalho, inicialização e assets NCM/interestadual. Autorização real em cada operação, IE cadastral e enquadramento tributário permanecem sujeitos à conferência com a empresa/SEFAZ.
