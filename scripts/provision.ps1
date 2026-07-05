param(
    [string]$ResourceGroup = "candid-rg",
    [string]$Location = "mexicocentral",
    [string]$NamePrefix = "candid",
    [string]$ResourceSuffix = "",
    [string]$PythonVersion = "3.12",
    [string]$AppServicePlanSku = "F1",
    [string]$StorageContainerName = "audios",
    [string]$Model = "gpt-4o-transcribe",
    [string]$AnthropicModel = "claude-haiku-4-5",
    [string]$AnthropicApiUrl = "https://api.anthropic.com/v1/messages",
    [string]$SkillFile = "SKILL.md",
    [string]$PublishProfilePath = ""
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Read-RequiredSecret {
    param([string]$Name)

    $existingValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($existingValue)) {
        return $existingValue
    }

    $secureValue = Read-Host "Enter $Name" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        $plainValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($plainValue)) {
        throw "$Name is required."
    }

    return $plainValue
}

function Invoke-AzCliJson {
    param([string[]]$Arguments)

    $output = & az @Arguments --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }

    if ([string]::IsNullOrWhiteSpace($output)) {
        return $null
    }

    return $output | ConvertFrom-Json
}

function Invoke-AzCliNone {
    param([string[]]$Arguments)

    & az @Arguments --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
}

Assert-Command "az"

& az account show --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "You are not logged in to Azure. Run: az login"
}

Write-Host "Ensuring Azure CLI Application Insights extension is available"
Invoke-AzCliNone @(
    "extension", "add",
    "--name", "application-insights",
    "--upgrade",
    "--only-show-errors"
)

if ([string]::IsNullOrWhiteSpace($ResourceSuffix)) {
    $suffix = ([Guid]::NewGuid().ToString("N")).Substring(0, 8).ToLowerInvariant()
}
else {
    $suffix = ($ResourceSuffix.ToLowerInvariant() -replace "[^a-z0-9]", "")
}

if ([string]::IsNullOrWhiteSpace($suffix)) {
    throw "ResourceSuffix must contain at least one alphanumeric character."
}

$appServicePlanName = "$NamePrefix-plan-$suffix"
$webAppName = "$NamePrefix-api-$suffix"
$storagePrefix = ($NamePrefix.ToLowerInvariant() -replace "[^a-z0-9]", "")
if ([string]::IsNullOrWhiteSpace($storagePrefix)) {
    $storagePrefix = "app"
}
if ($storagePrefix.Length -gt 13) {
    $storagePrefix = $storagePrefix.Substring(0, 13)
}
$storageAccountName = "$($storagePrefix)st$suffix"
$logAnalyticsName = "$NamePrefix-logs-$suffix"
$appInsightsName = "$NamePrefix-appi-$suffix"

Write-Host "Creating resource group: $ResourceGroup ($Location)"
Invoke-AzCliNone @(
    "group", "create",
    "--name", $ResourceGroup,
    "--location", $Location
)

Write-Host "Creating storage account: $storageAccountName"
Invoke-AzCliNone @(
    "storage", "account", "create",
    "--resource-group", $ResourceGroup,
    "--name", $storageAccountName,
    "--location", $Location,
    "--sku", "Standard_LRS",
    "--kind", "StorageV2",
    "--allow-blob-public-access", "false",
    "--min-tls-version", "TLS1_2",
    "--https-only", "true"
)

Write-Host "Creating blob container: $StorageContainerName"
$storageKey = & az storage account keys list `
    --resource-group $ResourceGroup `
    --account-name $storageAccountName `
    --query "[0].value" `
    --output tsv

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($storageKey)) {
    throw "Failed to read storage account key."
}

Invoke-AzCliNone @(
    "storage", "container", "create",
    "--account-name", $storageAccountName,
    "--account-key", $storageKey,
    "--name", $StorageContainerName,
    "--public-access", "off"
)

Write-Host "Creating Log Analytics workspace: $logAnalyticsName"
Invoke-AzCliNone @(
    "monitor", "log-analytics", "workspace", "create",
    "--resource-group", $ResourceGroup,
    "--workspace-name", $logAnalyticsName,
    "--location", $Location,
    "--retention-time", "30"
)

$workspace = Invoke-AzCliJson @(
    "monitor", "log-analytics", "workspace", "show",
    "--resource-group", $ResourceGroup,
    "--workspace-name", $logAnalyticsName
)

Write-Host "Creating Application Insights component: $appInsightsName"
Invoke-AzCliNone @(
    "monitor", "app-insights", "component", "create",
    "--resource-group", $ResourceGroup,
    "--app", $appInsightsName,
    "--location", $Location,
    "--workspace", $workspace.id,
    "--application-type", "web"
)

$appInsights = Invoke-AzCliJson @(
    "monitor", "app-insights", "component", "show",
    "--resource-group", $ResourceGroup,
    "--app", $appInsightsName
)

