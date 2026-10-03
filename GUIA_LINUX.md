# Operação local e Linux

Consulte [README.md](README.md) para instalação da versão pública. Esta cópia é uma demonstração independente: não aponte para bancos ou mídia da instalação original.

No Linux, `bash INSTALAR_LINUX.sh` cria o ambiente e pede suas credenciais de administrador. Depois carregue exemplos com `.venv/bin/python manage.py carregar_demo` e inicie com `bash INICIAR_SELOS.sh`.

Os arquivos em `deploy/` são modelos com usuário e caminhos genéricos. Eles não são instalados nem ativados automaticamente. O coletor LPR exige configuração explícita; consulte [docs/LPR.md](docs/LPR.md).

Para HTTPS, configure seu próprio DNS, certificado e proxy e execute `python gerenciar_linux.py configurar-https https://selos.example.org`, substituindo o domínio de exemplo. O servidor fica em loopback. A câmera do celular precisa de origem segura e permissão do navegador.

O comando `python gerenciar_linux.py backup` exige a instância parada e cria backup privado que inclui chave, banco e anexos. Esse backup nunca deve entrar no repositório público. A restauração em pasta vazia usa `restaurar_backup.py`; veja a ajuda do comando antes de executar.

Esta entrega foi validada no Windows. Serviços systemd, instalação Linux nativa e câmera física dependem de validação no ambiente alvo.
