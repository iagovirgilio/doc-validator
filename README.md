# Document Validator API

API para validação de documentos brasileiros (RG/CNH, diploma, comprovante de residência) usando IA. Recebe imagens ou PDFs, extrai dados estruturados e retorna JSON com validação, issues e consistência de nomes entre documentos.

**Stack:** FastAPI, OpenAI (visão + texto), LlamaParse (Llama Cloud) para extração de texto em PDFs de RG.

---

## Pré-requisitos

- **Python 3.12** (ou 3.11+)
- **Git**
- Contas e chaves:
  - [OpenAI](https://platform.openai.com/) — API Key
  - [Llama Cloud](https://cloud.llamaindex.ai/) — API Key (para LlamaParse, usado em RG em PDF)

---

## Como rodar localmente

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd doc-validator
```

*(Substitua `<url-do-repositorio>` pela URL do repositório, por exemplo `https://github.com/sua-org/doc-validator.git`.)*

### 2. Criar ambiente virtual e instalar dependências

```bash
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD) ou Linux/macOS:**
```bash
# Windows CMD
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite com suas chaves:

```bash
copy .env.example .env
```

**Linux/macOS:**
```bash
cp .env.example .env
```

Edite o `.env` e preencha:

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI (uso em visão e em extração por texto). |
| `LLAMA_CLOUD_API_KEY` | Para RG em PDF | Chave Llama Cloud (LlamaParse). Se vazio, RG em PDF usará apenas OpenAI visão. |
| `OPENAI_MODEL` | Não | Modelo OpenAI (padrão: `gpt-4o-mini`). |
| `LLAMAPARSE_TIER` | Não | Tier do LlamaParse: `fast`, `cost_effective`, `agentic` (padrão), `agentic_plus`. |
| `MAX_FILE_SIZE_MB` | Não | Tamanho máximo por arquivo em MB (padrão: 10). |

Exemplo mínimo para rodar:

```env
OPENAI_API_KEY=sk-...
LLAMA_CLOUD_API_KEY=llx-...
OPENAI_MODEL=gpt-4o-mini
LLAMAPARSE_TIER=agentic
```

### 4. Subir a API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

- **API:** http://localhost:8080  
- **Docs (Swagger):** http://localhost:8080/docs  
- **ReDoc:** http://localhost:8080/redoc  
- **Health:** http://localhost:8080/health  

O `--reload` recarrega o servidor ao alterar o código (útil em desenvolvimento).

---

## Uso rápido da API

### Endpoint unificado (recomendado)

**`POST /documents/validate`** — Envia até 3 arquivos; o **nome do arquivo** define o tipo:

| Nome do arquivo (exemplos) | Tipo |
|----------------------------|------|
| `rg.pdf`, `rg.png`, `rg_frente.jpg` | RG |
| `diploma.pdf`, `diploma.jpg` | DIPLOMA |
| `comprovante.pdf`, `comprovante_residencia.png` | COMPROVANTE_RESIDENCIA |

Exemplo com cURL:

```bash
curl -X POST "http://localhost:8080/documents/validate" \
  -H "accept: application/json" \
  -F "documentos=@rg.pdf" \
  -F "documentos=@diploma.pdf" \
  -F "documentos=@comprovante_residencia.pdf"
```

A resposta inclui `resultados` (um por documento), `resumo` (totais, nomes consistentes, processadores utilizados), `tempo_processamento_ms` e `data_processamento`.

### Endpoints por tipo

- `POST /validate/rg` — apenas RG  
- `POST /validate/diploma` — apenas diploma  
- `POST /validate/comprovante` — apenas comprovante de residência  

Consulte a documentação interativa em `/docs` para os schemas exatos.

---

## Rodar com Docker

Build da imagem:

```bash
docker build -t doc-validator .
```

Executar (passando o `.env` como variáveis de ambiente ou usando um arquivo):

```bash
docker run --env-file .env -p 8080:8080 doc-validator
```

A API ficará disponível em http://localhost:8080.

---

## Fluxo resumido

- **RG em PDF:** LlamaParse extrai o texto → OpenAI (modo JSON) preenche o schema de RG → resposta com `processador: "llamaparse"`.
- **Demais casos (diploma, comprovante, imagens, RG em imagem):** OpenAI Visão (imagem ou primeira página do PDF convertida em PNG) → JSON no schema do tipo → resposta com `processador: "openai"`.

Nenhum dado é persistido nesta API; o resultado é devolvido na resposta. A integração com Supabase (ou outro backend) fica a cargo do consumidor da API.
