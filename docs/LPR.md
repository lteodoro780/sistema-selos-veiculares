# Integração LPR e demonstração

O módulo `lpr` mantém passagens de veículos, a leitura original, o vínculo identificado, a revisão manual e regras aprendidas por câmera. A demonstração funciona integralmente sem dispositivo conectado: `python manage.py carregar_demo` cria passagens sintéticas e uma leitura para revisão.

## Adaptador opcional

O comando `python manage.py coletar_lpr` é desativado por padrão e recusa execução sem ativação explícita. Para conectar um equipamento próprio em ambiente autorizado, defina no `.env` privado:

```dotenv
LPR_ENABLED=true
LPR_CAM_IP=ENDERECO_DO_SEU_EQUIPAMENTO
LPR_CAM_USER=SEU_USUARIO
LPR_CAM_PASS=SUA_CREDENCIAL_PRIVADA
LPR_CAMERA_NAME=Camera configurada localmente
LPR_POLL_SECONDS=2
LPR_FORWARD_MOVEMENT=ENTRADA
LPR_REVERSE_MOVEMENT=SAIDA
LPR_UNKNOWN_MOVEMENT=PASSAGEM
```

Os valores acima são marcadores, não credenciais válidas. O adaptador recebido utiliza HTTP Digest e endpoints Hikvision ISAPI. Digest não cifra as imagens nem o tráfego HTTP; valide as condições de transporte e a compatibilidade do dispositivo antes de qualquer utilização real. Nenhuma conexão com câmera física foi executada durante a preparação pública.

O coletor consulta `/ISAPI/Traffic/channels/1/vehicleDetect/plates` e obtém JPEGs da câmera. As imagens, quando coletadas, ficam no diretório privado de mídia, nunca no Git. `deploy/selos-lpr.service.example` é um modelo opcional que exige ajuste explícito de usuário, caminhos e ambiente.

## Regras de identificação

Cadastro exato tem prioridade. Depois são consultadas regras manuais por câmera e heurísticas de confusões OCR. A faixa azul da imagem pode ajudar a identificar o padrão Mercosul; nenhum caractere é inventado sem cadastro compatível. Mais de um veículo compatível resulta em revisão. A correção manual preserva `raw_plate` e registra operador, data e observação.

Os IPs `192.0.2.x` presentes nas simulações e testes são endereços de documentação e não identificam equipamentos reais. Eles não são usados como destino padrão de coleta.
