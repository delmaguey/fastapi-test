# Azure Provisioning

The provisioning entrypoint is a PowerShell script at `scripts/provision.ps1`.

## Resources

- Resource group
- Linux App Service Plan, default `F1`
- Linux Web App for Python 3.12
- Storage account
- Private blob container for audio files
- Log Analytics workspace
- Application Insights
- Managed identity on the Web App
- Storage Blob Data Contributor role assignment for the Web App identity

## Usage

Sign in to Azure:

```powershell
az login
```

Provision resources:

```powershell
./scripts/provision.ps1 `
  -ResourceGroup candid-rg `
  -Location eastus `
  -ResourceSuffix dev01 `
  -PublishProfilePath publish-profile.xml
```

If you omit `-ResourceSuffix`, the script generates a random suffix for resource names.

The script defaults to the free `F1` App Service Plan SKU to avoid VM quota errors in subscriptions with zero App Service worker quota. To use Basic after quota is available:

```powershell
./scripts/provision.ps1 `
  -ResourceGroup candid-rg `
  -Location eastus `
  -ResourceSuffix dev01 `
  -AppServicePlanSku B1 `
  -PublishProfilePath publish-profile.xml
```

If Azure returns `Operation cannot be completed without additional quota` for `appservice plan create`, either request quota for that region/SKU or try another region:

```powershell
./scripts/provision.ps1 `
  -ResourceGroup candid-rg-west `
  -Location westus2 `
  -ResourceSuffix dev01
```

The script prompts for secure runtime settings:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `RESEND_API_KEY`

You can also pass them as environment variables before running the script.

## GitHub Actions

After provisioning, add these GitHub repository secrets:

- `AZURE_WEBAPP_NAME`: the Web App name printed by the script
- `AZURE_WEBAPP_PUBLISH_PROFILE`: the full XML publish profile

To skip publish profile download, omit `-PublishProfilePath`.

Do not commit the publish profile XML.
