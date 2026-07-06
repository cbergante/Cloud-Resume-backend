# Cloud Resume Challenge — Backend API

Serverless visitor counter API built as part of the [Cloud Resume Challenge](https://cloudresumechallenge.dev/) (Azure Edition). This repo powers the visitor counter displayed on my resume site at [resume.carlosbergante.com](https://resume.carlosbergante.com).

## Overview

This is a Python-based Azure Function that reads and increments a visitor count stored in Azure Cosmos DB (Table API), triggered via a simple HTTP request from the front-end resume site's JavaScript.

## Architecture

```
Browser (resume.carlosbergante.com)
        │
        │  HTTP GET/POST
        ▼
Azure Function (Python, Consumption plan)
        │
        │  azure-data-tables SDK
        ▼
Azure Cosmos DB (Table API, Serverless)
```

## Tech Stack

- **Runtime**: Python 3.11, Azure Functions v4
- **Hosting**: Azure Functions, Linux Consumption plan
- **Database**: Azure Cosmos DB — Table API, Serverless capacity mode
- **SDK**: [`azure-data-tables`](https://pypi.org/project/azure-data-tables/)

## API

**Endpoint:** `GET/POST /api/visitorcounter`

Increments the stored visitor count by 1 and returns the updated total.

**Response:**
```json
{ "count": 42 }
```

No authentication required (anonymous access) — this endpoint is designed to be called directly from public-facing front-end JavaScript.

## Local Development

### Prerequisites
- [Python 3.11](https://www.python.org/downloads/)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- VS Code with the [Azure Functions extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azurefunctions)
- An Azure Cosmos DB account (Table API)

### Setup

```bash
# Clone the repo
git clone https://github.com/cbergante/resumechallenge.git
cd resumechallenge

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `local.settings.json` file in the project root (this file is gitignored and should **never** be committed):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_CONNECTION_STRING": "<your-cosmos-db-connection-string>"
  }
}
```

### Run locally

```bash
func start
```

The function will be available at `http://localhost:7071/api/visitorcounter`.

## Deployment

Deployed to Azure via the VS Code Azure Functions extension (**Azure Functions: Deploy to Function App**). The `COSMOS_CONNECTION_STRING` is configured as an application setting directly on the Azure Function App — it is not stored in source control.

## Project Status

Part of an ongoing Cloud Resume Challenge build. Current progress:

- [x] Static resume site hosted on Azure Storage, served via Cloudflare (CDN + HTTPS + custom domain)
- [x] Cosmos DB (Table API) provisioned
- [x] Azure Function built and deployed
- [ ] Front-end/back-end integration (JavaScript fetch + CORS)
- [ ] Automated tests
- [ ] Infrastructure as Code (Bicep/Terraform)
- [ ] CI/CD via GitHub Actions

## Notes

Built while learning Python and Azure Functions for the first time — a couple of deviations from the original challenge guide were required due to changes in Azure's current offerings (e.g. Azure CDN classic being retired, Azure Front Door being unavailable on free-tier subscriptions). Details on these will be covered in the accompanying blog post.

## Author

**Carlos Bergante**
[LinkedIn](https://www.linkedin.com/in/carlosbergante/) · [cbergante@outlook.com](mailto:cbergante@outlook.com)
