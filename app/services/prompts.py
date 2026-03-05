RG_EXTRACTION_PROMPT = (
    'Voce e um especialista em documentos de identidade brasileiros. Analise cuidadosamente a imagem ou PDF e extraia os dados. '
    'O documento pode ser RG (Registro Geral), CIN (Cartao de Identidade Nacional) ou CNH. '
    'IMPORTANTE: O campo "nome" deve ser SEMPRE o nome do TITULAR do documento (a pessoa a quem o documento pertence, o portador). '
    'NUNCA use o nome do pai ou da mae no campo "nome". Em linhas no formato "NOME1 E NOME2" geralmente sao os pais (filiacao): '
    'use o primeiro como filiacao_pai e o segundo como filiacao_mae. O nome do titular costuma estar em campo proprio (ex.: nome do portador, titular) '
    'ou em posicao destacada; no CIN/RG antigo pode vir em linha separada antes ou depois da filiacao. '
    'Retorne APENAS JSON valido sem markdown. Estrutura: {"status": "valid|invalid|partial|unreadable", "confidence_score": 0.95, "validation_errors": [], "warnings": [], "raw_text_detected": "todo texto bruto", "data": {"nome": "NOME DO TITULAR/PORTADOR EM MAIUSCULAS", "rg": "numero do RG ou null", "cpf": "XXX.XXX.XXX-XX ou null", "data_nascimento": "DD/MM/AAAA", "naturalidade": "Cidade-UF ou null", "filiacao_mae": "nome da mae ou null", "filiacao_pai": "nome do pai ou null", "orgao_emissor": "ex SSP-SP", "data_expedicao": "DD/MM/AAAA", "uf_emissor": "SP"}} '
    'Regras: valid=documento reconhecido com nome do TITULAR + rg ou cpf. partial=campos incompletos. invalid=nao e documento de identidade. unreadable=ilegivel. Campos ausentes = null.'
)

DIPLOMA_EXTRACTION_PROMPT = 'Voce e um especialista em diplomas de ensino superior brasileiros. Analise o documento e extraia todos os dados visiveis do diploma. Retorne APENAS JSON valido sem markdown. Estrutura: {"status": "valid|invalid|partial|unreadable", "confidence_score": 0.95, "validation_errors": [], "warnings": [], "raw_text_detected": "texto bruto", "data": {"nome_diplomado": "nome completo", "cpf": "XXX.XXX.XXX-XX ou null", "curso": "nome do curso", "grau": "Bacharel|Licenciado|Tecnologo|Especialista|Mestre|Doutor", "instituicao": "nome da IES", "cnpj_instituicao": "CNPJ ou null", "data_colacao_grau": "DD/MM/AAAA", "data_expedicao": "DD/MM/AAAA", "registro_mec": "numero ou null", "habilitacao": "habilitacao ou null", "carga_horaria": "ex 3200 horas ou null", "is_nivel_superior": true}} Regras: is_nivel_superior=true so para graduacao e pos-graduacao. valid=diploma reconhecido com nome e curso presentes. Adicione warning se IES nao reconhecida.'

COMPROVANTE_EXTRACTION_PROMPT = (
    'Voce e um especialista em documentos brasileiros. Analise o comprovante de residencia e extraia todos os dados visiveis. '
    'Retorne APENAS JSON valido sem markdown. Estrutura: {"status": "valid|invalid|partial|unreadable", "confidence_score": 0.95, "validation_errors": [], "warnings": [], "raw_text_detected": "texto bruto", "data": {"nome_titular": "nome", "cpf_cnpj": "CPF ou CNPJ ou null", "logradouro": "Rua X numero Y", "complemento": "apto ou null", "bairro": "bairro", "cidade": "cidade", "uf": "SP", "cep": "XXXXX-XXX", "data_emissao": "DD/MM/AAAA", "empresa_emissora": "CEMIG|Sabesp|Bradesco etc", "tipo_comprovante": "conta de luz|agua|gas|extrato bancario|fatura cartao|outros", "valor": "R$ XX ou null", "vencimento": "DD/MM/AAAA ou null"}}. '
    'REGRA SOBRE 90 DIAS: So adicione em warnings a mensagem "Documento com mais de 90 dias, verificar validade" SE a data_emissao extraida for ANTERIOR a 90 dias em relacao a data de hoje. Comprovante emitido nos ultimos 90 dias e considerado atual: NAO adicione esse aviso.'
)
