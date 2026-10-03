# Relatório de sanitização

## Origem e escopo

Base: pacote `Selos-Linux.tar.gz` e atualizações de integração LPR, Mercosul, Mercosul v2, revisão manual v3, portaria v4, Selos v5, PDF vertical v6, painel v7, ocorrências v8/v9, proprietário v10 e criação/vínculo v11, recebidos juntos em `Selos-Completo-para-Work.tar.gz`.

Os arquivos originais foram preservados. A entrega é uma nova cópia consolidada para instalação independente; o histórico Git original e os pacotes de origem não são distribuídos. Este relatório descreve a revisão dos arquivos recebidos, não certifica versões existentes na máquina de trabalho que não foram fornecidas.

## Removido ou substituído

| Item | Tratamento na cópia pública |
| --- | --- |
| IP interno e nome da câmera | Padrões de produção removidos do coletor; variáveis privadas sem valor padrão. Fixtures usam rede de documentação. |
| Identidade institucional | Marca textual do PDF substituída por SV/DEMO; interface, categorias, campos e migrações usam organização, cargo e grupos genéricos. |
| Dados de pessoas e veículos | Exemplo CSV e casos de teste tratados como sintéticos; telefones de teste substituídos por zeros. Placas usadas como exemplos operacionais foram trocadas mantendo os cenários de confusão OCR. |
| `.env`, chaves e credenciais locais | Nenhum arquivo privado incluído. `.env.example` contém apenas campos vazios e opções genéricas; chave é gerada na instalação. |
| Banco, mídia e documentos | Não vieram dados de produção nos pacotes. O banco sintético usado na validação, mídia local e configuração gerada foram excluídos da distribuição. |
| Fotos de placas e brasões | Nenhum arquivo de foto/brasão de produção encontrado. Capturas públicas mostram somente registros fictícios e nenhuma foto real. |
| Backups de aplicação das atualizações | Excluídos da cópia pública. Ferramentas de backup permanecem como código; seus resultados são ignorados. |
| Bytecode e caches | `__pycache__`, `.pyc` e demais artefatos de execução excluídos do pacote. |
| Instaladores incrementais | Não distribuídos; suas alterações de código foram consolidadas. Não há necessidade de aplicar v1…v11 separadamente. |
| Documentação histórica | Substituída por instalação reproduzível, arquitetura, limites, segurança e operação da versão pública. |

## Preservado

Aplicativos Django, relações entre entidades, migrações para instalação vazia, autenticação, permissões, mídia privada, relatórios, QR/PDF, importação, ocorrências, revisão LPR, adaptador ISAPI e licença do componente jsQR.

Os testes contêm senhas artificiais usadas apenas em bancos temporários de teste. Não são credenciais de produção nem acesso padrão ao portal. O exemplo de configuração contém nomes de variáveis de segredo para permitir configuração local, sem respectivos valores.

## Ajustes para a consolidação

Os testes de vínculo foram atualizados para os formulários com prefixos da v11. Testes antigos de LPR foram adaptados à API atual e à exigência de imagem Mercosul. A resolução automática passou a exigir um único cadastro compatível, sem escolher arbitrariamente entre candidatos por pontuação. A importação mantém formatos de múltiplas abas com nomes de grupos genéricos.

O esquema público foi generalizado também nas migrações iniciais. Não use esta cópia como atualização direta de um banco existente. Screenshots foram gerados em sessão local com conta temporária e dados sintéticos; cookies, chaves e arquivos de sessão não são distribuídos.

## Publicação

Esta cópia sanitizada é a versão pública deste repositório. O histórico de produção, pacotes de atualização originais, bancos, mídia, credenciais e configurações privadas permanecem fora do Git. A revisão técnica de padrões e a inspeção visual das capturas foram executadas; não há garantia sobre material externo não fornecido.
