# Validação da versão pública

## Resultado

- 89 testes existentes passaram após consolidação e atualização para as APIs atuais.
- 4 testes adicionais passaram: dados fictícios e recusa de banco preenchido; criação de selo de oito dígitos, colisão e proteção de vínculo; coletor desativado; buscas de pessoa e veículo.
- `manage.py check`: nenhum problema identificado.
- `makemigrations --check --dry-run`: nenhum ajuste de esquema pendente.
- Migrações aplicadas com sucesso em banco novo.
- 11 rotas conferidas no navegador Chromium: painel, selos, LPR, criação de selo, pessoas, ocorrências, cadastro de veículo, cadastro de ocorrência, documentos, relatórios e ficha de pessoa.
- Nenhum erro HTTP ou JavaScript detectado nas rotas visitadas.
- 4 PDFs gerados por rota autenticada; um exemplo conferido visualmente e por extração de texto, com marca SV/DEMO e registros sintéticos.
- 6 screenshots gerados e revisados; somente dados fictícios, sem imagens de placas reais.
- Pacote ZIP verificado para ausência de `.env`, banco, mídia, backups, histórico Git, caches e credenciais locais usadas na validação.

## Ambiente e limites

Validação executada em Windows com Python 3.12, Django 5.2.17 e Chromium. O servidor foi executado em loopback com Waitress e os estáticos coletados com WhiteNoise.

Não foi feito teste com câmera Hikvision física, câmera de celular real, serviços systemd ou instalação Linux nativa. A conectividade ISAPI e a impressão em papel/equipamento físico precisam de validação específica. Screenshots documentam a demonstração local, não um ambiente de produção.

Não houve publicação ou push. O código público utiliza um esquema genérico para banco novo e não é um pacote de atualização da instalação institucional.