Write-Host "Creating Linux App Service Plan: $appServicePlanName"
Invoke-AzCliNone @(
    "appservice", "plan", "create",
    "--resource-group", $ResourceGroup,
    "--name", $appServicePlanName,
    "--location", $Location,
    "--sku", $AppServicePlanSku,
    "--is-linux"
)

Write-Host "Creating Python Web App: $webAppName"
Invoke-AzCliNone @(
    "webapp", "create",
    "--resource-group", $ResourceGroup,
    "--plan", $appServicePlanName,
    "--name", $webAppName,
    "--runtime", "PYTHON|$PythonVersion",
    "--https-only", "true",
    "--assign-identity"
)

$webApp = Invoke-AzCliJson @(
    "webapp", "show",
    "--resource-group", $ResourceGroup,
    "--name", $webAppName
)

$subscriptionId = $webApp.id.Split('/')[2]

Write-Host "Configuring Web App runtime settings"
$alwaysOn = "true"
if ($AppServicePlanSku -eq "F1") {
    $alwaysOn = "false"
}

Invoke-AzCliNone @(
    "webapp", "config", "set",
    "--resource-group", $ResourceGroup,
    "--name", $webAppName,
    "--linux-fx-version", "PYTHON|$PythonVersion",
    "--startup-file", "gunicorn -w 2 -k uvicorn.workers.UvicornWorker main:app",
    "--always-on", $alwaysOn,
    "--ftps-state", "Disabled",
    "--min-tls-version", "1.2"
)

Write-Host "Enabling SCM publishing for GitHub Actions publish-profile deployments"
$scmPublishingPolicyId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$webAppName/basicPublishingCredentialsPolicies/scm"
$ftpPublishingPolicyId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$webAppName/basicPublishingCredentialsPolicies/ftp"

Invoke-AzCliNone @(
    "resource", "update",
    "--ids", $scmPublishingPolicyId,
    "--set", "properties.allow=true"
)

Invoke-AzCliNone @(
    "resource", "update",
    "--ids", $ftpPublishingPolicyId,
    "--set", "properties.allow=false"
)

Write-Host "Assigning Storage Blob Data Contributor to the Web App managed identity"
Invoke-AzCliNone @(
    "role", "assignment", "create",
    "--assignee-object-id", $webApp.identity.principalId,
    "--assignee-principal-type", "ServicePrincipal",
    "--role", "Storage Blob Data Contributor",
    "--scope", "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Storage/storageAccounts/$storageAccountName"
)

Write-Host "Collecting secure application settings"
$openAiApiKey = Read-RequiredSecret "OPENAI_API_KEY"
$anthropicApiKey = Read-RequiredSecret "ANTHROPIC_API_KEY"
$supabaseUrl = Read-RequiredSecret "SUPABASE_URL"
$supabaseKey = Read-RequiredSecret "SUPABASE_KEY"
$resendApiKey = Read-RequiredSecret "RESEND_API_KEY"

Write-Host "Setting Web App application settings"
Invoke-AzCliNone @(
    "webapp", "config", "appsettings", "set",
    "--resource-group", $ResourceGroup,
    "--name", $webAppName,
    "--settings",
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
    "ENABLE_ORYX_BUILD=true",
    "WEBSITE_WEBDEPLOY_USE_SCM=true",
    "STORAGE_ACCOUNT=$storageAccountName",
    "STORAGE_CONTAINER_NAME=$StorageContainerName",
    "MODEL=$Model",
    "ANTHROPIC_MODEL=$AnthropicModel",
    "ANTHROPIC_API_URL=$AnthropicApiUrl",
    "SKILL_FILE=$SkillFile",
    "APPLICATIONINSIGHTS_CONNECTION_STRING=$($appInsights.connectionString)",
    "OPENAI_API_KEY=$openAiApiKey",
    "ANTHROPIC_API_KEY=$anthropicApiKey",
    "SUPABASE_URL=$supabaseUrl",
    "SUPABASE_KEY=$supabaseKey",
    "RESEND_API_KEY=$resendApiKey"
)

if (-not [string]::IsNullOrWhiteSpace($PublishProfilePath)) {
    Write-Host "Downloading publish profile to $PublishProfilePath"
    & az webapp deployment list-publishing-profiles `
        --resource-group $ResourceGroup `
        --name $webAppName `
        --xml > $PublishProfilePath

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download publish profile."
    }
}

$webAppUrl = "https://$($webApp.defaultHostName)"

Write-Host ""
Write-Host "Provisioning complete."
Write-Host "Web app: $webAppName"
Write-Host "URL: $webAppUrl"
Write-Host ""
Write-Host "Create these GitHub repository secrets:"
Write-Host "AZURE_WEBAPP_NAME=$webAppName"
Write-Host "AZURE_WEBAPP_PUBLISH_PROFILE=<contents of the publish profile XML>"
