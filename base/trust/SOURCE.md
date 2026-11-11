# Cadeia TLS da SVRS

Obtida em 04/11/2026 pelas URLs HTTPS oficiais indicadas na página https://certificados.serpro.gov.br/serprossl/ifr-certificate-chain . Raiz também referenciada pelo ITI em https://www.gov.br/iti/pt-br/assuntos/repositorio/repositorio-ac-raiz .

- Raiz ICP-Brasil v10: https://repositorio.serpro.gov.br/docs/icpbrasilv10.crt
- Intermediária SERPRO SSLv1: https://repositorio.serpro.gov.br/cadeias/serprossl.crt

SHA-256 DER:

- Raiz: 6e0bff069a26994c15de2c4888cc54af84882e5495b7fbf66be9ccffec7489f6
- Intermediária: 08fc942d5176e568acbef9c595f36a20de6acf9ea30c6f5fcedd48216ed5b070

As assinaturas da raiz e da intermediária foram verificadas. O handshake TLS do domínio nfe-homologacao.svrs.rs.gov.br foi validado em 04/11/2026 com verificação de hostname e cadeia ativa. Nenhum A1 real foi usado neste teste e nenhuma NF-e foi transmitida.

A cadeia pública é específica para confiança do servidor HTTPS; não substitui o certificado A1 da empresa. O aplicativo confere os fingerprints antes de carregar o recurso. Não instala raízes no Windows e não aceita certificados baixados da conexão com erro como âncoras de confiança.
